"""vendor.py: copy the site's two libraries into build/vendor/, unchanged, with their provenance and notices.

    python3 tools/vendor.py

A maintainer tool, run by hand when a pin changes; the build never runs it and never fetches a library. For each
package below it downloads the npm tarball, checks it against npm's published integrity, copies the listed files
byte for byte, and records the tarball URL, the integrity and each file's sha256 in build/vendor/SOURCES.json.
build/vendor/THIRD-PARTY-NOTICES.txt gets the licence text of KaTeX, of 3d-force-graph, and of every package in
3d-force-graph's dependency tree (its bundle carries them). tools/vendorcheck.py checks all of it in the build.
"""
import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "vendor"
PACKAGES = {
    # pinned 2026-10-10, each published at least two weeks before
    # contrib/mhchem is NOT vendored: it is adapted from MathJax code under Apache-2.0, and the libraries were
    # approved as MIT (asked of Michael 2026-10-10); \ce formulas show as source until he rules
    "katex": ("0.18.7", ["LICENSE", "dist/katex.min.js", "dist/katex.min.css", "dist/fonts/",
                         "dist/contrib/auto-render.min.js"]),
    "3d-force-graph": ("1.80.0", ["LICENSE", "dist/3d-force-graph.min.js"]),
}
BUNDLED_BY = "3d-force-graph"  # its UMD build carries its whole dependency tree
INTRO = (
    "Third-party software in this site's vendor/ directory, and the licences it is used under.\n\n"
    f"3d-force-graph {PACKAGES[BUNDLED_BY][0]} (vendor/3d-force-graph/3d-force-graph.min.js) is a bundle that its "
    "author built with its dependencies inside it (three.js r183 among them). Each package of its dependency "
    "tree follows with its licence. The versions named are those npm resolves today for that release; the "
    "bundle carries the versions its author built with, under the same licences.\n")


def npm_view(spec, field):
    r = subprocess.run(["npm", "view", spec, field], capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit(f"npm view {spec} {field}: {r.stderr.strip()}")
    return r.stdout.strip()


def fetch_verified(url, integrity):
    algo, want = integrity.split("-", 1)
    data = urllib.request.urlopen(url, timeout=60).read()
    got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if got != want:
        raise SystemExit(f"{url}: {algo} {got} is not npm's {want}")
    return data


def licence_file(pkg_dir):
    for p in sorted(pkg_dir.iterdir()):
        if p.is_file() and p.name.lower().split(".")[0] in ("license", "licence", "copying"):
            return p
    return None


def notice_text(raw):
    """The licence as the notices file carries it (and as vendorcheck hashes it): stripped of outer whitespace."""
    return raw.decode("utf-8", errors="replace").strip()


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    sources = {}
    for name, (version, wanted) in PACKAGES.items():
        spec = f"{name}@{version}"
        url, integrity = npm_view(spec, "dist.tarball"), npm_view(spec, "dist.integrity")
        tar = tarfile.open(fileobj=io.BytesIO(fetch_verified(url, integrity)), mode="r:gz")
        files = {}
        declared = json.loads(tar.extractfile("package/package.json").read()).get("license")
        for m in tar.getmembers():
            rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
            if not m.isfile() or not any(rel == w or (w.endswith("/") and rel.startswith(w)) for w in wanted):
                continue
            data = tar.extractfile(m).read()
            dest = OUT / name / rel.removeprefix("dist/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            files[dest.relative_to(OUT).as_posix()] = hashlib.sha256(data).hexdigest()
        missing = [w for w in wanted if not any(f.startswith(f"{name}/{w.removeprefix('dist/')}") for f in files)]
        if missing:
            raise SystemExit(f"{spec}: not in the tarball: {missing}")
        sources[name] = {"version": version, "licence": declared, "tarball": url, "integrity": integrity,
                         "files": dict(sorted(files.items()))}

    # the notices: install the bundling package's tree (scripts off) only to read each package's licence
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "package.json").write_text('{"name":"notices","version":"0.0.0","private":true}')
        spec = f"{BUNDLED_BY}@{PACKAGES[BUNDLED_BY][0]}"
        subprocess.run(["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", spec], cwd=tmp,
                       check=True, capture_output=True, timeout=300)
        lock = json.loads((Path(tmp) / "package-lock.json").read_text())
        tree = []
        for key, info in sorted(lock["packages"].items()):
            if not key.startswith("node_modules/") or info.get("dev"):
                continue
            pkg_dir = Path(tmp) / key
            meta = json.loads((pkg_dir / "package.json").read_text())
            lf = licence_file(pkg_dir)
            if lf is None:
                raise SystemExit(f"{meta['name']}: no licence file in the package")
            text = notice_text(lf.read_bytes())
            tree.append({"name": meta["name"], "version": meta["version"], "licence": meta.get("license"),
                         "tarball": info["resolved"], "integrity": info["integrity"], "licence_file": lf.name,
                         "licence_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "text": text})
    sources[BUNDLED_BY]["bundles"] = [{k: v for k, v in t.items() if k != "text"} for t in tree if t["name"] != BUNDLED_BY]
    for name in PACKAGES:
        text = notice_text((OUT / name / "LICENSE").read_bytes())
        sources[name]["licence_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    katex_licence = notice_text((OUT / "katex" / "LICENSE").read_bytes())
    parts = [
        INTRO,
        f"{'=' * 72}\nkatex {PACKAGES['katex'][0]} ({sources['katex']['licence']})\n\n{katex_licence}\n",
    ]
    for t in tree:
        parts.append(f"{'=' * 72}\n{t['name']} {t['version']} ({t['licence']})\n\n{t['text']}\n")
    (OUT / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(parts), encoding="utf-8")
    (OUT / "SOURCES.json").write_text(json.dumps(sources, indent=1) + "\n", encoding="utf-8")
    n = sum(len(v["files"]) for v in sources.values())
    print(f"vendored {n} files from {', '.join(f'{k}@{v[0]}' for k, v in PACKAGES.items())}; "
          f"notices for {len(tree)} packages")


if __name__ == "__main__":
    sys.exit(main())
