"""verifylive.py: the live site serves exactly the rehearsed build, and none of this repo's source.

    python3 tools/verifylive.py BASE_URL DIST [--control]

Every file in DIST (the rehearsal's output at the deployed commit) is fetched from BASE_URL and must answer 200
with the same bytes. Each directory with an index.html must also answer 200 at its directory URL, with those
bytes. This repo's source files, a .git path and a made-up page must answer 404, so the server holds the built
site and nothing beside it.
--control first runs the same comparison against a copy of DIST with one file's bytes changed and one file
added that the server cannot have, and requires exactly those two findings.
"""
import argparse
import hashlib
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

NOT_SERVED = ["build.sh", "Dockerfile", "pd-books.pin", "tools/oracle.py", "build/site.py", "deploy/nginx.conf",
              ".git/config", "no-such-page/index.html"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "books-site verifylive"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def check(base, dist):
    base = base.rstrip("/") + "/"
    dist = Path(dist)
    jobs = []
    for f in sorted(dist.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(dist).as_posix()
        want = hashlib.sha256(f.read_bytes()).hexdigest()
        jobs.append((rel, want))
        if f.name == "index.html":
            jobs.append((rel[: -len("index.html")], want))  # the directory URL ("" is the site's root)

    def one(job):
        rel, want = job
        status, body = fetch(base + rel)
        if status != 200:
            return f"{rel or '/'}: answered {status}, the rehearsed build has it"
        if hashlib.sha256(body).hexdigest() != want:
            return f"{rel or '/'}: served bytes differ from the rehearsed build"
        return None

    def absent(rel):
        status, _ = fetch(base + rel)
        return None if status == 404 else f"{rel}: answered {status}, should be 404 (not part of the site)"

    with ThreadPoolExecutor(8) as pool:
        bad = [x for x in pool.map(one, jobs) if x] + [x for x in pool.map(absent, NOT_SERVED) if x]
    return bad, len(jobs)


def control(base, dist):
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "dist"
        shutil.copytree(dist, copy)
        changed = copy / "site.css"
        changed.write_bytes(changed.read_bytes() + b"\n/* not deployed */\n")
        (copy / "books" / "planted-not-served.html").write_text("x", encoding="utf-8")
        bad, _ = check(base, copy)
    want = ["books/planted-not-served.html: answered 404, the rehearsed build has it",
            "site.css: served bytes differ from the rehearsed build"]
    if sorted(bad) != want:
        print(f"VERIFYLIVE CONTROL FAILED: planted {want}, checker said {bad[:8]}")
        sys.exit(2)
    print("verifylive control: RED as planted (a changed file; a file the server does not have)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        control(a.base, a.dist)
    bad, n = check(a.base, a.dist)
    for line in bad[:30]:
        print(f"  {line}")
    if bad:
        print(f"LIVE RED: {len(bad)} findings")
        sys.exit(1)
    print(f"LIVE GREEN: {a.base} serves all {n} paths of the rehearsed build byte for byte, "
          f"and none of the {len(NOT_SERVED)} source paths")


if __name__ == "__main__":
    main()
