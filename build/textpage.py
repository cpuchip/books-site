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
KEEP_CLASSES = {"math", "inline", "display", "smallcaps", "center", "footnotes", "footnote-ref", "footnote-back"}
# every id from the book is written with this prefix, ids and links alike, so none can be one the page uses
ID_PREFIX = "c-"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:*-]*\Z")
# the only styles the census found; text-align becomes a class (ta-left ...), a width is dropped, so no style attribute
# ships (the oracle refuses any, as markup that could hide text) and site.css keeps every image inside the page
ALIGN = re.compile(r"\s*text-align:\s*(left|center|right|justify)\s*;?\s*\Z")
# a style of sizes only (width, height; one or more declarations): dropped
WIDTH = re.compile(r"(?:\s*(?:width|height):\s*\d+(?:\.\d+)?(?:%|in|cm|mm|em|px|pt)\s*(?:;|\Z))+\s*\Z")
SPAN = re.compile(r"[1-9][0-9]?\Z")


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


def sanitize(text_html, book, image_ok, resolve, depth, targets=frozenset()):
    """(clean HTML, images used, reasons). Reasons non-empty means: no page.

    image_ok(path) says whether the export holds images/<book>/... at that path; resolve(target) is "self", an
    href to another page, or None (unlink); depth is how many ../ reach the site root from the page; targets are the
    ids other chapters of the book link to, kept here so those links land."""
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
    up = "../" * depth
    for kind, tag, attrs in p.events:
        if kind == "data":
            out.append(html.escape(tag, quote=False))
            continue
        if kind == "end":
            if tag == "a":
                if open_a.pop():
                    out.append("</a>")
                continue
            out.append(f"</{tag}>")
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
        a = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in kept)
        out.append(f"<{tag}{a}>")
    return "".join(out), images, why
