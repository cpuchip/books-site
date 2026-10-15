"""search.py: the site's search index, written from its own finished pages. books-site, MIT. Standard library only.

    python3 build/search.py DIST

Reads every page under DIST (but the search page) and writes DIST/search/: pages.json, docs.json, p/<c>.json
(postings by a word's first character) and t/<n>.json (each unit's text, for snippets). Its units, words and
format are set out in docs/BLUEPRINT.md, "Finding things". Nothing here runs on the server: the reader's browser
fetches these files and searches them itself (search.js).
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

WORD = re.compile(r"[a-z0-9]+")
# a formula written as source in a page's text (an excerpt, a problem): left out of the words, kept in the text;
# a dollar escaped as \$ (Boyden's money) is a dollar, never a delimiter
FORMULA = re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$(?:\\.|[^$\\])*\$|\\\(.*?\\\)|\\\[.*?\\\]", re.S)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# elements whose edges part words; inline ones (em, span, a) do not
SEPARATE = {"article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt", "figcaption", "figure",
            "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "img", "li", "main", "nav", "ol", "p",
            "section", "table", "tbody", "td", "th", "thead", "tr", "ul"}
CHUNK = 1000  # units per t/<n>.json; each unit's whole text, so a phrase is checked against all of it


def words(s):
    return WORD.findall(FORMULA.sub(" ", s).lower())


class _Page(HTMLParser):
    """A page's units: [kind, fragment, [text pieces], [word pieces]]. The first is the page itself (what no other
    unit holds); then each top-level block of a text article, each element with data-kind and an id."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.in_title = [], False
        self.units = [["page", "", [], []]]
        self.stack = []  # (tag, unit index or None, skip, math, text-article)
        self.main = 0
        self.macros = None

    def owner(self):
        for tag, u, skip, math, art in reversed(self.stack):
            if u is not None:
                return u
        return 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "main":
            self.main += 1
            self.macros = a.get("data-macros")
        top = self.stack[-1] if self.stack else None
        skip = bool(top and top[2]) or tag in ("script", "style", "code", "output")
        math = bool(top and top[3]) or (tag == "span" and "math" in (a.get("class") or "").split())
        u = None
        if self.main and not skip:
            if top and top[4] and a.get("id"):  # a top-level block of a chapter's text
                u = len(self.units)
                self.units.append(["text", a["id"], [], []])
            elif a.get("data-kind") and a.get("id"):
                u = len(self.units)
                self.units.append([a["data-kind"], a["id"], [], []])
        if self.main and tag in SEPARATE:
            self.piece(" ", " ")
        if tag in VOID:
            return
        article = tag == "article" and a.get("data-kind") == "text"
        self.stack.append((tag, u, skip, math, article))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if self.main and tag in SEPARATE:
            self.piece(" ", " ")
        if tag == "main":
            self.main -= 1
        for j in range(len(self.stack) - 1, -1, -1):
            if self.stack[j][0] == tag:
                del self.stack[j:]
                return

    def piece(self, text, word):
        unit = self.units[self.owner()]
        unit[2].append(text)
        unit[3].append(word)

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.main or (self.stack and self.stack[-1][2]):
            return
        math = bool(self.stack and self.stack[-1][3])
        self.piece(data, " " if math else data)


def build(dist):
    dist = Path(dist)
    out = dist / "search"
    books, book_index = [], {}
    for b in sorted(dist.glob("books/*/index.html")):
        p = _Page()
        p.feed(b.read_text(encoding="utf-8"))
        book_index[b.parent.name] = len(books)
        # the book's macros (its page's data-macros), so a snippet's formulas typeset as the book's pages do
        books.append([b.parent.name, " ".join("".join(p.title).split()), json.loads(p.macros) if p.macros else {}])
    pages, docs, texts, post, kinds = [], [], [], {}, []
    for f in sorted(dist.rglob("index.html")):
        rel = f.relative_to(dist).as_posix()
        if rel.startswith("search/"):
            continue
        p = _Page()
        p.feed(f.read_text(encoding="utf-8"))
        parts = rel.split("/")
        book = book_index.get(parts[1], -1) if parts[0] == "books" and len(parts) > 2 else -1
        pi = len(pages)
        pages.append([rel, " ".join("".join(p.title).split()), book])
        for kind, frag, text, word in p.units:
            w = words("".join(word))
            if not w:
                continue
            di = len(docs)
            if kind not in kinds:
                kinds.append(kind)
            docs.append([pi, frag, kinds.index(kind)])
            texts.append(" ".join("".join(text).split()))
            for x in set(w):
                post.setdefault(x, []).append(di)
    shards = {}
    for x in sorted(post):
        ids, last, delta = post[x], 0, []
        for i in ids:
            delta.append(i - last)
            last = i
        shards.setdefault(x[0], {})[x] = delta
    out.mkdir(parents=True, exist_ok=True)
    dump = lambda rel, v: _write(out / rel, json.dumps(v, ensure_ascii=False, separators=(",", ":")))
    dump("pages.json", {"v": 1, "books": books, "pages": pages})
    dump("docs.json", {"v": 1, "kinds": kinds, "docs": docs, "chunk": CHUNK})
    for c, words_ in sorted(shards.items()):
        dump(f"p/{c}.json", words_)
    for n in range(0, len(texts), CHUNK):
        dump(f"t/{n // CHUNK}.json", texts[n:n + CHUNK])
    return len(pages), len(docs), len(post)


def _write(path, s):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    n_pages, n_docs, n_words = build(sys.argv[1])
    print(f"search index: {n_pages} pages, {n_docs} units, {n_words} words")
