"""vendorcheck.py: the site's vendored libraries are exactly what their npm releases published, with notices.

    python3 tools/vendorcheck.py DIST [--offline] [--control]

Every file under DIST/vendor/ (bar SOURCES.json and THIRD-PARTY-NOTICES.txt) must be listed in SOURCES.json with
its sha256 and every listed file must be there; THIRD-PARTY-NOTICES.txt must name each package and each package
its bundle carries, each followed by a licence text. Online (the default; --offline for development only), each
tarball is downloaded again and must match npm's published integrity and hold the same bytes for every listed
file. --control plants a flipped byte, an unlisted file and a dropped notice in a copy and requires all three red.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

META = {"SOURCES.json", "THIRD-PARTY-NOTICES.txt"}
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vendor import INTRO, PACKAGES, PARTS, part_notice, source_header  # noqa: E402  the pins and the parts


def check(dist, offline):
    vendor = Path(dist) / "vendor"
    bad = []
    try:
        sources = json.loads((vendor / "SOURCES.json").read_text(encoding="utf-8"))
        notices = (vendor / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    except FileNotFoundError as e:
        return [f"missing {e.filename}"]
    if set(sources) != set(PACKAGES):
        bad.append(f"packages {sorted(sources)}, the pins are {sorted(PACKAGES)}")
    for name, pkg in sources.items():
        pin = PACKAGES.get(name, ("?",))[0]
        if pkg.get("version") != pin or pkg.get("tarball") != f"https://registry.npmjs.org/{name}/-/{name}-{pin}.tgz":
            bad.append(f"{name}: SOURCES says {pkg.get('version')} from {pkg.get('tarball')}, the pin is {pin}")
    listed = {f: h for pkg in sources.values() for f, h in pkg["files"].items()}
    present = {p.relative_to(vendor).as_posix() for p in vendor.rglob("*") if p.is_file()} - META
    for f in sorted(present - set(listed)):
        bad.append(f"unlisted file {f}")
    for f in sorted(set(listed) - present):
        bad.append(f"listed file missing {f}")
    for f in sorted(present & set(listed)):
        if hashlib.sha256((vendor / f).read_bytes()).hexdigest() != listed[f]:
            bad.append(f"sha256 differs {f}")
    # each notice: a "===" line, "<name> <version> (...)", a blank line, then the licence text exactly as the
    # package ships it (its sha256 recorded in SOURCES.json; online, read again from the package's own tarball)
    sections = {}
    for m in re.finditer(r"^={20,}\n(\S+) (\S+) \(([^\n]*)\)\n\n(.*?)\n*(?=^={20,}|\Z)", notices, re.S | re.M):
        sections.setdefault((m.group(1), m.group(2)), []).append((m.group(3), m.group(4).strip()))
    # (name, version, the licence its header must state, the sha256 of its text); exactly one notice each
    want = [(name, pkg["version"], pkg.get("licence"), pkg.get("licence_sha256")) for name, pkg in sources.items()]
    want += [(b["name"], b["version"], b["licence"], b["licence_sha256"])
             for pkg in sources.values() for b in pkg.get("bundles", [])]
    # a part under a licence of its own (mhchem): exactly the parts tools/vendor.py names, each over files of its
    # package, each with its own notice
    parts = [(name, x) for name, pkg in sources.items() for x in pkg.get("parts", [])]
    if sorted(x["name"] for _, x in parts) != sorted(f"{pkg}/{part}" for pkg, part, *_ in PARTS):
        bad.append(f"parts {sorted(x['name'] for _, x in parts)}, tools/vendor.py names "
                   f"{sorted(f'{pkg}/{part}' for pkg, part, *_ in PARTS)}")
    for name, x in parts:
        for f in x["files"]:
            if f not in sources[name]["files"]:
                bad.append(f"{x['name']}: its file {f} is not one of {name}'s")
        want.append((x["name"], x["version"], x["licence"], x["licence_sha256"]))
    for name, version, licence, sha in want:
        found = sections.get((name, version), [])
        if not found:
            bad.append(f"no licence notice for {name}")
        elif len(found) > 1:
            bad.append(f"{len(found)} notices for {name}")
        elif hashlib.sha256(found[0][1].encode("utf-8")).hexdigest() != sha:
            bad.append(f"the notice for {name} is not its licence text")
        elif found[0][0] != licence:
            bad.append(f"the notice for {name} states {found[0][0]!r}, its package says {licence!r}")
    extra = set(sections) - {(n, ver) for n, ver, _, _ in want}
    for n, ver in sorted(extra):
        bad.append(f"a notice for {n} {ver}, which nothing vendored carries")
    intro = notices.split("=" * 20, 1)[0]
    if intro.strip() != INTRO.strip():
        bad.append("the notices' introduction is not the one tools/vendor.py writes")
    if not offline:
        for name, pkg in sources.items():
            algo, want = pkg["integrity"].split("-", 1)
            data = urllib.request.urlopen(pkg["tarball"], timeout=60).read()
            if base64.b64encode(hashlib.new(algo, data).digest()).decode() != want:
                bad.append(f"{name}: the tarball no longer matches npm's integrity")
                continue
            tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
            upstream = {}
            for m in tar.getmembers():
                if m.isfile():
                    rel = m.name.split("/", 1)[1]
                    upstream[f"{name}/{rel.removeprefix('dist/')}"] = hashlib.sha256(tar.extractfile(m).read()).hexdigest()
            for f, h in pkg["files"].items():
                if upstream.get(f) != h:
                    bad.append(f"{f}: not byte-identical to {name}@{pkg['version']}")
            for x in pkg.get("parts", []):
                header = source_header(tar.extractfile(f"package/{x['header_from']}").read())
                text = part_notice(header, urllib.request.urlopen(x["licence_url"], timeout=60).read())
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != x["licence_sha256"]:
                    bad.append(f"{x['name']}: its header in the tarball and the licence at {x['licence_url']} are not "
                               "what its notice carries")
        for b in [x for pkg in sources.values() for x in pkg.get("bundles", [])]:
            algo, want_i = b["integrity"].split("-", 1)
            data = urllib.request.urlopen(b["tarball"], timeout=60).read()
            if base64.b64encode(hashlib.new(algo, data).digest()).decode() != want_i:
                bad.append(f"{b['name']}: the tarball no longer matches npm's integrity")
                continue
            tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
            lic = [m for m in tar.getmembers() if m.isfile() and m.name.split("/", 1)[-1] == b["licence_file"]]
            text = tar.extractfile(lic[0]).read().decode("utf-8", errors="replace").strip() if lic else ""
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != b["licence_sha256"]:
                bad.append(f"{b['name']}: its licence in the npm tarball is not the one the notices carry")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dist"
            shutil.copytree(a.dist, copy)
            v = copy / "vendor"
            js = v / "katex" / "katex.min.js"
            data = bytearray(js.read_bytes())
            data[len(data) // 2] ^= 1
            js.write_bytes(bytes(data))
            (v / "katex" / "extra.js").write_text("// not from npm\n")
            n = v / "THIRD-PARTY-NOTICES.txt"
            t = n.read_text(encoding="utf-8")
            t2 = re.sub(r"^d3-octree .*?(?=^={20,})", "", t, count=1, flags=re.S | re.M)
            assert t2 != t, "vendor control: the d3-octree notice was not found to drop"
            t2b = re.sub(r"^katex/contrib/mhchem .*?(?=^={20,})", "", t2, count=1, flags=re.S | re.M)
            assert t2b != t2, "vendor control: the mhchem notice was not found to drop"
            t2 = t2b
            t3 = re.sub(r"^(three \S+ \([^\n]*\)\n\n).*?(?=\n={20,})", r"\1See permission at the project site.", t2,
                        count=1, flags=re.S | re.M)
            assert t3 != t2, "vendor control: the three notice was not found to replace"
            t4 = re.sub(r"^(3d-force-graph \S+) \(MIT\)", r"\1 (GPL-3.0-only; not for redistribution)", t3, count=1, flags=re.M)
            assert t4 != t3, "vendor control: the 3d-force-graph header was not found to change"
            dup = re.search(r"^={20,}\nd3-color \S+ \([^\n]*\)\n\n.*?\n(?=^={20,})", t4, re.S | re.M)
            assert dup, "vendor control: no d3-color notice to duplicate"
            t2 = t4 + "\n" + dup.group(0)
            n.write_text(t2, encoding="utf-8")
            sj = v / "SOURCES.json"
            src = json.loads(sj.read_text(encoding="utf-8"))
            src["katex"]["version"] = "0.16.0"
            sj.write_text(json.dumps(src), encoding="utf-8")
            got = sorted(b.split(":")[0] if b.startswith("katex: SOURCES") else b for b in check(copy, offline=True))
        # the version plant also unhooks KaTeX's notice (it is recorded under 0.18.7): both findings are right
        want = ["a notice for katex 0.18.7, which nothing vendored carries", "katex", "no licence notice for d3-octree",
                "no licence notice for katex", "sha256 differs katex/katex.min.js", "2 notices for d3-color",
                "no licence notice for katex/contrib/mhchem",
                "the notice for 3d-force-graph states 'GPL-3.0-only; not for redistribution', its package says 'MIT'",
                "the notice for three is not its licence text", "unlisted file katex/extra.js"]
        want = sorted(want)
        if got != want:
            print(f"VENDOR CONTROL FAILED: planted {want}, checker said {got}")
            sys.exit(2)
        print("vendor control: RED as planted (a flipped byte, an unlisted file, a dropped notice, a dropped part's "
              "notice, a notice with other words, a changed licence header, a duplicate notice, a version off its pin)")
    bad = check(a.dist, a.offline)
    sources = json.loads((Path(a.dist) / "vendor" / "SOURCES.json").read_text(encoding="utf-8"))
    print(f"vendor: {sum(len(p['files']) for p in sources.values())} files from "
          + ", ".join(f"{k}@{p['version']}" for k, p in sources.items())
          + (" (npm NOT asked again: --offline)" if a.offline else ", each byte-identical to its npm tarball"))
    for b in bad[:20]:
        print(f"  {b}")
    if bad:
        print(f"VENDOR RED: {len(bad)}")
        sys.exit(1)
    print("VENDOR GREEN")


if __name__ == "__main__":
    main()
