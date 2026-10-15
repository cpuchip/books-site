"""site.py: build books.cpuchip.net from a pd-books export. Standard library only.

    python3 build/site.py --export PD_BOOKS/export --out dist [--pin COMMIT] [--no-checks]

Refuses (exit 1, nothing written to --out) when pd-books' own check_only.py fails on the export, when the
schema is one this build does not know, or when books.json and export/books/ disagree. --no-checks skips
pd-books' check only; the oracle's export control uses it because its planted export is built by us.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import neutral  # noqa: E402
import sapage  # noqa: E402
import search  # noqa: E402
import textpage  # noqa: E402

HERE = Path(__file__).resolve().parent
SCHEMAS = {1}
PD_BOOKS = "https://github.com/cpuchip/pd-books"
LEARN = "https://learn.cpuchip.net/"
CONCEPT_LAYER = ["book", "person", "chapter", "concept", "method", "theorem", "law", "quantity", "unit",
                 "instrument", "experiment"]
TERM_GROUPS = [("concept", "Concepts"), ("theorem", "Theorems"), ("method", "Methods"), ("law", "Laws"),
               ("quantity", "Quantities"), ("unit", "Units"), ("instrument", "Instruments"),
               ("experiment", "Experiments"), ("person", "People")]
VERDICTS = {
    "verified": "the printed answer passed a computed check",
    "unverified": "no computed check settled this one (yet)",
}
CHECK_WORDS = {
    "PASS": "passes", "PASS-INTERPRETED": "passes, with the problem read into an equation",
    "FLAG-MISMATCH": "the printed answer does not match the problem",
    "FLAG-MISSING": "no printed answer to check", "FLAG-EXTRACTION": "the record may be misread",
    "FLAG-TASK": "the check does not fit this problem", "UNJUDGED-OTHER": "not a kind the checker handles",
}

def e(x):
    """Escape for HTML; a value that is not a string (the export has dict and list answer_expr) shows as JSON."""
    return html.escape(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))


def refuse(msg):
    print(f"REFUSED: {msg}")
    sys.exit(1)


def load(export, pd_books_check):
    export = Path(export)
    if pd_books_check:
        tool = export.parent / "tools" / "check_only.py"
        if not tool.exists():
            refuse(f"no {tool}: the build runs pd-books' own export check")
        r = subprocess.run([sys.executable, "-I", str(tool), str(export)], capture_output=True, text=True)
        if r.returncode != 0:
            refuse("pd-books check_only.py:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    index = json.loads((export / "books.json").read_text(encoding="utf-8"))
    graph = json.loads((export / "graph.json").read_text(encoding="utf-8"))
    for name, d in (("books.json", index), ("graph.json", graph)):
        if d.get("schema_version") not in SCHEMAS:
            refuse(f"{name} schema_version {d.get('schema_version')!r}; this build knows {sorted(SCHEMAS)}")
    listed = [b["id"] for b in index["books"]]
    files = sorted(p.stem for p in (export / "books").glob("*.json"))
    if sorted(listed) != files:
        refuse(f"books.json lists {listed}, export/books/ holds {files}")
    books = []
    for b in listed:
        d = json.loads((export / "books" / f"{b}.json").read_text(encoding="utf-8"))
        if d.get("schema_version") not in SCHEMAS:
            refuse(f"{b}.json schema_version {d.get('schema_version')!r}")
        books.append(d)
    return index, books, graph


MATH_CSS = ["vendor/katex/katex.min.css"]
MATH_JS = ["vendor/katex/katex.min.js", "vendor/katex/contrib/auto-render.min.js", "site.js"]
CHEM_JS = "vendor/katex/contrib/mhchem.min.js"  # KaTeX's \ce and \pu (Apache-2.0); only on pages that use them


def page(title, body, depth, desc="", math=None, scripts=(), licence=None, styles=()):
    """math: None for a page without math, else the book's macros (a dict) for KaTeX. licence: the footer's
    sentence for a page that shows a share-alike book (sapage.py), in place of the public-domain data line."""
    up = "../" * depth
    css = "".join(f'\n<link rel="stylesheet" href="{up}{c}">' for c in (MATH_CSS if math is not None else list(styles)))
    mjs = MATH_JS if math is not None else []
    if mjs and ("\\ce{" in body or "\\pu{" in body):
        mjs = mjs[:1] + [CHEM_JS] + mjs[1:]  # after katex.min.js, which it extends
    js = "".join(f'\n<script src="{up}{j}"></script>' for j in mjs + list(scripts))
    main_attrs = f" data-macros=\"{e(json.dumps(math, ensure_ascii=False, sort_keys=True))}\"" if math else ""
    report = ('\n<p class="n">Math: <output id="math-report">not typeset (scripts are off)</output></p>'
              if math is not None else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{up}site.css">{css}
</head>
<body>
<header class="top"><a class="brand" href="{up}index.html">Math and physics books</a>
<nav><a href="{up}search/index.html">Search</a> <a href="{up}graph/index.html">Concept graph</a> <a href="{up}about/index.html">About</a></nav></header>
<main{main_attrs}>
{body}
</main>
<footer class="foot"><p>{licence or f'Book data from <a href="{PD_BOOKS}">pd-books</a> (CC0). Lessons that use these books:\n<a href="{LEARN}">learn.cpuchip.net</a>.'} Site code MIT; the libraries it uses are listed in
<a href="{up}vendor/THIRD-PARTY-NOTICES.txt">their notices</a>.</p>{report}</footer>{js}
</body>
</html>
"""


def field(name, s):
    """data-field marks a value the oracle compares exactly with the export's (only a non-empty string is one)."""
    return f' data-field="{name}"' if isinstance(s, str) and s.strip() else ""


def text(s, name=None):
    """Export markdown is shown as text (LaTeX source kept) until the math renderer lands."""
    return f'<span class="tx"{field(name, s) if name else ""}>{e(s or "")}</span>'


def chapter_slug(book_id, chapter_id):
    return chapter_id[len(book_id) + 1:]


def scan_links(evidence):
    out = []
    for m in re.finditer(r"Internet Archive scan ([A-Za-z0-9_.-]+[A-Za-z0-9_])", evidence or ""):
        url = f"https://archive.org/details/{m.group(1)}"
        if url not in out:
            out.append(url)
    return out


def render_problem(p):
    answers = "".join(f"<li>{text(a, 'answer')}</li>" for a in p.get("answer_markdown") or []) or "<li>(none printed)</li>"
    checks = "".join(
        f"<li><code>{e(c['task'])}</code>: {e(CHECK_WORDS.get(c['verdict'], c['verdict']))}"
        + (f" <code>{e(c['answer_expr'])}</code>" if c.get("answer_expr") else "") + "</li>"
        for c in p.get("checks") or [])
    keys = ""
    for k in p.get("keys") or []:
        pins = k.get("core_pins") or {}
        keys += (f'<div class="keys"><p>On the STU-32 ({e(k.get("mode", ""))}, {e(k.get("entry", ""))}):</p>'
                 + "".join(f"<pre{field('step', s)}>{e(s)}</pre>" for s in k.get("steps") or [])
                 + f'<p>Calculator: <code>{e(k.get("calculator_value", ""))}</code>; the book prints '
                 f'<code>{e(k.get("printed_value", ""))}</code>. Run on the calculator core at firmware '
                 f'<code>{e(str(pins.get("firmware", ""))[:7])}</code>.</p></div>')
    verdict = p.get("verdict") or ""
    return (f'<li class="problem" data-kind="problem" data-id="{e(p["id"])}" id="p-{e(p["id"].split("/", 1)[-1].replace("/", "-"))}">'
            f'<p class="loc">{e(p.get("location") or "")}{", p. " + e(str(p["page"])) if p.get("page") else ""}</p>'
            + (f'<p>{text(p.get("markdown"), "text")}</p>' if (p.get("markdown") or "").strip()
               else '<p class="n">The record holds no text for this problem.</p>')
            + f'<div class="ans"><span>Printed answer:</span><ul>{answers}</ul></div>'
            f'<p class="verdict v-{e(verdict)}">{e(verdict)}: {e(VERDICTS.get(verdict, ""))}</p>'
            + (f'<details><summary>How it was checked</summary><ul>{checks}</ul></details>' if checks else "")
            + keys + "</li>")


def render_erratum(x):
    scans = scan_links(x.get("evidence"))
    ev = neutral.evidence(x.get("evidence") or "")
    return (f'<li class="erratum" data-kind="erratum" data-id="{e(x["id"])}">'
            f'<p class="loc">{e(x["id"].split("/")[-1])}: {e(x.get("location") or "")}'
            f'{", p. " + e(str(x["page"])) if x.get("page") else ""}</p>'
            f'<p>Printed: {text(x.get("printed"), "printed")}<br>Corrected: {text(x.get("corrected"), "corrected")}</p>'
            + (f'<p class="ctx">In the source: <code{field("context", x["context"])}>{e(x["context"])}</code></p>'
               if x.get("context") else "")
            + (f'<p class="n">{e(x["class"])}</p>' if x.get("class") else "")
            + f'<p class="credit">{e(neutral.credit(x.get("status"), x.get("kind")))}</p>'
            + (f'<p class="ev">{e(ev)}</p>' if ev else "")
            + "".join(f'<p>Scan: <a href="{e(u)}">{e(u)}</a></p>' for u in scans)
            + "</li>")


def term_anchor(node_id):
    return "t-" + node_id.replace("/", "-")


def terms_of(graph, books):
    """{book: {node: [chapter ids]}} from the graph's taught_in links to chapters that are part_of a book.
    Refuses an export whose graph places a chapter in another book than the book file does, or whose taught_in
    starts at a node that is not a term type."""
    kind = {n["id"]: n["type"] for n in graph["nodes"]}
    book_of = {l["source"]: l["target"] for l in graph["links"]
               if l["type"] == "part_of" and kind.get(l["source"]) == "chapter"}
    files = {c["id"]: d["book"]["id"] for d in books for c in d["chapters"]}
    for c, b in book_of.items():
        if c in files and files[c] != b:
            refuse(f"graph.json says {c} is part_of {b}; its book file is {files[c]}")
    types = {t for t, _ in TERM_GROUPS}
    out = {}
    for l in graph["links"]:
        if l["type"] == "taught_in" and kind.get(l["source"]) not in types:
            refuse(f"graph.json: {l['source']} ({kind.get(l['source'])}) is taught_in {l['target']}; "
                   f"terms are {sorted(types)}")
        if l["type"] == "taught_in" and l["target"] in book_of:
            chs = out.setdefault(book_of[l["target"]], {}).setdefault(l["source"], [])
            if l["target"] not in chs:
                chs.append(l["target"])
    for b, terms in out.items():
        anchors = [term_anchor(n) for n in terms]
        if len(set(anchors)) != len(anchors):
            refuse(f"two terms of {b} share an anchor")
    return out


def check_relations(relations, titles):
    seen = set()
    for r in relations:
        pair = tuple(sorted(r.get("books") or []))
        if len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= set(titles):
            refuse(f"books.json relation {r.get('books')} does not name two books of the shelf")
        if pair in seen:
            refuse(f"books.json relates {pair[0]} and {pair[1]} twice")
        seen.add(pair)


def render_relations(d, relations, names, titles, terms):
    bid = d["book"]["id"]
    mine = sorted(((r, next(o for o in r["books"] if o != bid)) for r in relations if bid in r["books"]),
                  key=lambda ro: (-len(ro[0].get("shared_concepts") or []), titles[ro[1]]["title"]))
    items = ""
    for r, o in mine:
        shared = r.get("shared_concepts") or []
        names_html = ", ".join(
            (f'<a href="terms/index.html#{e(term_anchor(n))}">{e(names.get(n) or n)}</a>' if n in terms
             else f'<span>{e(names.get(n) or n)}</span>') for n in shared)
        t = titles[o]
        items += (f'<li class="relation" data-kind="relation" data-id="{e(bid)}~{e(o)}">'
                  f'<a href="../{e(o)}/index.html">{e(t["title"])}</a> <span class="by">{e(str(t.get("year", "")))}</span>'
                  + (f'<details><summary><span data-count="shared">{len(shared)}</span> shared '
                     f'{"term" if len(shared) == 1 else "terms"}</summary><p class="shared">{names_html}</p></details>'
                     if shared else f'<p class="n"><span data-count="shared">0</span> shared terms recorded.</p>')
                  + "</li>")
    return (f'<section><h2>Related books</h2><p class="n">The books the concept graph relates to this one, most shared '
            f'terms first.</p><ul class="relations">{items}</ul></section>' if items
            else '<section><h2>Related books</h2><p>None on this shelf yet.</p></section>')


def render_terms(d, terms, names, kinds, teaching, titles):
    b = d["book"]
    bid = b["id"]
    order = {c["id"]: k for k, c in enumerate(d["chapters"])}
    chapter = {c["id"]: c for c in d["chapters"]}
    groups, jump = "", []
    for t, heading in TERM_GROUPS:
        ids = sorted((n for n in terms if kinds.get(n) == t), key=lambda n: ((names.get(n) or n).casefold(), n))
        if not ids:
            continue
        rows = ""
        for n in ids:
            chs = sorted(terms[n], key=lambda c: order.get(c, len(order)))
            where = ", ".join(
                f'<a href="../ch/{e(chapter_slug(bid, c))}/index.html">'
                f'{e((chapter.get(c) or {}).get("title") or (chapter.get(c) or {}).get("number") or chapter_slug(bid, c))}</a>'
                for c in chs)
            others = sorted(teaching.get(n, set()) - {bid}, key=lambda o: titles[o]["title"])
            also = ", ".join(f'<a href="../../{e(o)}/terms/index.html#{e(term_anchor(n))}">{e(titles[o]["title"])}</a>'
                             for o in others)
            rows += (f'<li class="term" data-kind="term" data-id="{e(bid)}|{e(n)}" id="{e(term_anchor(n))}">'
                     f'<span class="tn">{e(names.get(n) or n)}</span>'
                     f'<p class="n">Taught in: {where}</p>'
                     + (f'<p class="n">Also in: {also}</p>' if also else "") + "</li>")
        groups += (f'<section data-group="{e(t)}" id="g-{e(t)}"><h2>{e(heading)} '
                   f'(<span data-count="group">{len(ids)}</span>)</h2><ul class="terms">{rows}</ul>'
                   f'<p class="n"><a href="#top">Back to the top</a></p></section>')
        jump.append(f'<a href="#g-{e(t)}">{e(heading)}</a>')
    body = f"""<p class="crumb"><a href="../index.html">{e(b['title'])}</a></p>
<h1 id="top">Index of terms</h1>
<p class="lede">Every concept, theorem, method and person the concept graph places in a chapter of this book,
with the chapters that teach it and the other books on the shelf that teach it too.</p>
{'<nav class="jump" aria-label="Term groups">' + ' '.join(jump) + '</nav>' if jump else ''}
{groups or '<p>The graph places no terms in this book yet.</p>'}"""
    return page(f"Index of terms: {b['title']}", body, 3, f"The terms taught in {b['title']}, by chapter")


def render_book(d, index_entry, pin, generated, related="", n_terms=0):
    b = d["book"]
    bid = b["id"]
    t = b.get("transcription") or {}
    chapters = "".join(
        f'<li data-kind="chapter" data-id="{e(c["id"])}"><a href="ch/{e(chapter_slug(bid, c["id"]))}/index.html">'
        f'{e(c.get("title") or c.get("number") or "")}</a>'
        f' <span class="n">{len(c["excerpts"])} excerpts, {len(c["equations"])} equations, '
        f'{sum(1 for p in d["problems"] if p.get("set") in set(c["exercise_sets"]))} problems</span></li>'
        for c in d["chapters"])
    errata = "".join(render_erratum(x) for x in d.get("errata") or [])
    listed_x = {i for c in d["chapters"] for i in c["excerpts"]}
    listed_q = {i for c in d["chapters"] for i in c["equations"]}
    listed_s = {i for c in d["chapters"] for i in c["exercise_sets"]}
    loose = ("".join(render_excerpt(x) for x in d["excerpts"] if x["id"] not in listed_x)
             + "".join(render_equation(x) for x in d["equations"] if x["id"] not in listed_q)
             + "".join(render_problem(p) for p in d["problems"]
                       if p.get("set") not in listed_s and p.get("set") not in {x["id"] for x in d["exercise_sets"]}))
    loose_sets = "".join(render_set(x, [p for p in d["problems"] if p.get("set") == x["id"]])
                         for x in d["exercise_sets"] if x["id"] not in listed_s)
    # raw.githubusercontent, not a /blob/ page: GitHub's blob view 503s/429s unauthenticated checkers
    # (measured from the build box 2026-10-10, every repo), so the link check could never confirm a blob link.
    data_url = f"https://raw.githubusercontent.com/cpuchip/pd-books/{pin}/export/{index_entry['file']}"
    body = f"""<h1>{e(b['title'])}</h1>
<p class="by">{e(", ".join(b.get("authors") or []))}, {e(str(b.get("year", "")))}. {e(b.get("edition") or "")}</p>
<section class="prov" id="provenance"><h2>Provenance and licence</h2>
<p>Text: <a href="{e(t.get('url', ''))}">{e(t.get('source', ''))}</a>, released {e(t.get('released', ''))}.
The transcription's licence, as it states it:</p>
<blockquote>{e(t.get('licence_terms', ''))}</blockquote>
<p>This site quotes excerpts and problems from that transcription and hosts no scans; scans are linked to
their archive. The records below (problems, checks, errata) are from <a href="{e(data_url)}">pd-books at
{e(pin[:7])}</a>, dedicated to the public domain (CC0), export generated {e(generated)}.</p></section>
<section><h2>Chapters</h2><ol class="chapters">{chapters}</ol>
<p><a href="terms/index.html">Index of terms</a> <span class="n"><span data-count="terms">{n_terms}</span>
{"term" if n_terms == 1 else "terms"}, by chapter</span></p></section>
{related}
<section><h2>Errata ({len(d.get('errata') or [])})</h2>
{'<ul class="errata">' + errata + '</ul>' if errata else '<p>None recorded yet.</p>'}</section>
{'<section><h2>Elsewhere in the book</h2><ul>' + loose + '</ul>' + loose_sets + '</section>' if loose or loose_sets else ''}"""
    return page(b["title"], body, 2, f"{b['title']} ({b.get('year')}): provenance, chapters, problems and errata",
                math=b.get("macros") or {})


# a formula in export markdown; a dollar escaped as \$ (Boyden's money) is a dollar, never a delimiter
MATH_SPAN = re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$(?:\\.|[^$\\])*\$", re.S)


def emphasis(s):
    """Export markdown as text (its LaTeX kept for KaTeX), with its *emphasis* and **strong** rendered by CommonMark's
    rule for star runs: a run that can open (left-flanking) and a later one that can close (right-flanking) pair up,
    nearest first, two stars where both have two, so nesting (*a (*i.e.*) b*) and a star inside a word (1*b*) work.
    A formula is set aside first: a star in it is not a marker, and an emphasis that holds one still closes. A star
    that pairs with nothing stays a star."""
    held = []

    def hold(m):
        held.append(m.group(0))
        return f"\x00{len(held) - 1}\x00"
    s = MATH_SPAN.sub(hold, s or "")
    parts = re.split(r"(\*+)", s)
    space = lambda c: c == "" or c.isspace()
    punct = lambda c: c != "" and not c.isalnum() and not c.isspace() and c != "\x00"
    runs = []  # [part index, stars left, can open, can close, open tags, close tags, stars in the run]
    for i in range(1, len(parts), 2):
        before = parts[i - 1][-1:] if parts[i - 1] else (parts[i - 2][-1:] if i >= 2 else "")
        after = parts[i + 1][:1] if i + 1 < len(parts) else ""
        left = not space(after) and (not punct(after) or space(before) or punct(before))
        right = not space(before) and (not punct(before) or space(after) or punct(after))
        runs.append([i, len(parts[i]), left, right, [], [], len(parts[i])])
    stack = []
    for r in runs:
        if r[3]:
            k = len(stack) - 1
            while k >= 0 and r[1]:
                o = stack[k]
                both = (o[2] and o[3]) or (r[2] and r[3])
                if o[1] and not (both and (o[6] + r[6]) % 3 == 0 and not (o[6] % 3 == 0 and r[6] % 3 == 0)):
                    use = 2 if o[1] >= 2 and r[1] >= 2 else 1
                    tag = "strong" if use == 2 else "em"
                    o[4].insert(0, f"<{tag}>")
                    r[5].append(f"</{tag}>")
                    o[1] -= use
                    r[1] -= use
                    del stack[k + 1:]  # runs between the pair can no longer pair across it
                    if not o[1]:
                        del stack[k]
                        k -= 1
                    continue
                k -= 1
        if r[1] and r[2]:
            stack.append(r)
    out = []
    for i, part in enumerate(parts):
        r = next((x for x in runs if x[0] == i), None) if i % 2 else None
        if r is None:
            out.append(html.escape(part))
        else:
            out.append("".join(r[5]) + "*" * r[1] + "".join(r[4]))
    return re.sub("\x00([0-9]+)\x00", lambda m: html.escape(held[int(m.group(1))]), "".join(out))


def locate(x, chapter_blocks):
    """The id of the text block where an excerpt's words begin, "" when they cannot be found there once (the
    excerpt then links to the text page's top), or None when the chapter has no text page."""
    if chapter_blocks is None:
        return None
    flat, owner = [], []
    for i, w, _ in chapter_blocks:
        flat.extend(w)
        owner.extend([i] * len(w))
    # the excerpt's words as its page shows them (its emphasis rendered, so 1*b* is the word 1b), formulas left out
    shown = html.unescape(re.sub(r"<[^>]+>", "", emphasis(x.get("markdown"))))
    want = textpage.words(MATH_SPAN.sub(" ", shown))
    s = " " + " ".join(flat) + " "
    for probe in (want, want[:8]):
        if len(probe) < 3:
            continue
        q = " " + " ".join(probe) + " "
        at = s.find(q)
        if at >= 0 and s.find(q, at + 1) < 0:
            return owner[s[:at + 1].count(" ") - 1]
    return ""


def page_label(v):
    """The export's page as a reader reads it: a printed page (183, xii) is "p. 183"; "scan 29" (a leaf of the scan,
    where the book prints no number the data could use) is "scan page 29"; anything else as written."""
    v = str(v)
    if re.fullmatch(r"[0-9]+|[ivxlcdm]+", v, re.I):
        return f"p. {v}"
    m = re.fullmatch(r"scan ([0-9]+)", v)
    return f"scan page {m.group(1)}" if m else v


def render_excerpt(x, where=None):
    page_no = f'<span class="pg">{e(page_label(x.get("page")))}</span>' if x.get("page") else ""
    link = ("" if where is None else
            f' <a class="intext" href="text/index.html{"#" + e(where) if where else ""}">In the text</a>')
    return (f'<li class="excerpt" data-kind="excerpt" data-id="{e(x["id"])}" id="{e(anchor(x["id"]))}"><p class="loc">{e(x.get("location") or "")}'
            f'{" " + page_no if page_no else ""}{link}</p>'
            f'<blockquote><span class="tx" data-field="text">{emphasis(x.get("markdown"))}</span></blockquote></li>')


def render_equation(x):
    return (f'<li class="equation" data-kind="equation" data-id="{e(x["id"])}" id="{e(anchor(x["id"]))}"><p class="loc">{e(x.get("location") or "")}</p>'
            f'<p><code{field("latex", x.get("latex"))}>{e(x.get("latex") or "")}</code></p>'
            + (f'<p>{text(x.get("statement"), "statement")}</p>' if (x.get("statement") or "").strip() else "") + "</li>")


def anchor(i):
    return "u-" + i.split("/", 1)[-1].replace("/", "-")


def elsewhere(d, x, what):
    """An item another chapter also lists: shown in full once, on its home chapter; here, a link to it."""
    bid = d["book"]["id"]
    home = next((c for c in d["chapters"] if c["id"] == x.get("chapter")), None)
    name = (home or {}).get("title") or x.get("chapter") or ""
    if not home:
        return f'<li class="{what} ref">This {what} is listed here; its own chapter is not in the data.</li>'
    href = f"../{e(chapter_slug(bid, home['id']))}/index.html#{e(anchor(x['id']))}"
    return f'<li class="{what} ref"><a href="{href}">This {what} is in {e(name)}</a> ({e(x.get("location") or "")})</li>'


def render_set(s, problems):
    items = "".join(render_problem(p) for p in problems)
    label = e(str(s.get("set")))
    return (f'<section class="set" data-kind="exercise_set" data-id="{e(s["id"])}" id="set-{label}">'
            f'<h3>Exercise {label}</h3>'
            + (f'<ol class="problems">{items}</ol>' if items
               else '<p class="n">The data holds no problems for this exercise yet.</p>')
            + "</section>")


def text_line(c, text_state):
    """The chapter page's line about its text page: a link, a reason it is withheld, or nothing (no text in the
    export)."""
    if c["id"] not in text_state:
        return ""
    why = text_state[c["id"]]
    if why is None:
        return '<p class="read"><a href="text/index.html">Read the chapter\'s text</a></p>'
    return (f'<p class="withheld" data-kind="text" data-id="{e(c["id"])}" data-withheld="{e(why)}">'
            f'The chapter\'s text is not shown yet: {e(why)}.</p>')


def render_text(d, c, clean):
    b = d["book"]
    title = c.get("title") or c.get("number") or "Chapter"
    errata = [x for x in d.get("errata") or [] if x.get("chapter") == c["id"]]
    if not d.get("errata"):
        beside = "<p>No errata are recorded for this book.</p>"
    elif errata:
        beside = "<ul>" + "".join(
            f'<li>{e(x["id"].split("/")[-1])}{", p. " + e(str(x["page"])) if x.get("page") else ""}: printed '
            f'<code>{e(x.get("printed") or "")}</code>, corrected <code>{e(x.get("corrected") or "")}</code></li>'
            for x in errata) + '</ul><p>Each is set out, with its evidence, on <a href="../../../index.html">the book\'s page</a>.</p>'
    else:
        beside = "<p>No errata are recorded for this chapter.</p>"
    body = f"""<p class="crumb"><a href="../../../index.html">{e(b['title'])}</a> / <a href="../index.html">{e(title)}</a></p>
<p class="n">The book's own words, changed in format only: the math typeset, and errata listed beside the text, never
edited into it. <a href="../../../index.html#provenance">Where this came from</a>.</p>
<aside class="errata-here"><h2>Errata</h2>{beside}</aside>
<article class="text" data-kind="text" data-id="{e(c['id'])}" data-field="body">{clean}</article>"""
    return page(f"{title} (text): {b['title']}", body, 5, math=b.get("macros") or {})


def text_pages(d, image_ok):
    """{chapter id: None (a page) or the reason it is withheld}, {chapter id: clean HTML}, [image paths]."""
    b = d["book"]["id"]
    chs = [c for c in d["chapters"] if c.get("text_html")]
    state = {}
    # a book the review held back (build/text-hold.json): its reason, as readers will read it
    held = (json.loads((HERE / "text-hold.json").read_text(encoding="utf-8")).get("books") or {}).get(b)
    if held:
        return {c["id"]: held for c in chs}, {}, []
    # an erratum with no chapter is one the text never shows (an answer at the back): printed_in_text false says so
    if any(not x.get("chapter") and x.get("printed_in_text") is not False for x in d.get("errata") or []):
        return {c["id"]: "its book's errata do not yet say which chapter each is in" for c in chs}, {}, []
    # the page carries the book's macros (data-macros), so a macro that names the transcription's source would put
    # that name on a text page, which Michael's ruling keeps off them
    if re.search(r"gutenberg", json.dumps(d["book"].get("macros") or {}), re.I):
        return {c["id"]: "its book's macros name the transcription's source" for c in chs}, {}, []
    where = {}
    for c in chs:
        for i in textpage.ids_of(c["text_html"]):
            where.setdefault(i, set()).add(c["id"])
    targets = {h for c in chs for h in textpage.links_of(c["text_html"])}

    def run(pages):
        clean, images, out = {}, [], {}
        for c in chs:
            mine = set(textpage.ids_of(c["text_html"]))

            def resolve(t, c=c, mine=mine):
                if t in mine:
                    return "self"
                other = (where.get(t) or set()) - {c["id"]}
                if len(other) == 1 and next(iter(other)) in pages:
                    return f"../../{chapter_slug(b, next(iter(other)))}/text/index.html#{textpage.ID_PREFIX}{t}"
                return None
            html_, imgs, why = textpage.sanitize(c["text_html"], b, image_ok, resolve, 5, targets, anchors=True)
            out[c["id"]] = "; ".join(why) if why else None
            if not why:
                clean[c["id"]] = html_
                images.extend(imgs)
        return out, clean, images
    first, _, _ = run({c["id"] for c in chs})  # which chapters pass; a link resolves only to a page that exists
    state, clean, images = run({i for i, w in first.items() if w is None})
    return state, clean, images


def render_chapter(d, c, text_state=None, chapter_blocks=None):
    by_id_x = {x["id"]: x for x in d["excerpts"]}
    by_id_q = {x["id"]: x for x in d["equations"]}
    sets = {s["id"]: s for s in d["exercise_sets"]}
    probs = {}
    for p in d["problems"]:
        probs.setdefault(p.get("set"), []).append(p)
    sections = ""
    for sid in c["exercise_sets"]:
        sections += render_set(sets.get(sid, {"id": sid, "set": sid}), probs.get(sid, []))
    b = d["book"]
    body = f"""<p class="crumb"><a href="../../index.html">{e(b['title'])}</a></p>
<h1>{e(c.get('title') or c.get('number') or '')}</h1>
{text_line(c, text_state or {})}
<section><h2>Excerpts</h2><ul class="excerpts">{''.join((render_excerpt(by_id_x[i], locate(by_id_x[i], chapter_blocks)) if by_id_x[i].get("chapter") == c["id"] else elsewhere(d, by_id_x[i], "excerpt")) for i in c['excerpts'] if i in by_id_x)}</ul></section>
<section><h2>Equations</h2><ul class="equations">{''.join((render_equation(by_id_q[i]) if by_id_q[i].get("chapter") == c["id"] else elsewhere(d, by_id_q[i], "equation")) for i in c['equations'] if i in by_id_q)}</ul></section>
<section><h2>Problems</h2>{sections or '<p>No exercises in this chapter.</p>'}</section>"""
    return page(f"{c.get('title') or c.get('number') or 'Chapter'}: {b['title']}", body, 4, math=b.get("macros") or {})


def render_shelf(index, books, sa=()):
    rows = "".join(
        f'<li class="book" data-kind="book" data-id="{e(d["book"]["id"])}"><a href="books/{e(d["book"]["id"])}/index.html">'
        f'{e(d["book"]["title"])}</a> <span class="by">{e(", ".join(d["book"].get("authors") or []))}, '
        f'{e(str(d["book"].get("year", "")))}</span> <span class="n">{len(d["chapters"])} chapters, '
        f'{len(d["problems"])} problems, {len(d.get("errata") or [])} errata</span></li>'
        for d in books)
    body = f"""<h1>Math and physics books</h1>
<h2>Public-domain books</h2>
<p class="lede">Books we read closely: each one's provenance, its chapters, its problems with the printed answers
checked by computation, and the errata we found, with the evidence for each.</p>
<ul class="shelf">{rows}</ul>{sa_shelf(sa)}"""
    both = (f'Book data from <a href="{PD_BOOKS}">pd-books</a> (CC0)'
            + (f' and <a href="{sapage.SA_BOOKS}">sa-books</a> (each book under its own CC BY-SA licence)' if sa else "")
            + f'. Lessons that use these books:\n<a href="{LEARN}">learn.cpuchip.net</a>.')
    return page("Math and physics books", body, 0, "Public-domain and share-alike math and physics books, checked",
                licence=both)


def sa_shelf(sa):
    """The share-alike books (sapage.py): (slug, book.json, page count) each."""
    if not sa:
        return ""
    rows = "".join(
        f'<li class="book" data-kind="sa-book" data-id="{e(slug)}"><a href="books/{e(slug)}/index.html">'
        f'{e(b["attribution"]["title_as_modified"])}</a> <span class="by">{e(b["author"])}, {e(str(b.get("year", "")))}'
        f'</span> <span class="n">{n} pages, <a href="{e(b["licence"]["url"])}">{e(b["licence"]["name"])}</a></span></li>'
        for slug, b, n in sa)
    return f"""
<h2>Share-alike books (CC BY-SA)</h2>
<p class="lede">Newer books whose authors released them under a Creative Commons Attribution-ShareAlike licence,
transcribed page by page. Each page carries its credits, and each stays under its book's licence.</p>
<ul class="shelf">{rows}</ul>"""


def node_urls(books, all_terms):
    """A page for each book, chapter and term node, as a link from graph/index.html; a term opens on the first
    book of the shelf that teaches it."""
    urls = {}
    for d in books:
        bid = d["book"]["id"]
        urls[bid] = f"../books/{bid}/index.html"
        for c in d["chapters"]:
            urls[c["id"]] = f"../books/{bid}/ch/{chapter_slug(bid, c['id'])}/index.html"
        for n in all_terms.get(bid, {}):
            urls.setdefault(n, f"../books/{bid}/terms/index.html#{term_anchor(n)}")
    return urls


def compact_graph(graph, urls):
    idx = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    nt = {t: i for i, t in enumerate(graph["node_types"])}
    et = {t: i for i, t in enumerate(graph["edge_types"])}
    return {"node_types": graph["node_types"], "edge_types": graph["edge_types"],
            "concept_layer": CONCEPT_LAYER,
            "counts": {"nodes": len(graph["nodes"]), "links": len(graph["links"])},
            "nodes": [[n["id"], nt[n["type"]], n.get("name") or ""] + ([urls[n["id"]]] if n["id"] in urls else [])
                      for n in graph["nodes"]],
            "links": [[idx[l["source"]], idx[l["target"]], et[l["type"]]] for l in graph["links"]]}


def render_graph_page(g, books, entries):
    options = "".join(f'<option value="book:{e(d["book"]["id"])}">{e(d["book"]["title"])}</option>' for d in books)
    terms = "".join(f'<li><a href="../books/{e(d["book"]["id"])}/terms/index.html">{e(d["book"]["title"])}</a></li>'
                    for d in books)
    body = f"""<h1>Concept graph</h1>
<p>{g['counts']['nodes']:,} nodes and {g['counts']['links']:,} links across the shelf
(<a href="graph.json">graph.json</a>). The view starts with the concept layer: books, chapters and the concepts,
theorems, methods, laws, quantities, units, instruments, experiments and people they teach. Drag to turn it and
scroll to zoom. Point at a node or tap it to see what it links to, or find it by name; the key can hide a type.</p>
<p><label for="view">View</label> <select id="view"><option value="concepts">The concept layer</option>
<option value="all">Everything (slow on a phone)</option>{options}</select></p>
<p class="n"><output id="graph-report">The 3D view needs scripts and WebGL.</output></p>
<div class="graph-wrap">
<div id="graph" class="graph-canvas"></div>
<aside class="graph-panel">
<p class="graph-find"><label for="graph-find">Find</label> <input id="graph-find" list="graph-names" type="search"
autocomplete="off" spellcheck="false"><datalist id="graph-names"></datalist></p>
<p id="graph-said" class="said" aria-live="polite"></p>
<div id="graph-pick" class="pick">Tap or click a node to name it.</div>
<h2>Key</h2>
<ul id="graph-key" class="graph-key"></ul>
</aside>
</div>
<section><h2>The same data, as text</h2><p>Each book's index of terms lists what it teaches and where:</p>
<ul>{terms}</ul></section>"""
    return page("Concept graph", body, 1, "The concept graph of the shelf in 3D",
                scripts=["vendor/3d-force-graph/3d-force-graph.min.js", "graph.js"])


def render_search_page(books, sa_shelf_rows):
    shelf = [(d["book"]["title"], d["book"]["id"]) for d in books] + [(book["title"], slug) for slug, book, _ in sa_shelf_rows]
    options = "".join(f'<option value="{e(slug)}">{e(title)}</option>' for title, slug in sorted(shelf))
    body = f"""<h1>Search</h1>
<p>Every word of the shelf: the books' text, excerpts, problems, equations' statements and terms. All the words must
be on the page; "quoted words" must stand together. The search runs in your browser on this site's own index
files, so the words you type are not sent: the browser fetches the parts of the index a search needs (named by a
word's first letter), and the server keeps no log of what it serves.</p>
<form id="search-form" class="search" action="index.html" method="get" role="search">
<p><label for="q">Words</label> <input id="q" name="q" type="search" autocomplete="off" spellcheck="false"></p>
<p><label for="search-book">In</label> <select id="search-book" name="book"><option value="">every book</option>
{options}</select> <button type="submit">Search</button></p>
</form>
<p class="n"><output id="search-report">The search needs scripts.</output></p>
<ol id="search-results" class="hits"></ol>"""
    return page("Search", body, 1, "Search every book on the shelf",
                scripts=["vendor/katex/katex.min.js", "search/search.js"], styles=["vendor/katex/katex.min.css"])


def render_about(pin, sa_pin=None):
    sa = (f"""
<p>The share-alike books are built from <a href="{sapage.SA_BOOKS}">sa-books</a> at <code>{e(sa_pin[:7])}</code>:
newer books whose authors released them under a Creative Commons Attribution-ShareAlike licence. Each of their
pages carries its credits and stays under its book's licence, and a build that loses a page, a word, a formula or
a figure of them does not publish.</p>""" if sa_pin else "")
    body = f"""<h1>About</h1>
<p>The public-domain books are built from <a href="{PD_BOOKS}">pd-books</a> at <code>{e(pin[:7])}</code>. A build that
loses a book, a problem or an erratum from that data does not publish. Corrections are welcome in pd-books.</p>
<p>Those books are in the public domain in the United States. Their transcriptions come from
<a href="https://www.gutenberg.org/">Project Gutenberg</a>, whose licence each book page quotes, with a link to the
book's own page there. Scans of the printed books are linked to the archive that holds them,
not copied here.</p>{sa}"""
    return page("About", body, 1)


def sa_books(root, sa_pin):
    """Every book in an sa-books checkout: ({site path: html}, {site path: figure file}, [(slug, book, pages)])."""
    files, figs, shelf = {}, {}, []
    for bj in sorted(Path(root, "books").glob("*/book.json")):
        slug = bj.parent.name
        try:
            f, g, (book, n) = sapage.build_pages(Path(root), slug, sa_pin, page)
        except sapage.Refused as x:
            refuse(f"sa-books: {x}")
        files.update(f)
        figs.update(g)
        shelf.append((slug, book, n))
    if not shelf:
        refuse(f"sa-books at {root} has no book")
    return files, figs, shelf


def build(export, out, pin, pd_books_check=True, sa_root=None, sa_pin=None):
    index, books, graph = load(export, pd_books_check)
    sa_files, sa_figs, sa_shelf_rows = sa_books(sa_root, sa_pin) if sa_root else ({}, {}, [])
    for p in sa_files:
        if any(p.startswith(f"books/{b['id']}/") for b in index["books"]):
            refuse(f"sa-books page {p} would overwrite a pd-books page")
    generated = (index.get("generated_from") or {}).get("generated_at", "")
    entries = {b["id"]: b for b in index["books"]}
    with tempfile.TemporaryDirectory(dir=Path(out).parent if Path(out).parent.exists() else None) as tmp:
        dist = Path(tmp) / "dist"
        dist.mkdir()

        def w(rel, s):
            p = dist / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(s, encoding="utf-8", newline="\n")

        shutil.copy(HERE / "site.css", dist / "site.css")
        w("index.html", render_shelf(index, books, sa_shelf_rows))
        for rel, s in sa_files.items():
            w(rel, s)
        for rel, src in sa_figs.items():
            (dist / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dist / rel)
        w("about/index.html", render_about(pin, sa_pin if sa_root else None))
        all_terms = terms_of(graph, books)
        check_relations(index.get("relations") or [], entries)
        names = {n["id"]: n.get("name") or "" for n in graph["nodes"]}
        kinds = {n["id"]: n["type"] for n in graph["nodes"]}
        teaching = {}
        for b, terms in all_terms.items():
            for n in terms:
                teaching.setdefault(n, set()).add(b)
        relations = index.get("relations") or []
        withheld, n_text = [], 0
        for d in books:
            bid = d["book"]["id"]
            terms = all_terms.get(bid, {})
            related = render_relations(d, relations, names, entries, terms)
            w(f"books/{bid}/index.html", render_book(d, entries[bid], pin, generated, related, len(terms)))
            w(f"books/{bid}/terms/index.html", render_terms(d, terms, names, kinds, teaching, entries))
            state, clean, images = text_pages(d, lambda rel: (Path(export) / rel).is_file())
            for cid, why in sorted(state.items()):
                if why is not None:
                    withheld.append((cid, why))
            for c in d["chapters"]:
                blk = textpage.blocks(clean[c["id"]]) if c["id"] in clean else None
                w(f"books/{bid}/ch/{chapter_slug(bid, c['id'])}/index.html", render_chapter(d, c, state, blk))
                if c["id"] in clean:
                    w(f"books/{bid}/ch/{chapter_slug(bid, c['id'])}/text/index.html", render_text(d, c, clean[c["id"]]))
                    n_text += 1
            for rel in sorted(set(images)):
                (dist / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(export) / rel, dist / rel)
        g = compact_graph(graph, node_urls(books, all_terms))
        w("graph/graph.json", json.dumps(g, ensure_ascii=False, separators=(",", ":")))
        w("graph/index.html", render_graph_page(g, books, entries))
        for f in ("site.js", "graph.js", "favicon.svg"):
            shutil.copy(HERE / f, dist / f)
        n_pages, n_units, n_words = search.build(dist)  # from the finished pages; the search page is not indexed
        w("search/index.html", render_search_page(books, sa_shelf_rows))
        shutil.copy(HERE / "search.js", dist / "search" / "search.js")
        shutil.copytree(HERE / "vendor", dist / "vendor")
        version = {"pd_books": pin, "export_generated_at": generated, "books": len(books)}
        if sa_root:
            version.update({"sa_books": sa_pin, "sa_books_books": len(sa_shelf_rows)})
        w("version.json", json.dumps(version, indent=1) + "\n")
        out = Path(out)
        if out.exists():
            shutil.rmtree(out)
        shutil.move(str(dist), str(out))
    print(f"built {out}: {len(books)} books, {sum(len(d['chapters']) for d in books)} chapter pages, "
          f"{sum(len(d['problems']) for d in books)} problems, {sum(len(d.get('errata') or []) for d in books)} errata, "
          f"{n_text} chapter text pages, {len(withheld)} withheld; search {n_units} units on {n_pages} pages"
          + (f"; sa-books {sa_pin[:7]}: {len(sa_shelf_rows)} books, {len(sa_files) - len(sa_shelf_rows)} pages, "
             f"{len(sa_figs)} figures" if sa_root else ""))
    for cid, why in withheld:
        print(f"  text withheld: {cid}: {why}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pin", help="pd-books commit (default: read pd-books.pin)")
    ap.add_argument("--no-checks", action="store_true")
    ap.add_argument("--sa-books", help="an sa-books checkout at --sa-pin (its books are built beside pd-books')")
    ap.add_argument("--sa-pin", help="sa-books commit (default: read sa-books.pin)")
    a = ap.parse_args()
    pin = a.pin or (HERE.parent / "pd-books.pin").read_text().strip()
    sa_pin = (a.sa_pin or (HERE.parent / "sa-books.pin").read_text().strip()) if a.sa_books else None
    build(a.export, a.out, pin, not a.no_checks, a.sa_books, sa_pin)


if __name__ == "__main__":
    main()
