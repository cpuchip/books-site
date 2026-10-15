"""saoracle.py: every page of every share-alike book is on the built site, once, with its words, formulas, figures
and credits.

    python3 tools/saoracle.py SA_BOOKS DIST [--control]

SA_BOOKS is a checkout of cpuchip/sa-books (the pin the build used); DIST the built site. Read here with its own
Markdown reading, nothing imported from the build (docs/BLUEPRINT.md, "The share-alike books"). For each book
(books/<slug>/book.json) and each transcription page (transcription/<doc>/pNNN.md):
  - presence: one element data-kind="sa-page" data-id="<slug>/<doc>/<pNNN>" on the site, on
    books/<slug>/<doc>/<pNNN>/index.html; a missing, extra or duplicated id fails;
  - words: the page's text outside math, with Markdown's markers taken out, as a sequence of words and
    punctuation, equals the article's text outside math (markers: # * _ | \\ ` are left out of both sides);
    and no Markdown marker shows in the article (a **pair**, a *pair* or _pair_, a table pipe);
  - formulas: the page's formulas in order equal the article's math spans in order, as TeX source;
  - figures: the page's figures in order equal the article's images, and each image file on the site is
    byte-identical to sa-books' fig/ file;
  - credits: on every page and on the book page, the credit block's title, excerpt line, copyright statement
    and credit equal book.json's (the excerpt line is the author's own, copied here), with links to the
    licence URL and to every URL in the credit, the licence line's own link being the licence URL; and the footer links the
    licence;
  - the book page (data-kind="sa-book") links every page of the book once, and the shelf lists the book.
--control plants, each in a fresh copy of DIST, and requires exactly its own findings red: drop a page, add a
page sa-books lacks, blank one page's copyright statement, point one page's licence link elsewhere, drop a word
from a paragraph, change one formula, drop a figure, change a figure's bytes.
"""
import argparse
import html
import json
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

EXCERPT = "From the online textbook Calculus-Based Physics by Jeffrey Schnick."  # the author's words, verbatim
MATH = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<!\\)\$(.+?)(?<!\\)\$", re.S)
FIGREF = re.compile(r"!\[[^\]]*\]\((fig/[^)\s]+)\)|<img\s+src=\"(fig/[^\"]+)\"")
TOKEN = re.compile(r"[^\W_]+|[^\w\s*_#|\\`]")
LEAK = re.compile(r"\*\*|(?<![\w*])\*[^\s*][^*]*?[^\s*]\*(?![\w*])|(?<!\w)_[^\s_][^_]*?[^\s_]_(?!\w)|\s\|\s")


def md_page(path):
    """(words, [tex], [fig/...]) of one transcription page, read here."""
    t = path.read_text(encoding="utf-8")
    lines = t.split("\n")
    assert lines[0] == "---", path
    end = lines.index("---", 1)
    body = "\n".join(lines[end + 1:])
    texs = [next(g for g in m.groups() if g is not None) for m in MATH.finditer(body)]
    rest = MATH.sub(" ", body)
    figs = [a or b for a, b in FIGREF.findall(rest)]
    rest = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", rest)
    rest = re.sub(r"<[^>]+>", " ", rest)
    rest = re.sub(r"(?m)^\s*\|[\s:|-]+\|\s*$", " ", rest)          # a table's separator row
    rest = re.sub(r"(?m)^\s*[-+] ", " ", rest)                     # a bullet (a '* ' bullet: the census has none)
    rest = re.sub(r"\\(.)", r"\1", rest)                           # escapes
    rest = html.unescape(rest)
    return TOKEN.findall(rest), texs, figs


class Page(HTMLParser):
    """The sa units on one built page: article words, math, images; credit blocks; links; footer."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.units, self.credits, self.links, self.footer_links = [], [], [], []
        self.stack, self.cur, self.math, self.credit, self.cfield, self.footer = [], None, None, None, None, 0

    BLOCK = {"p", "li", "td", "th", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table", "ul", "ol", "img"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.BLOCK and self.cur is not None:
            self.cur["text"].append(" ")  # a cell, item or paragraph boundary separates words, as on the screen
        self.stack.append((tag, a))
        if a.get("data-kind") in ("sa-page", "sa-book"):
            self.cur = {"kind": a["data-kind"], "id": a.get("data-id"), "text": [], "math": [], "imgs": [],
                        "depth": len(self.stack), "links": []}
            self.units.append(self.cur)
        if tag == "span" and self.cur is not None and self.cur["kind"] == "sa-page" and "math" in (a.get("class") or "").split():
            self.math = {"depth": len(self.stack), "tex": []}
        if tag == "img" and self.cur is not None:
            self.cur["imgs"].append(a.get("src") or "")
        if tag == "section" and "credit" in (a.get("class") or "").split():
            self.credit = {"depth": len(self.stack), "fields": {}, "links": [], "field_links": {}}
            self.credits.append(self.credit)
        if self.credit is not None and a.get("data-credit"):
            self.cfield = (a["data-credit"], len(self.stack))
            self.credit["fields"][a["data-credit"]] = ""
        if tag == "a":
            href = a.get("href") or ""
            self.links.append(href)
            if self.credit is not None:
                self.credit["links"].append(href)
                if self.cfield:
                    self.credit["field_links"].setdefault(self.cfield[0], []).append(href)
            if self.cur is not None:
                self.cur["links"].append(href)
            if self.footer:
                self.footer_links.append(href)
        if tag == "footer":
            self.footer = len(self.stack)
        if tag in ("img", "br", "meta", "link", "hr"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        d = len(self.stack)
        if self.math is not None and d == self.math["depth"]:
            tex = "".join(self.math["tex"])
            if (tex[:2], tex[-2:]) in (("\\(", "\\)"), ("\\[", "\\]")):
                tex = tex[2:-2]
            self.cur["math"].append(tex)
            self.math = None
        if self.cfield and d == self.cfield[1]:
            self.cfield = None
        if self.credit is not None and d == self.credit["depth"]:
            self.credit = None
        if self.cur is not None and d == self.cur["depth"]:
            self.cur = None
        if self.footer and d == self.footer:
            self.footer = 0
        self.stack.pop()

    def handle_data(self, data):
        if self.math is not None:
            self.math["tex"].append(data)
        elif self.cur is not None and self.cur["kind"] == "sa-page":
            self.cur["text"].append(data)
        if self.cfield:
            self.credit["fields"][self.cfield[0]] += data


def ws(s):
    return " ".join(s.split())


def check(sa, dist):
    """[(id, category, detail)]."""
    out = []
    pages = {}
    for f in sorted(dist.rglob("*.html")):
        p = Page()
        p.feed(f.read_text(encoding="utf-8"))
        p.close()
        if p.units or p.credits:
            pages[f.relative_to(dist).as_posix()] = p
    seen = {}
    for rel, p in pages.items():
        for u in p.units:
            seen.setdefault((u["kind"], u["id"]), []).append((rel, u, p))
    shelf = pages.get("index.html")
    expected = set()
    for bj in sorted((sa / "books").glob("*/book.json")):
        slug = bj.parent.name
        book = json.loads(bj.read_text(encoding="utf-8"))
        want = {"title": book["attribution"]["title_as_modified"] + ".", "excerpt": EXCERPT,
                "statement": book["licence"]["statement"], "credit": book["attribution"]["credit"]}
        urls = set(re.findall(r"https?://[^\s)]+", book["attribution"]["credit"])) | {book["licence"]["url"]}

        def credits_ok(uid, rel, p):
            if len(p.credits) != 1:
                out.append((uid, "credit", f"{rel}: {len(p.credits)} credit blocks"))
                return
            c = p.credits[0]
            for k, v in want.items():
                if ws(c["fields"].get(k, "")) != ws(v):
                    out.append((uid, "credit", f"{rel}: {k} is {ws(c['fields'].get(k, ''))[:60]!r}"))
            if c["field_links"].get("licence", [None])[0] != book["licence"]["url"]:
                out.append((uid, "credit", f"{rel}: the licence line links {c['field_links'].get('licence')}"))
            gone = urls - set(c["links"])
            if gone:
                out.append((uid, "credit", f"{rel}: no link to {sorted(gone)}"))
            if book["licence"]["url"] not in p.footer_links:
                out.append((uid, "credit", f"{rel}: the footer does not link the licence"))
        units = [h for h in seen.get(("sa-book", slug), []) if h[0] != "index.html"]  # the shelf's entry is not the page
        if len(units) != 1 or units[0][0] != f"books/{slug}/index.html":
            out.append((slug, "book", f"sa-book on {[r for r, _, _ in units]}"))
        if not shelf or ("sa-book", slug) not in {(u["kind"], u["id"]) for u in shelf.units}:
            out.append((slug, "shelf", "not on index.html"))
        page_links = []
        if units:
            rel, u, p = units[0]
            credits_ok(slug, rel, p)
            page_links = [h for h in u["links"] if re.fullmatch(r"[A-Za-z0-9]+/p\d{3}/index\.html", h)]
        for doc in book["transcription"]["documents"]:
            for md in sorted((sa / "books" / slug / "transcription" / doc).glob("p[0-9][0-9][0-9].md")):
                uid = f"{slug}/{doc}/{md.stem}"
                expected.add(("sa-page", uid))
                if page_links.count(f"{doc}/{md.stem}/index.html") != 1:
                    out.append((uid, "book-link", f"the book page links it {page_links.count(f'{doc}/{md.stem}/index.html')} times"))
                hits = seen.get(("sa-page", uid), [])
                if not hits:
                    out.append((uid, "missing", "not on the site"))
                    continue
                if len(hits) > 1:
                    out.append((uid, "duplicate", f"on {[r for r, _, _ in hits]}"))
                rel, u, p = hits[0]
                want_rel = f"books/{slug}/{doc}/{md.stem}/index.html"
                if rel != want_rel:
                    out.append((uid, "page", f"on {rel}, not {want_rel}"))
                words, texs, figs = md_page(md)
                text = "".join(u["text"])
                got = TOKEN.findall(text)
                if got != words:
                    i = next((k for k, (a, b) in enumerate(zip(got, words)) if a != b), min(len(got), len(words)))
                    out.append((uid, "words", f"differ at token {i}: site {' '.join(got[max(0, i - 3):i + 4])!r}, "
                                              f"page {' '.join(words[max(0, i - 3):i + 4])!r} ({len(got)} vs {len(words)})"))
                if LEAK.search(text):
                    m = LEAK.search(text)
                    out.append((uid, "markup", f"a Markdown marker shows: {text[max(0, m.start() - 20):m.end() + 20]!r}"))
                if [t for t in u["math"]] != texs:
                    i = next((k for k, (a, b) in enumerate(zip(u["math"], texs)) if a != b), min(len(u["math"]), len(texs)))
                    out.append((uid, "math", f"formula {i}: site {(u['math'][i] if i < len(u['math']) else None)!r:.60}, "
                                             f"page {(texs[i] if i < len(texs) else None)!r:.60} ({len(u['math'])} vs {len(texs)})"))
                site_figs = [s.rsplit("/", 1)[-1] for s in u["imgs"]]
                if site_figs != [f.rsplit("/", 1)[-1] for f in figs]:
                    out.append((uid, "figure", f"site {site_figs}, page {figs}"))
                for s in u["imgs"]:
                    on_site = (dist / Path(rel).parent / s).resolve()
                    src = sa / "books" / slug / "transcription" / doc / "fig" / s.rsplit("/", 1)[-1]
                    if not on_site.is_file() or not src.is_file() or on_site.read_bytes() != src.read_bytes():
                        out.append((uid, "figure", f"{s.rsplit('/', 1)[-1]} differs from sa-books' file or is missing"))
                credits_ok(uid, rel, p)
    for key, hits in seen.items():
        if key[0] == "sa-page" and key not in expected:
            out.append((key[1], "extra", f"on {[r for r, _, _ in hits]}, not in sa-books"))
    return out


def report(findings):
    for f in findings:
        print("  " + " | ".join(f))


def control(sa, dist):
    """Each plant in a fresh copy; [(name, ok, findings)]."""
    pages = sorted(dist.glob("books/*/*/p[0-9][0-9][0-9]/index.html"))
    rich = [p for p in pages if 'class="math inline"' in p.read_text(encoding="utf-8") and "<img" in p.read_text(encoding="utf-8")]
    a, b = rich[len(rich) // 3], rich[2 * len(rich) // 3]
    uid = lambda p: "/".join(p.relative_to(dist).parts[1:4])

    def sub(path, old, new):
        s = path.read_text(encoding="utf-8")
        assert old in s, (path, old[:40])
        path.write_text(s.replace(old, new, 1), encoding="utf-8")

    def word(path):
        s = path.read_text(encoding="utf-8")
        art = s.index('data-kind="sa-page"')
        m = re.compile(r"<p>([A-Za-z]{4,}) ").search(s, art)
        assert m, path
        path.write_text(s[:m.start(1)] + s[m.end(1) + 1:], encoding="utf-8")

    def formula(path):
        s = path.read_text(encoding="utf-8")
        i = s.index('<span class="math inline">\\(') + len('<span class="math inline">\\(')
        path.write_text(s[:i] + "Z+" + s[i:], encoding="utf-8")

    def nofig(path):
        s = path.read_text(encoding="utf-8")
        art = s.index('data-kind="sa-page"')
        m = re.compile(r"<img [^>]*>").search(s, art)
        path.write_text(s[:m.start()] + s[m.end():], encoding="utf-8")

    def figbytes(path):
        s = path.read_text(encoding="utf-8")
        m = re.compile(r'<img src="([^"]+)"').search(s, s.index('data-kind="sa-page"'))
        f = (path.parent / m.group(1)).resolve()
        f.write_bytes(f.read_bytes() + b"\0")
    licence = re.search(r'data-credit="licence">This page is licensed under <a href="([^"]+)"', a.read_text(encoding="utf-8")).group(1)
    plants = [
        ("drop a page", lambda d: shutil.rmtree(d / a.relative_to(dist).parent), {(uid(a), "missing")}),
        ("add a page sa-books lacks", lambda d: (shutil.copytree(d / b.relative_to(dist).parent, d / b.relative_to(dist).parent.with_name("p999")),
                                                 sub(d / b.relative_to(dist).parent.with_name("p999") / "index.html", f'data-id="{uid(b)}"', f'data-id="{uid(b)[:-4]}p999"')),
         {(uid(b)[:-4] + "p999", "extra")}),
        ("blank a copyright statement", lambda d: sub(d / a.relative_to(dist), re.search(r'data-credit="statement">([^<]+)<', a.read_text(encoding="utf-8")).group(1), ""), {(uid(a), "credit")}),
        ("point a licence link elsewhere", lambda d: sub(d / b.relative_to(dist), f'licensed under <a href="{licence}"', 'licensed under <a href="https://example.org/"'), {(uid(b), "credit")}),
        ("drop a word", lambda d: word(d / a.relative_to(dist)), {(uid(a), "words")}),
        ("change a formula", lambda d: formula(d / b.relative_to(dist)), {(uid(b), "math")}),
        ("drop a figure", lambda d: nofig(d / a.relative_to(dist)), {(uid(a), "figure")}),
        ("change a figure's bytes", lambda d: figbytes(d / b.relative_to(dist)), {(uid(b), "figure")}),
    ]
    results = []
    for name, plant, expect in plants:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "dist"
            shutil.copytree(dist, d)
            plant(d)
            got = check(sa, d)
            results.append((name, {(i, c) for i, c, _ in got} == expect, got))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sa_books")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    sa, dist = Path(a.sa_books), Path(a.dist)
    if a.control:
        bad = False
        for name, ok, got in control(sa, dist):
            print(f"control {'red as planted' if ok else 'WRONG'}: {name}")
            if not ok:
                bad = True
                report(got)
        if bad:
            print("SA ORACLE: a control did not come back as planted; no verdict")
            sys.exit(1)
    findings = check(sa, dist)
    n = len(list((sa / "books").glob("*/transcription/*/p[0-9][0-9][0-9].md")))
    if findings:
        report(findings[:60])
        print(f"SA ORACLE RED: {len(findings)} findings over {n} pages")
        sys.exit(1)
    print(f"SA ORACLE GREEN: {n} pages, their words, formulas, figures and credits{' (controls red as planted)' if a.control else ''}")


if __name__ == "__main__":
    main()
