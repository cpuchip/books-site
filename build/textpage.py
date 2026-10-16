"""textpage.py: a chapter's text_html, written again from an allowlist. books-site, MIT.

KEEP what the census at pd-books 3ed7925 holds, DROP three known inert attributes, REJECT anything else: a rejected
chapter gets no page and is named with its reasons (docs/BLUEPRINT.md, "The chapter text pages"). Nothing unknown
is stripped and the rest shipped.
"""
import html
import re
from html.parser import HTMLParser

TAGS = {"a", "blockquote", "br", "caption", "div", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5",
        "hr", "img", "li", "ol", "p", "section", "span", "strong", "sup", "table", "tbody", "td", "th", "thead",
        "tr", "ul"}
VOID = {"br", "hr", "img"}
DROP = {"role", "data-label", "data-latex-placement"}
# the only classes kept: those site.js, browsercheck and site.css read in a chapter's text; any other token is dropped
# (a book's own class could otherwise take a site rule, e.g. graph-canvas clips, tx typesets $...$)
KEEP_CLASSES = {"math", "inline", "display", "smallcaps", "center", "footnotes", "footnote-ref", "footnote-back",
                # a worked illustration's layout as an HTML table (Boyden's sums, divisions and roots): the table, and
                # one rule on one side of a cell, which a KaTeX array cannot draw (agreed with the data owner, #7968)
                "tex", "rule-t", "rule-b", "rule-l", "rule-r"}
# every id from the book is written with this prefix, ids and links alike, so none can be one the page uses
ID_PREFIX = "c-"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:*-]*\Z")
# the only styles the census found; text-align becomes a class (ta-left ...), a width is dropped, so no style attribute
# ships (the oracle refuses any, as markup that could hide text) and site.css keeps every image inside the page
ALIGN = re.compile(r"\s*text-align:\s*(left|center|right|justify)\s*;?\s*\Z")
# a style of sizes only (width, height; one or more declarations): dropped
WIDTH = re.compile(r"(?:\s*(?:width|height):\s*\d+(?:\.\d+)?(?:%|in|cm|mm|em|px|pt)\s*(?:;|\Z))+\s*\Z")
SPAN = re.compile(r"[1-9][0-9]?\Z")
# a book transcribed from a scan marks where each printed page starts (span.pagenum) and where each figure stands
# (figure.scan-figure, or span.scan-figure inside a paragraph), as empty elements with data-page (and the
# transcriber's data-description of the figure). The page writes them again as links to that page of the scan, in
# a .scanmark element: furniture, whose words are not the book's (textpage.blocks and the oracle leave them out).
MARKS = {"pagenum", "scan-figure"}
MARK_ATTRS = {"data-page", "data-description", "data-continued"}


def scanmark(tag, attrs, scans):
    """(the element's opening tag and the words the site writes in it, reasons): a marker of text_html written
    again, or reasons when it is not one (an unknown attribute, a page with no scan)."""
    a = dict((k, v or "") for k, v in attrs)
    cls = [c for c in a.get("class", "").split() if c in MARKS]
    why = [f"attribute {k}= on a {cls[0]} marker" for k in a if k not in MARK_ATTRS | {"class"}]
    page = a.get("data-page", "")
    url = scans.get(page)
    if not url:
        why.append(f"a {cls[0]} marker for page {page!r}, which has no scan")
        return "", why
    href = html.escape(url, quote=True)
    if cls[0] == "pagenum":
        if tag != "span":
            why.append(f"a pagenum marker on <{tag}>")
        label = f"p. {html.escape(page)}" + (", continued" if a.get("data-continued") == "true" else "")
        return f'<span class="scanmark pagenum"><a href="{href}">{label}</a>', why
    # the description's formulas are $...$ (as excerpts' are), typeset by site.js in a .tx span
    desc = html.escape(a.get("data-description", ""), quote=False)
    desc = f'<span class="tx">{desc}</span>' if desc else ""
    link = f'<a href="{href}">Figure on p. {html.escape(page)} of the scan</a>'
    if tag == "figure":
        return (f'<figure class="scanmark scan-figure">{link}'
                + (f"<figcaption>Described by the transcriber: {desc}</figcaption>" if desc else ""), why)
    if tag == "span":
        return f'<span class="scanmark scan-figure">[{link}' + (f": {desc}]" if desc else "]"), why
    why.append(f"a scan-figure marker on <{tag}>")
    return "", why


class _Parse(HTMLParser):
    """Events in order, or reasons to reject."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events, self.why, self.stack = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in TAGS:
            self.why.append(f"tag <{tag}>")
            return
        self.events.append(("start", tag, attrs))
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in TAGS and tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.why.append(f"end tag </{tag}> does not close <{self.stack[-1] if self.stack else 'nothing'}>")
            return
        self.stack.pop()
        self.events.append(("end", tag, None))

    def handle_data(self, data):
        self.events.append(("data", data, None))

    def handle_comment(self, data):
        self.why.append("a comment")

    def handle_decl(self, decl):
        self.why.append("a declaration")

    def unknown_decl(self, data):
        self.why.append("a declaration")

    def handle_pi(self, data):
        self.why.append("a processing instruction")


def ids_of(text_html):
    """Every id the chapter's HTML declares (as written), for resolving links across a book's chapters."""
    p = _Parse()
    p.feed(text_html)
    p.close()
    return [v for kind, tag, attrs in p.events if kind == "start" for k, v in attrs if k == "id" and v]


def links_of(text_html):
    """Every fragment a link of the chapter points to (without its #), as the parser reads the href."""
    p = _Parse()
    p.feed(text_html)
    p.close()
    return [v[1:] for kind, tag, attrs in p.events if kind == "start" and tag == "a"
            for k, v in attrs if k == "href" and v and v.startswith("#")]


def sanitize(text_html, book, image_ok, resolve, depth, targets=frozenset(), anchors=False, scans=None):
    """(clean HTML, images used, reasons). Reasons non-empty means: no page.

    image_ok(path) says whether the export holds images/<book>/... at that path; resolve(target) is "self", an
    href to another page, or None (unlink); depth is how many ../ reach the site root from the page; targets are the
    ids other chapters of the book link to, kept here so those links land. anchors: give every top-level element
    that has no id of its own the id b-N (N its place among the top-level elements, from 1), so an excerpt or a search
    result can link to its paragraph (docs/BLUEPRINT.md, "Finding things"). scans: the book's page_scans, for its
    page and figure markers (see scanmark); a marker in a book without them is a reason to reject."""
    p = _Parse()
    p.feed(text_html)
    p.close()
    why = list(p.why)
    if text_html.rfind("<") > text_html.rfind(">"):
        why.append("the text ends inside a tag")  # the parser drops an unfinished tag at the end without a word
    if p.stack:
        why.append(f"<{p.stack[-1]}> never closed")
    if re.search(r"gutenberg", text_html, re.I):
        why.append('"gutenberg" in the text')
    linked = {v[1:] for kind, tag, attrs in p.events if kind == "start" and tag == "a"
              for k, v in attrs if k == "href" and v and v.startswith("#")} | set(targets)
    seen = {}
    for kind, tag, attrs in p.events:
        if kind == "start":
            for k, v in attrs:
                if k == "id" and v in linked:
                    seen[v] = seen.get(v, 0) + 1
    for v, n in sorted(seen.items()):
        if n > 1:
            why.append(f"id {v!r} declared {n} times and linked")
    out, images, open_a = [], [], []
    level, place = 0, 0  # open elements written so far; top-level elements seen
    up = "../" * depth
    marking = []  # for each open element, whether it is a marker (whose own content, if any, is a reason to reject)
    for kind, tag, attrs in p.events:
        if kind == "data":
            if any(marking):
                if tag.strip():
                    why.append("text inside a page or figure marker")
                continue
            out.append(html.escape(tag, quote=False))
            continue
        if kind == "start" and any(marking):
            why.append(f"<{tag}> inside a page or figure marker")
            continue
        if kind == "start" and tag not in VOID and any(c in MARKS for k, v in attrs if k == "class"
                                                       for c in (v or "").split()):
            el, w = scanmark(tag, attrs, scans or {})
            why.extend(w)
            if level == 0:
                place += 1
            out.append(el)
            marking.append(True)
            level += 1
            continue
        if kind == "start" and tag not in VOID:
            marking.append(False)
        if kind == "end" and marking:
            marking.pop()
        if kind == "end":
            if tag == "a":
                if open_a.pop():
                    out.append("</a>")
                    level -= 1
                continue
            out.append(f"</{tag}>")
            level -= 1
            continue
        kept, keep_a, classes = [], True, []
        for k, v in attrs:
            v = v if v is not None else ""
            if k in DROP:
                continue
            if k == "class":
                classes.extend(c for c in v.split() if c in KEEP_CLASSES)
            elif k == "id":
                if v in linked:
                    if not ID.match(v):
                        why.append(f"linked id {v!r} is not a plain id")
                    kept.append((k, ID_PREFIX + v))
            elif k == "style" and ALIGN.match(v):
                classes.append("ta-" + ALIGN.match(v).group(1))
            elif k == "style" and WIDTH.match(v):
                continue
            elif k in ("colspan", "rowspan") and tag in ("td", "th") and SPAN.match(v):
                kept.append((k, v))
            elif k == "value" and tag == "li" and re.fullmatch(r"[1-9][0-9]{0,3}", v):
                kept.append((k, v))  # the book's own item number (an exercise's), since pd-books 040cb80
            elif k == "alt" and tag == "img":
                kept.append((k, v))
            elif k == "src" and tag == "img":
                prefix = f"images/{book}/"
                if (v.startswith(prefix) and ".." not in v.split("/") and not re.search(r"[%\\?#]", v)
                        and image_ok(v)):
                    kept.append((k, up + v))
                    images.append(v)
                else:
                    why.append(f"image {v!r} is not this book's or the export does not hold it")
            elif k == "href" and tag == "a":
                if not v.startswith("#"):
                    why.append(f"link {v[:40]!r} is not a fragment")
                    continue
                to = resolve(v[1:])
                if to == "self":
                    kept.append((k, "#" + ID_PREFIX + v[1:]))
                elif to:
                    kept.append((k, to))
                else:
                    keep_a = False
            else:
                why.append(f"attribute {k}={v[:40]!r} on <{tag}>")
        if classes:
            kept.insert(0, ("class", " ".join(classes)))
        if tag == "a":
            open_a.append(keep_a)
            if not keep_a:
                # the link goes, its words stay; an id on it stays too (on a span), since other links may land on it
                ids = [(k, v) for k, v in kept if k == "id"]
                if ids:
                    out.append(f'<span id="{html.escape(ids[0][1], quote=True)}"></span>')
                continue
        if level == 0 and tag not in VOID:
            place += 1
            if anchors and not any(k == "id" for k, v in kept):
                kept.append(("id", f"b-{place}"))
        a = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in kept)
        out.append(f"<{tag}{a}>")
        if tag not in VOID:
            level += 1
    return "".join(out), images, why


# elements whose edges part words (a cell, an item, a line break); inline ones (em, span, a) do not
SEPARATE = {"blockquote", "br", "caption", "div", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "hr", "img",
            "li", "ol", "p", "section", "table", "tbody", "td", "th", "thead", "tr", "ul"}
BLOCK_ID = re.compile(r"b-[1-9][0-9]*\Z")
WORD = re.compile(r"[a-z0-9]+")


def words(s):
    """The words an excerpt, a block or a query is compared by: lowercased runs of a-z and 0-9."""
    return WORD.findall(s.lower())


def blocks(clean):
    """[(id, words, text)] for each top-level element of sanitized HTML that has an id, in order. words leave math
    out; text is what a reader sees, with each formula as its LaTeX source between its delimiters."""
    p = _Parse()
    p.feed(clean)
    p.close()
    out, level, cur, in_math, in_mark = [], 0, None, 0, 0  # a .scanmark's words are the site's, not the book's
    for kind, tag, attrs in p.events:
        if kind != "data" and cur is not None and tag in SEPARATE:
            cur[1].append(" ")
            cur[2].append(" ")
        if kind == "start":
            a = dict(attrs)
            if level == 0:
                cur = [a.get("id"), [], []] if tag not in VOID else None
                if cur is not None:
                    out.append(cur)
            if in_math or (tag == "span" and "math" in (a.get("class") or "").split()):
                in_math += 1 if tag not in VOID else 0
            if in_mark or "scanmark" in (a.get("class") or "").split():
                in_mark += 1 if tag not in VOID else 0
            if tag not in VOID:
                level += 1
        elif kind == "end":
            level -= 1
            if in_math:
                in_math -= 1
            if in_mark:
                in_mark -= 1
        elif in_mark:
            continue
        elif cur is not None and level > 0:
            cur[2].append(tag)
            if not in_math:
                cur[1].append(tag)
    return [(i, words("".join(w)), " ".join("".join(x).split())) for i, w, x in out if i]
