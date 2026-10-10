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

HERE = Path(__file__).resolve().parent
SCHEMAS = {1}
PD_BOOKS = "https://github.com/cpuchip/pd-books"
LEARN = "https://learn.cpuchip.net/"
CONCEPT_LAYER = ["book", "person", "chapter", "concept", "method", "theorem", "law", "quantity", "unit",
                 "instrument", "experiment"]
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


def page(title, body, depth, desc=""):
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="stylesheet" href="{up}site.css">
</head>
<body>
<header class="top"><a class="brand" href="{up}index.html">Public-domain books</a>
<nav><a href="{up}graph/index.html">Concept graph</a> <a href="{up}about/index.html">About</a></nav></header>
<main>
{body}
</main>
<footer class="foot"><p>Book data from <a href="{PD_BOOKS}">pd-books</a> (CC0). Lessons that use these books:
<a href="{LEARN}">learn.cpuchip.net</a>. Site code MIT.</p></footer>
</body>
</html>
"""


def text(s):
    """Export markdown is shown as text (LaTeX source kept) until a math renderer is approved."""
    return f'<span class="tx">{e(s or "")}</span>'


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
    answers = "".join(f"<li>{text(a)}</li>" for a in p.get("answer_markdown") or []) or "<li>(none printed)</li>"
    checks = "".join(
        f"<li><code>{e(c['task'])}</code>: {e(CHECK_WORDS.get(c['verdict'], c['verdict']))}"
        + (f" <code>{e(c['answer_expr'])}</code>" if c.get("answer_expr") else "") + "</li>"
        for c in p.get("checks") or [])
    keys = ""
    for k in p.get("keys") or []:
        pins = k.get("core_pins") or {}
        keys += (f'<div class="keys"><p>On the STU-32 ({e(k.get("mode", ""))}, {e(k.get("entry", ""))}):</p>'
                 + "".join(f"<pre>{e(s)}</pre>" for s in k.get("steps") or [])
                 + f'<p>Calculator: <code>{e(k.get("calculator_value", ""))}</code>; the book prints '
                 f'<code>{e(k.get("printed_value", ""))}</code>. Run on the calculator core at firmware '
                 f'<code>{e(str(pins.get("firmware", ""))[:7])}</code>.</p></div>')
    verdict = p.get("verdict") or ""
    return (f'<li class="problem" data-kind="problem" data-id="{e(p["id"])}" id="p-{e(p["id"].split("/", 1)[-1].replace("/", "-"))}">'
            f'<p class="loc">{e(p.get("location") or "")}{", p. " + e(str(p["page"])) if p.get("page") else ""}</p>'
            f'<p>{text(p.get("markdown"))}</p>'
            f'<div class="ans"><span>Printed answer:</span><ul>{answers}</ul></div>'
            f'<p class="verdict v-{e(verdict)}">{e(verdict)}: {e(VERDICTS.get(verdict, ""))}</p>'
            + (f'<details><summary>How it was checked</summary><ul>{checks}</ul></details>' if checks else "")
            + keys + "</li>")


def render_erratum(x):
    scans = scan_links(x.get("evidence"))
    ev = neutral.evidence(x.get("evidence") or "")
    return (f'<li class="erratum" data-kind="erratum" data-id="{e(x["id"])}">'
            f'<p class="loc">{e(x["id"].split("/")[-1])}: {e(x.get("location") or "")}'
            f'{", p. " + e(str(x["page"])) if x.get("page") else ""}</p>'
            f'<p>Printed: {text(x.get("printed"))}<br>Corrected: {text(x.get("corrected"))}</p>'
            + (f'<p class="ctx">In the source: <code>{e(x["context"])}</code></p>' if x.get("context") else "")
            + (f'<p class="n">{e(x["class"])}</p>' if x.get("class") else "")
            + f'<p class="credit">{e(neutral.credit(x.get("status"), x.get("kind")))}</p>'
            + (f'<p class="ev">{e(ev)}</p>' if ev else "")
            + "".join(f'<p>Scan: <a href="{e(u)}">{e(u)}</a></p>' for u in scans)
            + "</li>")


def render_book(d, index_entry, pin, generated):
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
             + "".join(render_problem(p) for p in d["problems"] if p.get("set") not in listed_s))
    # raw.githubusercontent, not a /blob/ page: GitHub's blob view 503s/429s unauthenticated checkers
    # (measured from lepton 2026-10-10, every repo), so the link check could never confirm a blob link.
    data_url = f"https://raw.githubusercontent.com/cpuchip/pd-books/{pin}/export/{index_entry['file']}"
    body = f"""<h1>{e(b['title'])}</h1>
<p class="by">{e(", ".join(b.get("authors") or []))}, {e(str(b.get("year", "")))}. {e(b.get("edition") or "")}</p>
<section class="prov"><h2>Provenance and licence</h2>
<p>Text: <a href="{e(t.get('url', ''))}">{e(t.get('source', ''))}</a>, released {e(t.get('released', ''))}.
The transcription's licence, as it states it:</p>
<blockquote>{e(t.get('licence_terms', ''))}</blockquote>
<p>This site quotes excerpts and problems from that transcription and hosts no scans; scans are linked to
their archive. The records below (problems, checks, errata) are from <a href="{e(data_url)}">pd-books at
{e(pin[:7])}</a>, dedicated to the public domain (CC0), export generated {e(generated)}.</p></section>
<section><h2>Chapters</h2><ol class="chapters">{chapters}</ol></section>
<section><h2>Errata ({len(d.get('errata') or [])})</h2>
{'<ul class="errata">' + errata + '</ul>' if errata else '<p>None recorded yet.</p>'}</section>
{'<section><h2>Elsewhere in the book</h2><ul>' + loose + '</ul></section>' if loose else ''}"""
    return page(b["title"], body, 2, f"{b['title']} ({b.get('year')}): provenance, chapters, problems and errata")


def render_excerpt(x):
    return (f'<li class="excerpt" data-kind="excerpt" data-id="{e(x["id"])}" id="{e(anchor(x["id"]))}"><p class="loc">{e(x.get("location") or "")}</p>'
            f'<blockquote>{text(x.get("markdown"))}</blockquote></li>')


def render_equation(x):
    return (f'<li class="equation" data-kind="equation" data-id="{e(x["id"])}" id="{e(anchor(x["id"]))}"><p class="loc">{e(x.get("location") or "")}</p>'
            f'<p><code>{e(x.get("latex") or "")}</code></p><p>{text(x.get("statement"))}</p></li>')


def anchor(i):
    return "u-" + i.split("/", 1)[-1].replace("/", "-")


def elsewhere(d, x, what):
    """An item another chapter also lists: shown in full once, on its home chapter; here, a link to it."""
    bid = d["book"]["id"]
    home = next((c for c in d["chapters"] if c["id"] == x.get("chapter")), None)
    name = (home or {}).get("title") or x.get("chapter") or ""
    href = f"../{e(chapter_slug(bid, home['id']))}/index.html#{e(anchor(x['id']))}" if home else "#"
    return f'<li class="{what} ref"><a href="{href}">This {what} is in {e(name)}</a> ({e(x.get("location") or "")})</li>'


def render_chapter(d, c):
    by_id_x = {x["id"]: x for x in d["excerpts"]}
    by_id_q = {x["id"]: x for x in d["equations"]}
    sets = {s["id"]: s for s in d["exercise_sets"]}
    probs = {}
    for p in d["problems"]:
        probs.setdefault(p.get("set"), []).append(p)
    sections = ""
    for sid in c["exercise_sets"]:
        s = sets.get(sid, {"set": sid})
        items = "".join(render_problem(p) for p in probs.get(sid, []))
        sections += (f'<section class="set" id="set-{e(str(s.get("set")))}"><h3>Exercise {e(str(s.get("set")))}</h3>'
                     f'<ol class="problems">{items}</ol></section>')
    b = d["book"]
    body = f"""<p class="crumb"><a href="../../index.html">{e(b['title'])}</a></p>
<h1>{e(c.get('title') or c.get('number') or '')}</h1>
<section><h2>Excerpts</h2><ul class="excerpts">{''.join((render_excerpt(by_id_x[i]) if by_id_x[i].get("chapter") == c["id"] else elsewhere(d, by_id_x[i], "excerpt")) for i in c['excerpts'] if i in by_id_x)}</ul></section>
<section><h2>Equations</h2><ul class="equations">{''.join((render_equation(by_id_q[i]) if by_id_q[i].get("chapter") == c["id"] else elsewhere(d, by_id_q[i], "equation")) for i in c['equations'] if i in by_id_q)}</ul></section>
<section><h2>Problems</h2>{sections or '<p>No exercises in this chapter.</p>'}</section>"""
    return page(f"{c.get('title') or ''}: {b['title']}", body, 4)


def render_shelf(index, books):
    rows = "".join(
        f'<li class="book" data-kind="book" data-id="{e(d["book"]["id"])}"><a href="books/{e(d["book"]["id"])}/index.html">'
        f'{e(d["book"]["title"])}</a> <span class="by">{e(", ".join(d["book"].get("authors") or []))}, '
        f'{e(str(d["book"].get("year", "")))}</span> <span class="n">{len(d["chapters"])} chapters, '
        f'{len(d["problems"])} problems, {len(d.get("errata") or [])} errata</span></li>'
        for d in books)
    body = f"""<h1>Public-domain math and physics books</h1>
<p class="lede">Books we read closely: each one's provenance, its chapters, its problems with the printed answers
checked by computation, and the errata we found, with the evidence for each.</p>
<ul class="shelf">{rows}</ul>"""
    return page("Public-domain math and physics books", body, 0, "Public-domain math and physics books, checked")


def compact_graph(graph):
    idx = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    nt = {t: i for i, t in enumerate(graph["node_types"])}
    et = {t: i for i, t in enumerate(graph["edge_types"])}
    return {"node_types": graph["node_types"], "edge_types": graph["edge_types"],
            "concept_layer": CONCEPT_LAYER,
            "counts": {"nodes": len(graph["nodes"]), "links": len(graph["links"])},
            "nodes": [[n["id"], nt[n["type"]], n.get("name") or ""] for n in graph["nodes"]],
            "links": [[idx[l["source"]], idx[l["target"]], et[l["type"]]] for l in graph["links"]]}


def render_graph_page(g):
    body = f"""<h1>Concept graph</h1>
<p>{g['counts']['nodes']:,} nodes and {g['counts']['links']:,} links across the shelf
(<a href="graph.json">graph.json</a>). The 3D view is in preparation.</p>"""
    return page("Concept graph", body, 1)


def render_about(pin):
    body = f"""<h1>About</h1>
<p>Every page here is built from <a href="{PD_BOOKS}">pd-books</a> at <code>{e(pin[:7])}</code>. A build that
loses a book, a problem or an erratum from that data does not publish. Corrections are welcome in pd-books.</p>
<p>The books are in the public domain in the United States. Their transcriptions come from Project Gutenberg,
whose licence each book page quotes. Scans of the printed books are linked to the archive that holds them,
not copied here.</p>"""
    return page("About", body, 1)


def build(export, out, pin, pd_books_check=True):
    index, books, graph = load(export, pd_books_check)
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
        w("index.html", render_shelf(index, books))
        w("about/index.html", render_about(pin))
        for d in books:
            bid = d["book"]["id"]
            w(f"books/{bid}/index.html", render_book(d, entries[bid], pin, generated))
            for c in d["chapters"]:
                w(f"books/{bid}/ch/{chapter_slug(bid, c['id'])}/index.html", render_chapter(d, c))
        g = compact_graph(graph)
        w("graph/graph.json", json.dumps(g, ensure_ascii=False, separators=(",", ":")))
        w("graph/index.html", render_graph_page(g))
        w("version.json", json.dumps({"pd_books": pin, "export_generated_at": generated,
                                      "books": len(books)}, indent=1) + "\n")
        out = Path(out)
        if out.exists():
            shutil.rmtree(out)
        shutil.move(str(dist), str(out))
    print(f"built {out}: {len(books)} books, {sum(len(d['chapters']) for d in books)} chapter pages, "
          f"{sum(len(d['problems']) for d in books)} problems, {sum(len(d.get('errata') or []) for d in books)} errata")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pin", help="pd-books commit (default: read pd-books.pin)")
    ap.add_argument("--no-checks", action="store_true")
    a = ap.parse_args()
    pin = a.pin or (HERE.parent / "pd-books.pin").read_text().strip()
    build(a.export, a.out, pin, not a.no_checks)


if __name__ == "__main__":
    main()
