"""outward.py: nothing on the built site names a seat, carries an em-dash, links a claude.ai page, or leaks a
private address, an internal hostname, a local path or a token.

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
characters, so a hyphen does not hide it; an em-dash in checked text. Anywhere, exempt or not, ids and links
included: any claude.ai URL or Claude-Session line; a private or mesh IPv4 address (10/8, 172.16/12,
192.168/16, 100.64/10); a hostname under an internal suffix (.lan, .local, .internal, .selfhosted,
.home.arpa); a home-directory path; a token of a known shape (GitHub, Anthropic, Slack, AWS). Those are what
Michael's ruling of 2026-10-10 (decision 84) keeps out of anything public; family names are on that list too,
and no check here can know them, so they stay a reading duty.
--control plants a common seat name in an erratum class, a hyphenated seat name in evidence, an em-dash in
a correction, a seat name in a graph node name, a claude.ai link, a private address in a link, a local path
in evidence, an internal hostname in a graph node name and a token in site.js, and requires exactly those
nine red.
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
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
LEAKS = [  # checked everywhere, like CLAUDE: none of these has a reason to be on the site
    ("claude.ai link", CLAUDE),
    ("private address", re.compile(
        r"(?<![\d.])(?:10(?:\." + _OCTET + r"){3}"
        r"|(?:172\.(?:1[6-9]|2\d|3[01])|192\.168|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))(?:\." + _OCTET + r"){2})"
        r"(?![\d.]*\d)")),
    ("internal hostname", re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:lan|local|internal|selfhosted|home\.arpa)\b", re.I)),
    ("local path", re.compile(r"(?:/home/|/Users/|/root/|[A-Za-z]:\\Users\\)")),
    ("token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{22,}|sk-ant-[\w-]{20,}|xox[abprs]-[\w-]{10,}|AKIA[0-9A-Z]{16})")),
]


def leaks(s):
    return [kind for kind, rx in LEAKS if rx.search(s)]
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


SOURCE = re.compile(r"gutenberg", re.I)


def export_notes(export):
    """The export's own notes on its equations, which may name the transcription's source (not book text, so not
    exempt from the other rules)."""
    out = set()
    for f in sorted((Path(export) / "books").glob("*.json")):
        for x in json.loads(f.read_text(encoding="utf-8"))["equations"]:
            if isinstance(x.get("statement"), str) and x["statement"].strip():
                out.add(" ".join(x["statement"].split()))
    return out


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
            if c.get("text_html"):  # a text page shows the chapter's text nodes, each one as the export has it
                t = _Text()
                t.feed(c["text_html"])
                for s in t.texts:
                    add(s)
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
    """Text nodes and attributes; sa[i] says whether texts[i] is inside a share-alike book's page text
    (<article data-kind="sa-page">), which tools/saoracle.py proves is sa-books' transcription, word for word, or
    inside an element with data-field, whose text tools/oracle.py compares with the export's own field exactly (an
    excerpt's with its emphasis stars set aside): the book's words, which rendered emphasis splits into pieces no
    longer whole strings of the export."""
    VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts, self.attrs, self.sa = [], [], []
        self.depth, self.sa_depth, self.field_depth = 0, None, None

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if v:
                self.attrs.append((k, v))
        if tag in self.VOID:
            return
        self.depth += 1
        if tag == "article" and ("data-kind", "sa-page") in attrs and self.sa_depth is None:
            self.sa_depth = self.depth
        if any(k == "data-field" for k, _ in attrs) and self.field_depth is None:
            self.field_depth = self.depth

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.sa_depth == self.depth:
            self.sa_depth = None
        if self.field_depth == self.depth:
            self.field_depth = None
        self.depth -= 1

    def handle_data(self, data):
        if data.strip():
            self.texts.append(data)
            self.sa.append(self.sa_depth is not None or self.field_depth is not None)


def check(export, dist):
    names, keep, allow = roster(), book_text(export), allowed()
    notes = export_notes(export)
    dist = Path(dist)
    bad = []

    def judge(rel, s, where, raw_checked=False, quoted=False):
        if not raw_checked:
            bad.extend((rel, kind, s[:120]) for kind in leaks(s))
        flat = " ".join(s.split())
        if quoted or flat in keep or flat in allow:
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
            # the transcription's source is named on a book's own page (its provenance) and nowhere else in the
            # site's words; elsewhere only inside the export's own text, never in an attribute (2026-10-13: the
            # export's macros put it in 101 chapter pages' data-macros)
            book_page = re.fullmatch(r"books/[^/]+/index\.html|about/index\.html", rel) is not None
            for s, sa in zip(t.texts, t.sa):
                judge(rel, s, "text", quoted=sa)
                if not book_page and SOURCE.search(s) and " ".join(s.split()) not in keep | notes:
                    bad.append((rel, "the source's name outside a book page", s[:120]))
            if not book_page:
                for k, v in t.attrs:
                    if SOURCE.search(v):
                        bad.append((rel, f"the source's name in attribute {k}", v[:120]))
            for k, v in t.attrs:
                if k in ("data-id", "id", "href", "src"):
                    # ids are the export's own and links are checked by linkcheck; the leaks still fail here
                    bad.extend((rel, kind, v[:120]) for kind in leaks(v))
                    continue
                judge(rel, v, f"attribute {k}")
        elif rel == "graph/graph.json":
            g = json.loads(f.read_text(encoding="utf-8"))
            raw = f.read_text(encoding="utf-8")
            bad.extend((rel, kind, "") for kind in leaks(raw))
            for n in g["nodes"]:
                judge(rel, n[2], f"graph node {n[0]}", raw_checked=True)
        elif rel.startswith("search/") and f.suffix == ".json":
            # the search index: tools/searchcheck.py proves it holds exactly the pages' own words, which this check
            # has judged on the pages; its words (spin, church, tutor) are the books', so only leaks are looked for
            bad.extend((rel, kind, "") for kind in leaks(f.read_text(encoding="utf-8")))
        elif f.suffix in TEXT_FILES:
            raw = f.read_text(encoding="utf-8")
            bad.extend((rel, kind, "") for kind in leaks(raw))
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
        el = plant(el, r'<p class="ev">', "settled by qwenniverse-fermion-check, see /home/someone/notes. ")
        el = plant(el, r'<p class="n">', "caught in the tutor run, ")
        # in our words beside a field, not inside it: a data-field's text is the export's (the oracle compares it
        # exactly), so an em-dash planted inside one is the oracle's to see
        el = plant(el, r'Corrected: ', f"{EM} ")
        t = plant(t[:m.start()] + el + t[m.end():], r'<main>',
                  '<a href="https://claude.ai/chat/x">x</a><a href="http://10.0.0.1:8080/">y</a>')
        book.write_text(t, encoding="utf-8")
        gpath = copy / "graph" / "graph.json"
        g = json.loads(gpath.read_text(encoding="utf-8"))
        g["nodes"][0][2] = g["nodes"][0][2] + " (abacus concurred, on seat.box.lan)"
        gpath.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        # the source's name where it may not be: a chapter page's macros, and the site's own words on one
        ch = next(p for p in sorted((copy / "books").glob("*/ch/*/index.html")) if "<main" in p.read_text(encoding="utf-8"))
        ct = ch.read_text(encoding="utf-8")
        ct = re.sub(r"<main(?: data-macros=\"[^\"]*\")?>", '<main data-macros="{&quot;\\\\PGLicense&quot;: &quot;Project Gutenberg&quot;}">'
                    '<p>From Project Gutenberg.</p>', ct, count=1)
        ch.write_text(ct, encoding="utf-8")
        # a share-alike page: our provenance line is checked, the book's own words beside it are not
        sa = next(iter(sorted(copy.glob("books/*/*/p[0-9][0-9][0-9]/index.html"))), None)
        if sa is not None:
            st = sa.read_text(encoding="utf-8")
            st = plant(st, r'<p class="n">Read from ', f"checked by abacus {EM} ")
            st = plant(st, r'data-kind="sa-page"[^>]*>', f"<p>The book{EM}its own dash.</p>")
            sa.write_text(st, encoding="utf-8")
        js = copy / "site.js"
        js.write_text(js.read_text(encoding="utf-8") + "\n// ghp_" + "x" * 36 + "\n", encoding="utf-8")
        got = sorted(why.split(" in ")[0] if why.startswith("seat") else why for _, why, _ in check(export, copy))
    want = sorted(["seat name 'qwenniverse-fermion'", "seat name 'tutor'", "em-dash", "seat name 'abacus'", "claude.ai link",
                   "private address", "local path", "internal hostname", "token",
                   "the source's name in attribute data-macros", "the source's name outside a book page"]
                  + (["em-dash", "seat name 'abacus'"] if sa is not None else []))
    if got != want:
        print(f"OUTWARD CONTROL FAILED: planted {want}, checker said {got}")
        sys.exit(2)
    print("outward control: RED as planted (seat names in a class, evidence and a graph node; an em-dash; a claude.ai link;"
          " a private address, a local path, an internal hostname, a token; the source's name in a chapter page's macros"
          " and in its own words)")


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
    print("OUTWARD GREEN: no seat names or em-dashes outside the book's own text; the source named only on book and about pages and in the export's own text; no claude.ai links, private addresses,"
          " internal hostnames, local paths or tokens anywhere")


if __name__ == "__main__":
    main()
