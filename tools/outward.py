"""outward.py: nothing on the built site names a seat, carries an em-dash, or links a session.

    python3 tools/outward.py EXPORT DIST [--control]

Every text node and every title/content/alt attribute of every page is read. A string that is, exactly, a
piece of book text in the export (a problem, an answer, an excerpt, an equation, a title, the licence) is the
book speaking and passes. Everything else is our writing, and fails on: a [distinct] roster name; a [common]
roster name inside an element with class ev or credit (where seat credits used to live); an em-dash; a
claude.ai session URL. graph.json is checked for em-dashes and session URLs.
--control plants a seat name in an evidence line and an em-dash in the shelf page of a copy, and requires both red.
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SESSION = re.compile(r"claude\.ai/code/session|Claude-Session", re.I)
EM = "—"


def roster():
    groups, cur = {"distinct": [], "common": []}, None
    for line in (HERE / "roster.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            cur = line.strip("[]")
            continue
        groups[cur].append(line)
    pat = lambda names: re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, names)) + r")(?![\w-])", re.I)
    return pat(groups["distinct"]), pat(groups["common"])


def book_text(export):
    keep = set()
    def add(s):
        if isinstance(s, str) and s.strip():
            keep.add(s.strip())
    for f in sorted((Path(export) / "books").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        b = d["book"]
        for s in [b.get("title"), b.get("edition"), (b.get("transcription") or {}).get("licence_terms")] + (b.get("authors") or []):
            add(s)
        for c in d["chapters"]:
            add(c.get("title")); add(c.get("number"))
        for x in d["excerpts"]:
            add(x.get("markdown")); add(x.get("location"))
        for x in d["equations"]:
            add(x.get("latex")); add(x.get("statement")); add(x.get("location"))
        for p in d["problems"]:
            add(p.get("markdown")); add(p.get("location"))
            for a in p.get("answer_markdown") or []:
                add(a)
        for x in d.get("errata") or []:
            add(x.get("printed")); add(x.get("corrected")); add(x.get("location")); add(x.get("context"))
    return keep


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.out = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in ("br", "meta", "link", "img", "hr", "input"):
            self.stack.append(a.get("class") or "")
        for k in ("title", "content", "alt"):
            if a.get(k):
                self.out.append((a[k], ""))
        if a.get("href"):
            self.out.append((a["href"], "href"))

    def handle_endtag(self, tag):
        if tag not in ("br", "meta", "link", "img", "hr", "input") and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if data.strip():
            self.out.append((data, " ".join(self.stack)))


def check(export, dist):
    distinct, common = roster()
    keep = book_text(export)
    bad = []
    for page in sorted(Path(dist).rglob("*.html")):
        t = _Text()
        t.feed(page.read_text(encoding="utf-8"))
        rel = page.relative_to(dist)
        for s, ctx in t.out:
            if SESSION.search(s):
                bad.append((rel, "session URL", s[:120]))
            if ctx == "href" or s.strip() in keep:
                continue
            if EM in s:
                bad.append((rel, "em-dash", s[:120]))
            m = distinct.search(s)
            if m:
                bad.append((rel, f"seat name {m.group(1)!r}", s[:120]))
            words = ctx.split()
            if ("ev" in words or "credit" in words) and common.search(s):
                bad.append((rel, f"seat name {common.search(s).group(1)!r} in a credit", s[:120]))
    g = (Path(dist) / "graph" / "graph.json")
    if g.exists():
        raw = g.read_text(encoding="utf-8")
        if SESSION.search(raw):
            bad.append(("graph/graph.json", "session URL", ""))
        if EM in raw:
            bad.append(("graph/graph.json", "em-dash", ""))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dist"
            shutil.copytree(a.dist, copy)
            idx = copy / "index.html"
            idx.write_text(idx.read_text(encoding="utf-8").replace(
                "</main>", f'<p class="ev">settled against the scan by tutor</p><p>a planted {EM} dash</p></main>', 1),
                encoding="utf-8")
            got = sorted(why for _, why, _ in check(a.export, copy))
            if got != ["em-dash", "seat name 'tutor' in a credit"]:
                print(f"OUTWARD CONTROL FAILED: planted a seat name and an em-dash, checker said {got[:5]}")
                sys.exit(2)
            print("outward control: RED as planted (a seat name in a credit, an em-dash)")
    bad = check(a.export, a.dist)
    for rel, why, s in bad[:30]:
        print(f"  {rel}: {why}: {s!r}")
    if bad:
        print(f"OUTWARD RED: {len(bad)} findings")
        sys.exit(1)
    print("OUTWARD GREEN: no seat names, em-dashes or session URLs in our writing")


if __name__ == "__main__":
    main()
