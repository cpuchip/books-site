#!/bin/sh
# build.sh: the whole build, no hand steps. A fresh export in, a checked site out, or nothing.
#
#   sh build.sh [OUT]                    fetch pd-books at pd-books.pin, build, check, write OUT (default dist)
#   PD_BOOKS=/path sh build.sh [OUT]     use a local pd-books checkout (its HEAD must equal the pin)
#   OFFLINE=1 ...                        skip external link requests (development only; says so)
#
# Order: pd-books' own export check (inside site.py) -> build into a staging dir -> the oracle with its
# planted controls (34, docs/BLUEPRINT.md) -> links -> outward -> graph. OUT is replaced only when every check is green.
set -eu
cd "$(dirname "$0")"
OUT=${1:-dist}
PIN=$(cat pd-books.pin)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if [ -n "${PD_BOOKS:-}" ]; then
  HEAD=$(git -C "$PD_BOOKS" rev-parse HEAD)
  [ "$HEAD" = "$PIN" ] || { echo "REFUSED: $PD_BOOKS is at $HEAD, pd-books.pin says $PIN"; exit 1; }
  [ -z "$(git -C "$PD_BOOKS" status --porcelain -- export tools)" ] || { echo "REFUSED: $PD_BOOKS has local changes in export/ or tools/"; exit 1; }
  SRC=$PD_BOOKS
else
  SRC=$WORK/pd-books
  git init -q "$SRC"
  git -C "$SRC" fetch -q --depth 1 https://github.com/cpuchip/pd-books.git "$PIN"
  git -C "$SRC" -c advice.detachedHead=false checkout -q FETCH_HEAD
fi

STAGE=$WORK/dist
python3 build/site.py --export "$SRC/export" --out "$STAGE" --pin "$PIN"
python3 tools/oracle.py "$SRC/export" "$STAGE" --control \
  --build "python3 build/site.py --export {export} --out {out} --pin $PIN --no-checks"
python3 tools/linkcheck.py "$STAGE" --control ${OFFLINE:+--offline}
python3 tools/outward.py "$SRC/export" "$STAGE" --control
python3 tools/graphcheck.py "$SRC/export" "$STAGE" --control

rm -rf "$OUT"
mv "$STAGE" "$OUT"
echo "SITE GREEN: $OUT from pd-books $PIN${OFFLINE:+ (OFFLINE: external links NOT requested)}"
