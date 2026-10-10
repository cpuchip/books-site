"""oracle.py: every book, chapter, problem and erratum the export holds is on the built site, counted both sides.

    python3 tools/oracle.py EXPORT DIST                      compare; exit 1 on any difference
    python3 tools/oracle.py EXPORT DIST --control [--seed N] also plant faults and require them red
        [--build "python3 build/site.py --export {export} --out {out}"]

The export side is read here with its own walk of the JSON; nothing is shared with the build. The site side
is every data-kind/data-id pair in every .html file under DIST. Ids are compared as multisets per kind, so a
missing unit, an extra one and a duplicate all fail, each named by id.

Controls (rebuilt from read-only inputs on every run, never kept as files):
  site:   copy DIST, delete one problem element, expect red naming exactly that id;
  export: copy EXPORT, drop one problem from a book file, run --build into a temp dir, compare that site
          with the TRUE export, expect red naming exactly that id.
A match is reported only after every control came back red for the planted id and nothing else.
"""
import argparse
import json
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

KINDS = ("book", "chapter", "excerpt", "equation", "problem", "erratum")


def export_ids(export):
    """{kind: Counter(id)} from the export alone."""
    export = Path(export)
    index = json.loads((export / "books.json").read_text(encoding="utf-8"))
    ids = {k: Counter() for k in KINDS}
    listed = [b["id"] for b in index["books"]]
    files = sorted(p.stem for p in (export / "books").glob("*.json"))
    if sorted(listed) != files:
        raise SystemExit(f"oracle: books.json lists {sorted(set(listed) - set(files))} without a file, "
                         f"files {sorted(set(files) - set(listed))} unlisted")
    for b in listed:
        d = json.loads((export / "books" / f"{b}.json").read_text(encoding="utf-8"))
        ids["book"][d["book"]["id"]] += 1
        for kind, key in (("chapter", "chapters"), ("excerpt", "excerpts"), ("equation", "equations"),
                          ("problem", "problems"), ("erratum", "errata")):
            for x in d.get(key, []):
                ids[kind][x["id"]] += 1
    return ids


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pairs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-kind" in a:
            self.pairs.append((a["data-kind"], a.get("data-id")))


def site_ids(dist):
    ids = {k: Counter() for k in KINDS}
    unknown = Counter()
    for page in sorted(Path(dist).rglob("*.html")):
        p = _Collect()
        p.feed(page.read_text(encoding="utf-8"))
        for kind, i in p.pairs:
            (ids[kind] if kind in ids else unknown)[(kind, i) if kind not in ids else i] += 1
    return ids, unknown


def compare(exp, site):
    """[(kind, id, problem)] for every difference; [] means equal."""
    out = []
    for k in KINDS:
        for i in sorted(set(exp[k]) | set(site[k])):
            e, s = exp[k][i], site[k][i]
            if s == 0:
                out.append((k, i, "missing from the site"))
            elif e == 0:
                out.append((k, i, "on the site, not in the export"))
            elif s != e:
                out.append((k, i, f"{s} times on the site, {e} in the export"))
    return out


def report(exp, site):
    return "  ".join(f"{k} {sum(exp[k].values())}/{sum(site[k].values())}" for k in KINDS)


_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")


def delete_element(html, kind, i):
    """Remove the whole element carrying data-kind=kind data-id=i (depth-counted on its tag name)."""
    m = re.search(r'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bdata-kind="%s"[^>]*\bdata-id="%s"[^>]*>'
                  % (re.escape(kind), re.escape(i)), html)
    if not m:
        return None
    tag, depth = m.group(1).lower(), 1
    for t in _TAG.finditer(html, m.end()):
        if t.group(2).lower() != tag or t.group(3):
            continue
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return html[:m.start()] + html[t.end():]
    return None


def control_site(exp, dist, rng):
    """Delete one problem element from a copy of dist; the oracle must name exactly it."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "dist"
        shutil.copytree(dist, copy)
        victim = rng.choice(sorted(exp["problem"]))
        for page in sorted(copy.rglob("*.html")):
            text = page.read_text(encoding="utf-8")
            new = delete_element(text, "problem", victim)
            if new is not None:
                page.write_text(new, encoding="utf-8")
                break
        else:
            return victim, [("problem", victim, "control could not find the element to delete")]
        site, _ = site_ids(copy)
        return victim, compare(exp, site)


def control_export(export, exp, build, rng):
    """Drop one problem from a copy of the export, build it, compare with the TRUE export."""
    with tempfile.TemporaryDirectory() as tmp:
        copy, out = Path(tmp) / "export", Path(tmp) / "dist"
        shutil.copytree(export, copy)
        victim = rng.choice(sorted(exp["problem"]))
        book = next(f for f in sorted((copy / "books").glob("*.json"))
                    if victim.startswith(f.stem + "/"))
        d = json.loads(book.read_text(encoding="utf-8"))
        before = len(d["problems"])
        d["problems"] = [p for p in d["problems"] if p["id"] != victim]
        assert len(d["problems"]) == before - 1, victim
        book.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        cmd = [a.format(export=copy, out=out) for a in shlex.split(build)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return victim, [("problem", victim, f"control build failed: {r.stdout[-300:]}{r.stderr[-300:]}")]
        site, _ = site_ids(out)
        return victim, compare(exp, site)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--build", default="python3 build/site.py --export {export} --out {out} --no-checks")
    a = ap.parse_args()

    exp = export_ids(a.export)
    if a.control:
        seed = a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 30)
        rng = random.Random(seed)
        for name, run in (("site", lambda: control_site(exp, a.dist, rng)),
                          ("export", lambda: control_export(a.export, exp, a.build, rng))):
            victim, diff = run()
            if diff == [("problem", victim, "missing from the site")]:
                print(f"control {name} (seed {seed}): RED as planted, names {victim}")
            else:
                print(f"control {name} (seed {seed}): FAILED, planted {victim}, oracle said {diff[:5]}")
                sys.exit(2)

    site, unknown = site_ids(a.dist)
    diff = compare(exp, site)
    print(f"export/site: {report(exp, site)}")
    if unknown:
        print(f"unknown data-kind on the site: {sorted(unknown)[:5]}")
    if diff or unknown:
        print(f"ORACLE RED: {len(diff)} differences")
        for k, i, why in diff[:30]:
            print(f"  {k} {i}: {why}")
        sys.exit(1)
    print("ORACLE GREEN: every unit in the export is on the site exactly once"
          + (", after both controls went red" if a.control else " (controls not run)"))


if __name__ == "__main__":
    main()
