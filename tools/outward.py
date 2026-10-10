"""outward.py: nothing on the built site names a seat, carries an em-dash, or links a claude.ai page.

    python3 tools/outward.py EXPORT DIST [--control]

What is read: every text node and every attribute of every page, and every other served text file (.json,
.css, .js, .txt), including graph/graph.json's node names, which the 3D view draws.

What is exempt: a text node that is, exactly, text QUOTED FROM THE BOOK: a problem's text and printed answers,
an excerpt, an equation's LaTeX, an erratum's printed text and its source context, a book's title, authors,
edition and licence sentence, a chapter's title. Everything the pipeline or this site wrote (statements,
locations, corrections, classes, evidence, credits, our page text) is checked. A roster name that a book
really uses in text outside those fields goes in tools/outward-allow.txt, one exact string per line, so every
exemption is written down and reviewed.

Failures: any roster name (tools/roster.txt, both groups) in checked text, matched case-blind on word
characters, so a hyphen does not hide it; an em-dash in checked text; any claude.ai URL or Claude-Session line
anywhere, exempt or not.
--control plants a common seat name in an erratum class, a hyphenated seat name in evidence, an em-dash in
a correction, a seat name in a graph node name and a claude.ai link, and requires exactly those five red.
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
CLAUDE = re.compile(r"claude\.ai|Claude-Session", re.I)
EM = "\u2014"
VENDOR_OURS = {"vendor/SOURCES.json", "vendor/THIRD-PARTY-NOTICES.txt"}  # written by tools/vendor.py: checked
TEXT_FILES = {".json", ".css", ".js", ".mjs", ".txt", ".svg", ".xml"}


def roster():
    names, cur = [], None
    for line in (HERE / "roster.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("["):
            names.append(line)
    names.sort(key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_])", re.I)


def allowed():
    f = HERE / "outward-allow.txt"
    if not f.exists():
        return set()
    return {l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def book_text(export):
    keep = set()

    def add(s):
        if isinstance(s, str) and s.strip():
            keep.add(" ".join(s.split()))

    for f in sorted((Path(export) / "books").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        b = d["book"]
        for s in [b.get("title"), b.get("edition"), (b.get("transcription") or {}).get("licence_terms")] + (b.get("authors") or []):
            add(s)
        for c in d["chapters"]:
            add(c.get("title"))
            add(c.get("number"))
        for x in d["excerpts"]:
            add(x.get("markdown"))
        for x in d["equations"]:
            add(x.get("latex"))
        for p in d["problems"]:
            add(p.get("markdown"))
            for a in p.get("answer_markdown") or []:
                add(a)
        for x in d.get("errata") or []:
            add(x.get("printed"))
            add(x.get("context"))
    return keep


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if v:
                self.attrs.append((k, v))

    def handle_data(self, data):
        if data.strip():
            self.texts.append(data)


def check(export, dist):
    names, keep, allow = roster(), book_text(export), allowed()
    dist = Path(dist)
    bad = []

    def judge(rel, s, where):
        if CLAUDE.search(s):
            bad.append((rel, "claude.ai link", s[:120]))
        flat = " ".join(s.split())
        if flat in keep or flat in allow:
            return
        if EM in s:
            bad.append((rel, "em-dash", s[:120]))
        m = names.search(s)
        if m:
            bad.append((rel, f"seat name {m.group(1)!r} in {where}", s[:120]))

    for f in sorted(dist.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(dist).as_posix()
        if rel.startswith("vendor/") and rel not in VENDOR_OURS:
            continue  # third-party code, byte-identical to its npm release (tools/vendorcheck.py), not our text
        if f.suffix == ".html":
            t = _Text()
            t.feed(f.read_text(encoding="utf-8"))
            for s in t.texts:
                judge(rel, s, "text")
            for k, v in t.attrs:
                if k in ("data-id", "id", "href", "src") and not CLAUDE.search(v):
                    continue  # ids are the export's own; links are checked by linkcheck (claude.ai still fails)
                judge(rel, v, f"attribute {k}")
        elif rel == "graph/graph.json":
            g = json.loads(f.read_text(encoding="utf-8"))
            raw = f.read_text(encoding="utf-8")
            if CLAUDE.search(raw):
                bad.append((rel, "claude.ai link", ""))
            for n in g["nodes"]:
                judge(rel, n[2], f"graph node {n[0]}")
        elif f.suffix in TEXT_FILES:
            raw = f.read_text(encoding="utf-8")
            if CLAUDE.search(raw):
                bad.append((rel, "claude.ai link", ""))
            if EM in raw or "\\u2014" in raw:
                bad.append((rel, "em-dash", ""))
            m = names.search(raw)
            if m:
                bad.append((rel, f"seat name {m.group(1)!r}", ""))
    return bad


def control(export, dist):
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "dist"
        shutil.copytree(dist, copy)
        # an erratum with an evidence line and a class line, so each plant lands where its name says
        book, t, m = next((p, t, m) for p in sorted((copy / "books").glob("*/index.html"))
                          for t in [p.read_text(encoding="utf-8")]
                          for m in [re.search(r'<li class="erratum".*?</li>', t, re.S)]
                          if m and 'class="ev"' in m.group(0) and '<p class="n">' in m.group(0))
        el = m.group(0)

        def plant(s, pattern, insert):
            n = re.subn(pattern, lambda x: x.group(0) + insert, s, count=1)
            assert n[1] == 1, f"outward control: {pattern!r} did not land"
            return n[0]
        el = plant(el, r'<p class="ev">', "settled by qwenniverse-fermion-check. ")
        el = plant(el, r'<p class="n">', "caught in the tutor run, ")
        el = plant(el, r'Corrected: <span class="tx"[^>]*>', f"{EM} ")
        t = plant(t[:m.start()] + el + t[m.end():], r'<main>', '<a href="https://claude.ai/chat/x">x</a>')
        book.write_text(t, encoding="utf-8")
        gpath = copy / "graph" / "graph.json"
        g = json.loads(gpath.read_text(encoding="utf-8"))
        g["nodes"][0][2] = g["nodes"][0][2] + " (abacus concurred)"
        gpath.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        got = sorted(why.split(" in ")[0] if why.startswith("seat") else why for _, why, _ in check(export, copy))
    want = sorted(["seat name 'qwenniverse-fermion'", "seat name 'tutor'", "em-dash", "seat name 'abacus'", "claude.ai link"])
    if got != want:
        print(f"OUTWARD CONTROL FAILED: planted {want}, checker said {got[:8]}")
        sys.exit(2)
    print("outward control: RED as planted (seat names in a class, evidence and a graph node; an em-dash; a claude.ai link)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        control(a.export, a.dist)
    bad = check(a.export, a.dist)
    for rel, why, s in bad[:30]:
        print(f"  {rel}: {why}: {s!r}")
    if bad:
        print(f"OUTWARD RED: {len(bad)} findings")
        sys.exit(1)
    print("OUTWARD GREEN: no seat names, em-dashes or claude.ai links outside the book's own text")


if __name__ == "__main__":
    main()
