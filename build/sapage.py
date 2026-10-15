"""sapage.py: the share-alike books (cpuchip/sa-books), page by page, with the credits on every page. books-site, MIT.

sa-books has no export; the site reads each book's transcription, one Markdown file per source page, and renders
the subset the census at sa-books d9cc208 found (docs/BLUEPRINT.md, "The share-alike books"). Anything outside
that subset refuses the build: a share-alike work goes up whole or not at all. The HTML then goes through
textpage.sanitize, the allowlist the chapter text pages use.
"""
import html
import json
import re
from pathlib import Path

import textpage

SA_BOOKS = "https://github.com/cpuchip/sa-books"
# the author's own words for an excerpt (http://www.cbphysics.org/howtoAttribute.html, read 2026-10-15); the oracle
# holds its own copy
EXCERPT_LINE = "online textbook Calculus-Based Physics by Jeffrey Schnick."
PAGE = re.compile(r"p(\d{3})\.md\Z")
FIG = re.compile(r"fig/(p\d{3}-(?:t?\d+)\.png)\Z")
RAW_TAG = re.compile(r"<(?:/?(?:table|tr|td|th|thead|tbody)|br\s*/?|img\s+src=\"(fig/[^\"]+)\"\s*/?)>")
ENTITY = re.compile(r"&(?:[a-z]+|#\d+|#x[0-9a-fA-F]+);")


class Refused(Exception):
    pass


def e(x):
    return html.escape(str(x), quote=True)


def load_book(root, slug):
    """book.json, refused when a credit the pages need is missing."""
    b = json.loads((root / "books" / slug / "book.json").read_text(encoding="utf-8"))
    need = [("author",), ("licence", "url"), ("licence", "statement"), ("attribution", "title_as_modified"),
            ("attribution", "credit"), ("transcription", "documents")]
    for path in need:
        v = b
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        if not v:
            raise Refused(f"{slug}/book.json has no {'.'.join(path)}")
    return b


def front_matter(text, where):
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise Refused(f"{where}: no front matter")
    head, body = text[4:].split("\n---\n", 1)
    meta = {}
    for line in head.split("\n"):
        k, sep, v = line.partition(": ")
        if not sep:
            raise Refused(f"{where}: front matter line {line[:40]!r}")
        meta[k] = v
    for k in ("source", "credit"):
        if not meta.get(k):
            raise Refused(f"{where}: front matter has no {k}")
    return meta, body


def take_math(body, where):
    """The body with each formula replaced by \\x00N\\x00, and the formulas [(display, tex)] in order.
    Delimiters: $$..$$ and \\[..\\] display, \\(..\\) and $..$ inline; a backslash-escaped $ is text."""
    out, math, i, n = [], [], 0, len(body)
    while i < n:
        c = body[i]
        if c == "\\" and i + 1 < n and body[i + 1] in "([":
            close = "\\)" if body[i + 1] == "(" else "\\]"
            j = body.find(close, i + 2)
            if j < 0:
                raise Refused(f"{where}: {body[i:i + 2]} never closed")
            math.append((body[i + 1] == "[", body[i + 2:j]))
            out.append(f"\x00{len(math) - 1}\x00")
            i = j + 2
        elif c == "\\" and i + 1 < n:
            out.append(body[i:i + 2])  # an escape: kept for the inline pass
            i += 2
        elif c == "$":
            display = body.startswith("$$", i)
            k = 2 if display else 1
            j = i + k
            while True:
                j = body.find("$$" if display else "$", j)
                if j < 0:
                    raise Refused(f"{where}: a $ never closed")
                if body[j - 1] != "\\":
                    break
                j += 1
            tex = body[i + k:j]
            if not display and ("\n\n" in tex or not tex.strip()):
                raise Refused(f"{where}: inline math across a blank line or empty")
            math.append((display, tex))
            out.append(f"\x00{len(math) - 1}\x00")
            i = j + k
        else:
            out.append(c)
            i += 1
    return "".join(out), math


def math_html(display, tex):
    if display:
        return f'<span class="math display">\\[{html.escape(tex, quote=False)}\\]</span>'
    return f'<span class="math inline">\\({html.escape(tex, quote=False)}\\)</span>'


def inline(s, math, fig_src, where):
    """One block's text: escapes, entities, the raw tags the census found, images, **bold**, *italic*, _italic_."""
    keep = []

    def hold(h):
        keep.append(h)
        return f"\x01{len(keep) - 1}\x01"

    s = re.sub(r"\x00(\d+)\x00", lambda m: hold(math_html(*math[int(m.group(1))])), s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: hold(f'<img src="{e(fig_src(m.group(2)))}" alt="{e(m.group(1))}">'), s)
    s = RAW_TAG.sub(lambda m: hold(f'<img src="{e(fig_src(m.group(1)))}" alt="">' if m.group(1)
                                   else ("<br>" if m.group(0).startswith("<br") else m.group(0))), s)
    s = ENTITY.sub(lambda m: hold(m.group(0)), s)
    s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|$<>])", lambda m: hold(html.escape(m.group(1), quote=False)), s)
    if "<" in s.replace("\x01", "") and re.search(r"<[A-Za-z/!]", s):
        raise Refused(f"{where}: markup outside the subset: {s[s.find('<'):s.find('<') + 40]!r}")
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?=\S)([^*]+?)(?<=\S)\*(?![*\w])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w])_(?=\S)([^_]+?)(?<=\S)_(?![\w])", r"<em>\1</em>", s)
    # a star or underscore with no partner stays text (the book's footnote star); the oracle compares symbols too
    while "\x01" in s:
        s = re.sub(r"\x01(\d+)\x01", lambda m: keep[int(m.group(1))], s)
    return s


def render_body(body, fig_src, where):
    """Markdown subset -> HTML. Blocks: headings (one level down: the page has its own h1), pipe tables, raw
    <table> lines, '- ' lists, numbered lines kept as text, paragraphs."""
    text, math = take_math(body, where)
    lines = text.split("\n")
    out, i = [], 0
    para = []

    def flush():
        if para:
            out.append("<p>" + inline("\n".join(para), math, fig_src, where) + "</p>")
            para.clear()
    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if not st:
            flush()
            i += 1
            continue
        m = re.match(r"(#{1,6}) +(.*)", st)
        if m:
            flush()
            lv = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lv}>{inline(m.group(2).rstrip(), math, fig_src, where)}</h{lv}>")
            i += 1
            continue
        if st.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            out.append(pipe_table(rows, math, fig_src, where))
            continue
        if st.startswith("<table"):
            flush()
            block = []
            while i < len(lines):
                block.append(lines[i])
                i += 1
                if "</table>" in block[-1]:
                    break
            out.append(inline("\n".join(block), math, fig_src, where))
            continue
        if re.match(r"[-*+] ", st):
            flush()
            items = []
            while i < len(lines) and lines[i].strip():
                s2 = lines[i].strip()
                if re.match(r"[-*+] ", s2):
                    items.append(s2[2:])
                elif items:
                    items[-1] += "\n" + s2
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(t, math, fig_src, where)}</li>" for t in items) + "</ul>")
            continue
        if re.match(r"\d+[.)] ", st):
            flush()  # a numbered line is the page's own numbering: its own paragraph, the number kept as text
            para.append(st)
            flush()
            i += 1
            continue
        para.append(line)
        i += 1
    flush()
    return "\n".join(out)


def pipe_table(rows, math, fig_src, where):
    def cells(r):
        r = r.strip()
        if not (r.startswith("|") and r.endswith("|")):
            raise Refused(f"{where}: table row {r[:40]!r}")
        return [c.strip() for c in r[1:-1].split("|")]
    if len(rows) < 2 or not all(re.fullmatch(r":?-{3,}:?", c) for c in cells(rows[1])):
        raise Refused(f"{where}: a table without its separator row")
    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    if any(len(r) != len(head) for r in body):
        raise Refused(f"{where}: a table row with the wrong number of cells")
    th = "".join(f"<th>{inline(c, math, fig_src, where)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{inline(c, math, fig_src, where)}</td>" for c in r) + "</tr>" for r in body)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def pages_of(root, slug, book):
    """[(doc, pNNN, meta, body)] in document order, then page order."""
    out = []
    tdir = root / "books" / slug / "transcription"
    for doc in book["transcription"]["documents"]:
        files = sorted(f for f in (tdir / doc).iterdir() if PAGE.match(f.name))
        if not files:
            raise Refused(f"{slug}/{doc}: no pages")
        for f in files:
            where = f"{slug}/{doc}/{f.name}"
            meta, body = front_matter(f.read_text(encoding="utf-8"), where)
            if meta["credit"] != credit_line(book):
                raise Refused(f"{where}: its credit differs from book.json's")
            out.append((doc, f.stem, meta, body))
    return out


def credit_line(book):
    return f"{book['attribution']['title_as_modified']}. {book['attribution']['credit']}"


def link_urls(s):
    """Text with each bare http(s) URL in parentheses made a link (the credit's source and licence URIs)."""
    parts = re.split(r"(https?://[^\s)]+)", s)
    return "".join(f'<a href="{e(p)}">{e(p)}</a>' if i % 2 else e(p) for i, p in enumerate(parts))


def credit_block(book):
    a, lic = book["attribution"], book["licence"]
    return (f'<section class="credit"><h2>Credits</h2>'
            f'<p data-credit="title">{e(a["title_as_modified"])}.</p>'
            f'<p data-credit="excerpt">From the {e(EXCERPT_LINE)}</p>'
            f'<p data-credit="statement">{e(lic["statement"])}</p>'
            f'<p data-credit="credit">{link_urls(a["credit"])}</p>'
            f'<p data-credit="licence">This page is licensed under <a href="{e(lic["url"])}">{e(lic["name"])}</a>; '
            f'the transcription is in <a href="{SA_BOOKS}">sa-books</a>.</p></section>')


def build_pages(root, slug, pin, page):
    """{site path: html}, {site path: source file} for the figures, (title, author, pages) for the shelf.
    page is site.py's page shell (title, body, depth, math=, licence=)."""
    book = load_book(root, slug)
    pages = pages_of(root, slug, book)
    docs = book["transcription"]["documents"]
    tdir = root / "books" / slug / "transcription"
    files, figs = {}, {}
    by_doc = {}
    for doc, p, meta, body in pages:
        by_doc.setdefault(doc, []).append(p)
    lic = book["licence"]
    footer = (f'This page is from {e(book["attribution"]["title_as_modified"])}, licensed under '
              f'<a href="{e(lic["url"])}">{e(lic["name"])}</a>.')
    for doc, p, meta, body in pages:
        where = f"{slug}/{doc}/{p}.md"

        def fig_src(src, doc=doc, where=where):
            m = FIG.match(src)
            if not m or not (tdir / doc / "fig" / m.group(1)).is_file():
                raise Refused(f"{where}: figure {src!r} is not in sa-books")
            return f"images/{slug}/{doc}/fig/{m.group(1)}"
        raw = render_body(body, fig_src, where)
        image_ok = lambda rel, doc=doc: (rel.startswith(f"images/{slug}/{doc}/fig/")
                                        and (tdir / doc / "fig" / rel.rsplit("/", 1)[1]).is_file())
        clean, images, why = textpage.sanitize(raw, slug, image_ok, lambda t: None, 4)
        if why:
            raise Refused(f"{where}: " + "; ".join(why))
        for rel in images:
            figs[rel] = tdir / doc / "fig" / rel.rsplit("/", 1)[1]
        seq = by_doc[doc]
        k = seq.index(p)
        nav = '<nav class="pager">' + (
            f'<a href="../{seq[k - 1]}/index.html" rel="prev">Previous page</a> ' if k else "") + (
            f'<a href="../{seq[k + 1]}/index.html" rel="next">Next page</a>' if k + 1 < len(seq) else "") + "</nav>"
        n = int(p[1:])
        title = f"Page {n} of {docs[doc]['title']}"
        reading = f'<p class="n">Read from {e(meta["source"])}. {e(meta.get("reading", ""))}</p>'
        body_html = f"""<p class="crumb"><a href="../../index.html">{e(book['attribution']['title_as_modified'])}</a> /
<a href="../../index.html#{e(doc)}">{e(docs[doc]['title'])}</a></p>
<h1>{e(title)}</h1>
{nav}
<article class="text" data-kind="sa-page" data-id="{e(slug)}/{e(doc)}/{e(p)}" data-field="body">{clean}</article>
{reading}
{credit_block(book)}
{nav}"""
        files[f"books/{slug}/{doc}/{p}/index.html"] = page(f"{title}: {book['title']}", body_html, 4, math={}, licence=footer)
    files[f"books/{slug}/index.html"] = page(book["attribution"]["title_as_modified"],
                                             render_book_page(book, slug, pin, by_doc), 2, licence=footer)
    return files, figs, (book, len(pages))


def render_book_page(book, slug, pin, by_doc):
    docs = book["transcription"]["documents"]
    src = {s["file"]: s for s in book.get("sources") or []}
    tree = f"{SA_BOOKS}/tree/{pin}/books/{slug}"
    lists = ""
    for doc, ps in by_doc.items():
        d = docs[doc]
        s = src.get(d.get("source"))
        orig = f' Original: <a href="{e(s["url"])}">{e(s["file"])}</a>.' if s else ""
        links = " ".join(f'<a href="{e(doc)}/{e(p)}/index.html">{int(p[1:])}</a>' for p in ps)
        lists += (f'<section id="{e(doc)}"><h3>{e(d["title"])}</h3><p class="n">{len(ps)} pages.{orig}</p><p class="pages">{links}</p></section>')
    return f"""<article class="book" data-kind="sa-book" data-id="{e(slug)}">
<h1>{e(book['attribution']['title_as_modified'])}</h1>
<p class="by">{e(book['author'])}{', ' + e(book['affiliation']) if book.get('affiliation') else ''}, {e(str(book.get('year', '')))}</p>
{credit_block(book)}
<section id="changes"><h2>What we changed</h2>
<p>We transcribed the author's PDFs and his .doc file page by page, cut the figures from the page images, and
proofread some pages against them. Each page says which file and page it was read from and how it was read. The
evidence for how the transcription was made, and what it is known to miss, is in
<a href="{e(tree)}/evidence">sa-books</a>.</p></section>
<section id="documents"><h2>The pages</h2>{lists}</section>
</article>"""
