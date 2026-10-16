#!/bin/sh
# build.sh: the whole build, no hand steps. A fresh export in, a checked site out, or nothing.
#
#   sh build.sh [OUT]                    fetch pd-books at pd-books.pin, build, check, write OUT (default dist)
#   PD_BOOKS=/path sh build.sh [OUT]     use a local pd-books checkout (its HEAD must equal the pin)
#   SA_BOOKS=/path ...                   use a local sa-books checkout (its HEAD must equal sa-books.pin)
#   OFFLINE=1 ...                        skip external link and npm requests (development only; says so)
#   CHROMIUM=/path/to/chrome ...         also run the browser check (math typeset, 3D graph counts); the
#                                        rehearsal before any deploy sets it, and a build without it says so
#
# Order: pd-books' own export check (inside site.py) -> build into a staging dir -> the oracle with its
# planted controls (58 at pd-books 43ada35, docs/BLUEPRINT.md) -> the share-alike books' oracle (8 controls) -> links -> outward -> graph -> the search index (4 controls) -> vendored libraries -> the browser (with
# CHROMIUM). OUT is replaced only when every check that ran is green.
set -eu
cd "$(dirname "$0")"
OUT=${1:-dist}
PIN=$(cat pd-books.pin)
SA_PIN=$(cat sa-books.pin)
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

if [ -n "${SA_BOOKS:-}" ]; then
  HEAD=$(git -C "$SA_BOOKS" rev-parse HEAD)
  [ "$HEAD" = "$SA_PIN" ] || { echo "REFUSED: $SA_BOOKS is at $HEAD, sa-books.pin says $SA_PIN"; exit 1; }
  [ -z "$(git -C "$SA_BOOKS" status --porcelain -- books)" ] || { echo "REFUSED: $SA_BOOKS has local changes in books/"; exit 1; }
  SA=$SA_BOOKS
else
  SA=$WORK/sa-books
  git init -q "$SA"
  git -C "$SA" fetch -q --depth 1 https://github.com/cpuchip/sa-books.git "$SA_PIN"
  git -C "$SA" -c advice.detachedHead=false checkout -q FETCH_HEAD
fi

STAGE=$WORK/dist
python3 build/site.py --export "$SRC/export" --out "$STAGE" --pin "$PIN" --sa-books "$SA" --sa-pin "$SA_PIN"
python3 tools/oracle.py "$SRC/export" "$STAGE" --control \
  --build "python3 build/site.py --export {export} --out {out} --pin $PIN --no-checks --sa-books $SA --sa-pin $SA_PIN"
python3 tools/saoracle.py "$SA" "$STAGE" --control
python3 tools/linkcheck.py "$STAGE" --control ${OFFLINE:+--offline}
python3 tools/outward.py "$SRC/export" "$STAGE" --control
python3 tools/graphcheck.py "$SRC/export" "$STAGE" --control
python3 tools/searchcheck.py "$STAGE" --control
python3 tools/vendorcheck.py "$STAGE" --control ${OFFLINE:+--offline}
if [ -n "${CHROMIUM:-}" ]; then
  python3 tools/browsercheck.py "$SRC/export" "$STAGE" --chromium "$CHROMIUM" --control --ceiling build/math-ceiling.json
fi

rm -rf "$OUT"
mkdir -p "$(dirname "$OUT")"  # a green build is never lost to a missing parent directory at the last step
mv "$STAGE" "$OUT"
if [ -n "${CHROMIUM:-}" ]; then BROWSER=" (browser checked)"; else BROWSER=" (browser check NOT run: set CHROMIUM)"; fi
echo "SITE GREEN: $OUT from pd-books $PIN and sa-books $SA_PIN${OFFLINE:+ (OFFLINE: external links and npm NOT requested)}$BROWSER"
