"""browsercheck.py: the built pages do in a browser what they say: the math is typeset, the 3D graph draws the export.

    python3 tools/browsercheck.py EXPORT DIST --chromium PATH [--control] [--jobs N]

A headless Chromium (a browser binary run as a command-line tool: --dump-dom, no automation library) loads every
book and chapter page and the graph page in each view from a local server this script runs and stops, and reads
what each page wrote into its report element after its scripts ran.
  Math: every page reports (#math-report data-typeset/data-source), and typeset + shown-as-source equals the number
        of formulas this checker counts in the built HTML itself: each data-field="latex" element, and each $...$
        or $$...$$ span inside a text field (found the way KaTeX's auto-render finds them: backslash escapes and
        brace depth respected). The number shown as source may not exceed each book's ceiling in
        build/math-ceiling.json (a ratchet: a broken KaTeX would show everything as source and still add up).
  Graph: #graph-report states the counts drawn: the default view the concept layer, ?view=all the whole graph, and
        ?book=<id> each book (the book, the chapters its book file lists, and every node taught_in them), each as
        this checker computes it from the export's graph.json and book files.
--control plants a formula KaTeX cannot read (its page must show one more as source), a chapter page without its
script (no report), and a graph script that drops a node (the default view one short), each in a copy.
"""
import argparse
import functools
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONCEPT_LAYER = ("book", "person", "chapter", "concept", "method", "theorem", "law", "quantity", "unit",
                 "instrument", "experiment")  # copied from the blueprint, not imported from the build
REPORT = re.compile(r'<output id="(math|graph)-report"([^>]*)>')
ANNOTATION = re.compile(r'<annotation encoding="application/x-tex">(.*?)</annotation>', re.S)
WINDOW = "500,900"
EQUATION = re.compile(r'<div class="math">.*?<annotation encoding="application/x-tex">(.*?)</annotation>'
                      r'|<code data-field="latex"[^>]*class="tex-source"[^>]*>(.*?)</code>', re.S)  # the narrowest window this headless Chromium lays out; no page may be wider than it
sys.path.insert(0, str(Path(__file__).resolve().parent))
from graphcheck import export_urls  # noqa: E402  the node links, by the rule the graph check already holds
ATTR = re.compile(r'data-([a-z-]+)="([^"]*)"')


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class Server:
    def __init__(self, root):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


def dump(chromium, url, budget, profile, timeout=240):
    # --no-sandbox: this box's AppArmor disables the unprivileged user namespaces Chromium's sandbox needs (Ubuntu
    # 26.04). What it loads is only this site's files, from 127.0.0.1: the resolver rule sends every other host
    # nowhere, so a page that fetched anything from outside would fail its report here.
    r = subprocess.run([chromium, "--headless", "--no-sandbox", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp", f"--window-size={WINDOW}",
                        "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader",
                        "--no-first-run", f"--user-data-dir={profile}", f"--virtual-time-budget={budget}",
                        "--dump-dom", url], capture_output=True, text=True, timeout=timeout)
    return r.stdout


def reports(dom):
    # the DOM dump escapes attribute values (a quote is &quot;), so a report is read back unescaped
    out = {k: {n: html.unescape(v) for n, v in ATTR.findall(attrs)} for k, attrs in REPORT.findall(dom)}
    if "math" in out:
        main = dom[dom.find("<main"):dom.rfind("</main>")]
        out["math"]["annotations"] = [html.unescape(a) for a in ANNOTATION.findall(main)]
        # the display equations in page order: ("typeset", its annotation) or ("source", its text)
        out["math"]["equations"] = [("typeset", html.unescape(a)) if a or not b else ("source", html.unescape(b))
                                    for a, b in EQUATION.findall(main)]
    return out


# ---- the math the HTML holds ----------------------------------------------------------------------------------

def find_end(text, start, delim):
    """auto-render's findEndOfMath: the index of the closing delimiter at brace depth 0, skipping escapes."""
    i, depth = start, 0
    while i < len(text):
        ch = text[i]
        if depth <= 0 and text.startswith(delim, i):
            return i
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return -1


def inline_spans(text):
    """The TeX of each $$...$$ and $...$ span auto-render would take from one text node."""
    out, i = [], 0
    while True:
        a = text.find("$", i)
        if a < 0:
            return out
        delim = "$$" if text.startswith("$$", a) else "$"
        end = find_end(text, a + len(delim), delim)
        if end < 0:
            return out
        out.append(text[a + len(delim):end])
        i = end + len(delim)


def aligned(tex):
    """The blueprint's display rule: a bare alignment row is typeset inside aligned."""
    if re.search(r"(^|[^\\])&", tex) and not re.search(r"\\begin\{", tex):
        return "\\begin{aligned}" + tex + "\\end{aligned}"
    return tex


class _Math(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.latex, self.tx, self.in_main, self.buf = [], [], [], False, None
        # a chapter text page's math: pandoc's <span class="math inline|display"> inside <article class="text">
        self.in_article, self.mbuf, self.text_math = 0, None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "main":
            self.in_main = True
        if self.in_main and a.get("data-field") == "latex":
            self.buf = []
        is_tx = self.in_main and "tx" in (a.get("class") or "").split()
        if tag == "article" and "text" in (a.get("class") or "").split():
            self.in_article = 1
        elif self.in_article and tag not in ("br", "meta", "link", "img", "hr", "input", "wbr"):
            self.in_article += 1
        classes = (a.get("class") or "").split()
        if self.in_article and tag == "span" and "math" in classes and ("inline" in classes or "display" in classes):
            self.mbuf = ([], "display" in classes)
        if tag not in ("br", "meta", "link", "img", "hr", "input", "wbr"):
            self.stack.append((tag, [] if is_tx else None))

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main = False
        if self.in_article and tag not in ("br", "meta", "link", "img", "hr", "input", "wbr"):
            self.in_article -= 1
        if self.mbuf is not None and tag == "span":
            tex, display = "".join(self.mbuf[0]), self.mbuf[1]
            open_, close = ("\\[", "\\]") if display else ("\\(", "\\)")
            if tex.startswith(open_) and tex.endswith(close):  # as site.js strips them
                tex = tex[2:-2]
            self.text_math.append(tex)
            self.mbuf = None
        if self.buf is not None and tag == "code":
            self.latex.append("".join(self.buf))
            self.buf = None
        for j in range(len(self.stack) - 1, -1, -1):
            if self.stack[j][0] == tag:
                for _, buf in self.stack[j:]:
                    if buf is not None:
                        self.tx.append("".join(buf))
                del self.stack[j:]
                return

    def handle_data(self, data):
        if self.buf is not None:
            self.buf.append(data)
        if self.mbuf is not None:
            self.mbuf[0].append(data)
        for _, buf in self.stack:
            if buf is not None:
                buf.append(data)


def formulas(html_text, equations_only=False):
    """The TeX of every formula the page holds, as site.js hands it to KaTeX (or the equations alone, unwrapped,
    in page order)."""
    p = _Math()
    p.feed(html_text)
    if equations_only:
        return p.latex
    return [aligned(t) for t in p.latex] + [s for t in p.tx for s in inline_spans(t)] + p.text_math


# ---- the graph the export holds -------------------------------------------------------------------------------

def view_nodes(export, g, view):
    """The node ids a view draws: everything, the concept layer, or a book with its chapters (from the book file) and
    every node taught_in them."""
    if view == "all":
        return {n["id"] for n in g["nodes"]}
    if view == "concepts":
        return {n["id"] for n in g["nodes"] if n["type"] in CONCEPT_LAYER}
    book = view[5:]
    d = json.loads((Path(export) / "books" / f"{book}.json").read_text(encoding="utf-8"))
    chapters = {c["id"] for c in d["chapters"]}
    return {book} | chapters | {l["source"] for l in g["links"] if l["type"] == "taught_in" and l["target"] in chapters}


def graph_views(export):
    export = Path(export)
    index = json.loads((export / "books.json").read_text(encoding="utf-8"))
    g = json.loads((export / "graph.json").read_text(encoding="utf-8"))
    views = {}
    for v in ["all", "concepts"] + [f"book:{b['id']}" for b in index["books"]]:
        keep = view_nodes(export, g, v)
        views[v] = [len(keep), sum(1 for l in g["links"] if l["source"] in keep and l["target"] in keep)]
    return views


def view_url(v):
    return "graph/index.html" + ("" if v == "concepts" else "?view=all" if v == "all" else f"?book={v[5:]}")


# ---- run --------------------------------------------------------------------------------------------------------

def run(export, dist, chromium, jobs, views=None, pages=None):
    """{"math": {page: (typeset, source) or None}, "graph": {view: (nodes, links) or None}}"""
    dist = Path(dist)
    if pages is None:
        pages = sorted(p.relative_to(dist).as_posix() for p in dist.glob("books/*/index.html")) + sorted(
            p.relative_to(dist).as_posix() for p in dist.glob("books/*/ch/*/index.html")) + sorted(
            p.relative_to(dist).as_posix() for p in dist.glob("books/*/ch/*/text/index.html"))
    views = views if views is not None else list(graph_views(export))
    out = {"math": {}, "graph": {}}
    with tempfile.TemporaryDirectory() as tmp, Server(dist) as base:
        def one(job):
            what, key, url, budget = job
            profile = Path(tmp) / f"p{threading.get_ident()}"
            t0 = time.monotonic()
            try:
                r = reports(dump(chromium, base + url, budget, profile)).get(what)
            except subprocess.TimeoutExpired:
                r = None  # no report: red, named by judge()
                # said here as well, so a hang is told apart from a page whose script did not run (2026-10-13: two
                # hangs in a day, each on a page that renders in seconds alone)
                print(f"browser: {url} timed out after {time.monotonic() - t0:.0f} s", flush=True)
            if what == "math":
                return what, key, (int(r["typeset"]), int(r["source"]), int(r.get("overflow", -1)),
                                   r["annotations"], r["equations"], r.get("macros-used")) if r and "typeset" in r else None
            if not (r and r.get("view") == key and "nodes" in r):
                return what, key, None
            return what, key, (int(r["nodes"]), int(r["links"]), r.get("digest"))
        # virtual time stops while a fetch is pending and then runs frame by frame: the graph's report is written
        # before its first frame, so a few frames of budget is enough, and a long one renders hundreds of frames of
        # a 19,904-node graph in software (minutes, when eight browsers share the CPU)
        # the graph views run after the pages, two at a time: the whole graph renders in software, and eight
        # browsers contending with it made its frames slow enough to time out (measured 2026-10-10)
        phases = [([("math", p, p, 10000) for p in pages], jobs), ([("graph", v, view_url(v), 300) for v in views], 2)]
        for jobs_list, n in phases:
            with ThreadPoolExecutor(n) as ex:
                for what, key, val in ex.map(one, jobs_list):
                    out[what][key] = val
    return out


def view_digest(export, view):
    """What graph.js must hold for a view, digested the way it digests it (sorted as JavaScript sorts strings)."""
    export = Path(export)
    g = json.loads((export / "graph.json").read_text(encoding="utf-8"))
    keep = view_nodes(export, g, view)
    urls = dict(export_urls(export))
    if view.startswith("book:"):  # a book's own terms open on its own index of terms
        book = view[5:]
        d = json.loads((Path(export) / "books" / f"{book}.json").read_text(encoding="utf-8"))
        chapters = {c["id"] for c in d["chapters"]}
        for l in g["links"]:
            if l["type"] == "taught_in" and l["target"] in chapters:
                urls[l["source"]] = f"../books/{book}/terms/index.html#t-{l['source'].replace('/', '-')}"
    js_sort = lambda xs: sorted(xs, key=lambda s: s.encode("utf-16-be"))
    nodes = js_sort(f"{n['id']}\t{n['type']}: {n.get('name') or ''}\t{urls.get(n['id'], '')}"
                    for n in g["nodes"] if n["id"] in keep)
    links = js_sort(f"{l['source']}\t{l['target']}" for l in g["links"] if l["source"] in keep and l["target"] in keep)
    return fnv64("\n".join(nodes) + "\n--\n" + "\n".join(links))


def fnv64(text):
    """graph.js's digest: two 32-bit FNV-1a hashes of the UTF-8 bytes (offsets 0x811c9dc5 and 0x050c5d1f)."""
    a, b = 0x811C9DC5, 0x050C5D1F
    for byte in text.encode("utf-8"):
        a = ((a ^ byte) * 0x01000193) & 0xFFFFFFFF
        b = ((b ^ byte) * 0x01000193) & 0xFFFFFFFF
    return f"{a:08x}{b:08x}"


def ceiling_key(page):
    """A book's ceiling, or its text pages' own ("<book> (text)"), so the text cannot hide behind the book."""
    return page.split("/")[1] + (" (text)" if page.endswith("/text/index.html") else "")


def load_ceiling(path):
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    out = dict(c["books"])
    out.update({f"{b} (text)": n for b, n in (c.get("text") or {}).items()})
    return out


def judge(export, dist, got, ceiling=None):
    bad = []
    if ceiling is not None:
        per = defaultdict(int)
        for page, val in got["math"].items():
            if val:
                per[ceiling_key(page)] += val[1]
        for b, n in sorted(per.items()):
            if n > ceiling.get(b, 0):
                bad.append(("math", b, f"{n} formulas shown as source, the ceiling is {ceiling.get(b, 0)}"))
    for page, val in sorted(got["math"].items()):
        want = formulas((Path(dist) / page).read_text(encoding="utf-8"))
        if val is None:
            bad.append(("math", page, "no math report: the page's scripts did not run"))
            continue
        typeset, source, overflow, notes, equations, macros_used = val
        book = json.loads((Path(export) / "books" / f"{page.split('/')[1]}.json").read_text(encoding="utf-8"))["book"]
        if macros_used is None or json.loads(macros_used) != (book.get("macros") or {}):
            bad.append(("math", page, f"KaTeX was given macros {str(macros_used)[:60]}, the export has "
                                      f"{json.dumps(book.get('macros') or {})[:60]}"))
        # display equations in order: each typeset from its own TeX, or shown as exactly its own source
        src = formulas((Path(dist) / page).read_text(encoding="utf-8"), equations_only=True)
        if len(equations) != len(src) or any(
                (kind == "typeset" and t != aligned(want_t)) or (kind == "source" and t != want_t)
                for (kind, t), want_t in zip(equations, src)):
            first = next((k for k, ((kind, t), w) in enumerate(zip(equations, src))
                          if (kind == "typeset" and t != aligned(w)) or (kind == "source" and t != w)), None)
            bad.append(("math", page, f"{len(equations)} equations drawn for {len(src)} in the HTML; "
                                      f"the first out of place is number {first}"))
        if typeset + source != len(want):
            bad.append(("math", page, f"{typeset} typeset + {source} as source, the HTML holds {len(want)}"))
        # each typeset formula carries its TeX (KaTeX's MathML annotation): each must be one of the page's own
        left = defaultdict(int)
        for t in want:
            left[t] += 1
        strangers = []
        for t in notes:
            if left[t] > 0:
                left[t] -= 1
            else:
                strangers.append(t)
        if len(notes) != typeset or strangers:
            bad.append(("math", page, f"{len(notes)} annotations for {typeset} typeset; "
                                      f"{len(strangers)} not from the page, e.g. {strangers[:1]}"))
        if overflow != 0:
            bad.append(("math", page, f"wider than a {WINDOW.split(',')[0]}px window by {overflow}px"))
    views = graph_views(export)
    for v, val in sorted(got["graph"].items()):
        if val is None:
            bad.append(("graph", v, "no graph report for this view"))
        elif list(val[:2]) != views[v]:
            bad.append(("graph", v, f"drew {val[0]} nodes / {val[1]} links, the export has {views[v][0]} / {views[v][1]}"))
        elif val[2] != view_digest(export, v):
            bad.append(("graph", v, "the right counts, but not the export's nodes, labels, node links or links "
                                    f"(digest {str(val[2])[:12]})"))
    return bad


def controls(export, dist, chromium, jobs, got, ceiling=None):
    """The planted faults, each on its own page or its own copy of a script, in one copy of the site."""
    d = Path(dist)
    chapters = [p for p, v in sorted(got["math"].items()) if "/ch/" in p and v and v[0] > 0
                and 'data-field="latex"' in (d / p).read_text(encoding="utf-8")]
    bad_formula, typeset_x, no_script, too_wide = chapters[0], chapters[1], chapters[-1], chapters[-2]
    rotated = next(p for p in chapters[2:-2] if len(set(formulas((d / p).read_text(encoding="utf-8"), True))) > 1)
    wrong_macros = next(p for p in chapters[2:-2] if p != rotated)
    texts = [p for p, v in sorted(got["math"].items()) if p.endswith("/text/index.html") and v and v[0] > 0
             and '<span class="math inline">' in (d / p).read_text(encoding="utf-8")]
    bad_text = texts[0] if texts else None
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "dist"
        shutil.copytree(dist, copy)

        def edit(rel, old_pattern, new, regex=True):
            f = copy / rel
            t = f.read_text(encoding="utf-8")
            t2 = re.sub(old_pattern, new, t, count=1) if regex else t.replace(old_pattern, new, 1)
            assert t2 != t, (rel, old_pattern)
            f.write_text(t2, encoding="utf-8")

        def script_copy(src, dst, old, new):
            t = (copy / src).read_text(encoding="utf-8")
            assert old in t, (src, old)
            (copy / dst).write_text(t.replace(old, new, 1), encoding="utf-8")

        # 1. a formula KaTeX cannot read: one more shown as source, one fewer typeset
        edit(bad_formula, r'(<code data-field="latex">)[^<]*(</code>)', r"\1\\frac{\2")
        # 1b. the same in a chapter's text, against the text pages' own ceiling
        if bad_text:
            edit(bad_text, r'(<span class="math inline">)\\\(', r"\1\\(\\frac{")
        # 2. a page whose script is gone: no report
        edit(no_script, r'<script src="[./]*site\.js"></script>', "")
        # 3. a site.js that typesets "x" for every equation: the right counts, annotations not from the page
        script_copy("site.js", "site-x.js", "katex.render(aligned(el.textContent)", 'katex.render("x"')
        edit(typeset_x, r'(<script src="[./]*)site\.js(">)', r"\1site-x.js\2")
        # 3b. a site.js that typesets each equation from the next one's TeX: every annotation is the page's own
        script_copy("site.js", "site-rot.js", "katex.render(aligned(el.textContent)",
                    "katex.render(aligned((all[(all.indexOf(el) + 1) % all.length] || el).textContent)")
        rot = (copy / "site-rot.js").read_text(encoding="utf-8").replace(
            '  Array.prototype.forEach.call(document.querySelectorAll(\'[data-field="latex"]\'), function (el) {',
            '  var all = Array.prototype.slice.call(document.querySelectorAll(\'[data-field="latex"]\'));\n'
            '  Array.prototype.forEach.call(document.querySelectorAll(\'[data-field="latex"]\'), function (el) {', 1)
        assert "var all" in rot
        (copy / "site-rot.js").write_text(rot, encoding="utf-8")
        edit(rotated, r'(<script src="[./]*)site\.js(">)', r"\1site-rot.js\2")
        # 3c. a page that hands KaTeX macros the export does not have (one harmless extra, so nothing else changes)
        mt = (copy / wrong_macros).read_text(encoding="utf-8")
        if 'data-macros="' in mt:
            a = mt.index('data-macros="') + len('data-macros="'); b = mt.index('"', a)
            m = json.loads(html.unescape(mt[a:b]))
            m["\\planted"] = "x"
            mt = mt[:a] + html.escape(json.dumps(m, ensure_ascii=False, sort_keys=True), quote=True) + mt[b:]
        else:
            mt = mt.replace("<main>", '<main data-macros="{&quot;\\\\planted&quot;: &quot;x&quot;}">', 1)
        (copy / wrong_macros).write_text(mt, encoding="utf-8")
        # 4. a line nothing can break: the page wider than the window
        edit(too_wide, "</main>", "<p>" + "w" * 3000 + "</p></main>", regex=False)
        # 5. a graph that loses one node and its links (a consistent graph, one node short)
        script_copy("graph.js", "graph-drop.js", "var graph = ForceGraph3D()",
                    "var gone = nodes.pop().id;\n    links = links.filter(function (l) "
                    "{ return l.source !== gone && l.target !== gone; });\n    var graph = ForceGraph3D()")
        # 6. a graph with every count right and a label wrong
        script_copy("graph.js", "graph-label.js", 'return n.kind + ": " + n.name;', 'return n.kind + ": " + n.name + " ";')
        g = (copy / "graph" / "index.html").read_text(encoding="utf-8")
        for name in ("graph-drop.js", "graph-label.js"):
            (copy / "graph" / f"{name[:-3]}.html").write_text(g.replace('src="../graph.js"', f'src="../{name}"'),
                                                             encoding="utf-8")
        planted = run(export, copy, chromium, jobs, views=[], pages=[bad_formula, no_script, typeset_x, too_wide, rotated, wrong_macros]
                      + ([bad_text] if bad_text else []))
        with Server(copy) as base:
            for name in ("graph-drop", "graph-label"):
                r = reports(dump(chromium, base + f"graph/{name}.html", 300, Path(tmp) / f"g-{name}")).get("graph") or {}
                planted["graph"][name] = (int(r["nodes"]), int(r["links"]), r.get("digest")) if "nodes" in r else None
        judged = judge(export, copy, {"math": planted["math"], "graph": {}}, ceiling)
        found = {(k, key) for k, key, _ in judged}
    findings = []
    base_t, base_s = got["math"][bad_formula][:2]
    if planted["math"][bad_formula] is None or planted["math"][bad_formula][:2] != (base_t - 1, base_s + 1):
        findings.append(f"bad formula on {bad_formula}: base {(base_t, base_s)}, planted {planted['math'][bad_formula]}")
    for page, what in ((no_script, "a page without its script"), (typeset_x, "every equation typeset as x"),
                       (too_wide, "a line nothing can break"), (rotated, "each equation typeset from the next")):
        if ("math", page) not in found:
            findings.append(f"{what} ({page}) passed")
    if planted["math"].get(wrong_macros) is None:
        findings.append(f"a page handing KaTeX macros the export does not have ({wrong_macros}): no report, so not judged")
    elif not any(k == "math" and key == wrong_macros and "KaTeX was given macros" in msg for k, key, msg in judged):
        findings.append(f"a page handing KaTeX macros the export does not have ({wrong_macros}) passed")
    want = graph_views(export)["concepts"]
    drop = planted["graph"]["graph-drop"]
    if not drop or drop[0] != want[0] - 1:
        findings.append(f"a graph one node short drew {drop}, the export has {want}")
    lab = planted["graph"]["graph-label"]
    if not lab or list(lab[:2]) != want or lab[2] == view_digest(export, "concepts"):
        findings.append(f"a graph with one label wrong matched the export: {lab}")
    if bad_text:
        base_t, base_s = got["math"][bad_text][:2]
        if planted["math"][bad_text] is None or planted["math"][bad_text][:2] != (base_t - 1, base_s + 1):
            findings.append(f"bad formula in a chapter's text {bad_text}: base {(base_t, base_s)}, "
                            f"planted {planted['math'][bad_text]}")
    else:
        print("browser control 'a bad formula in a chapter's text': NOT RUN, no text page has inline math")
    if ceiling is not None:
        for page in [bad_formula] + ([bad_text] if bad_text else []):
            key = ceiling_key(page)
            merged = dict(got["math"], **{page: planted["math"][page]})
            if not any(k == "math" and kk == key for k, kk, _ in judge(export, dist, {"math": merged, "graph": {}}, ceiling)):
                findings.append(f"one more formula as source in {key} did not trip its ceiling {ceiling.get(key)}")
    if findings:
        print("BROWSER CONTROL FAILED:", *findings, sep="\n  ")
        sys.exit(2)
    print("browser control: RED as planted (a bad formula, over its book's ceiling; the same in a chapter's text, over the "
          "text pages' ceiling; no report without the script; "
          "equations typeset from other text; equations out of order; macros the export does not have; a page too wide; the graph one node short; one "
          "label wrong)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--chromium", required=True)
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--ceiling", help="build/math-ceiling.json")
    a = ap.parse_args()
    ceiling = load_ceiling(a.ceiling) if a.ceiling else None
    got = run(a.export, a.dist, a.chromium, a.jobs)
    if a.control:
        controls(a.export, a.dist, a.chromium, a.jobs, got, ceiling)
    bad = judge(a.export, a.dist, got, ceiling)
    typeset = sum(v[0] for v in got["math"].values() if v)
    source = defaultdict(int)
    for p, v in got["math"].items():
        if v:
            source[ceiling_key(p)] += v[1]
    print(f"browser: {len(got['math'])} pages, {typeset} formulas typeset, {sum(source.values())} shown as source; "
          f"graph views {len(got['graph'])}, concept layer {got['graph'].get('concepts')}, all {got['graph'].get('all')}")
    for b, n in sorted(source.items(), key=lambda kv: -kv[1]):
        if n:
            print(f"  shown as source: {n:4d} {b}")
    for kind, key, why in bad[:20]:
        print(f"  {kind} {key}: {why}")
    if bad:
        print(f"BROWSER RED: {len(bad)}")
        sys.exit(1)
    print("BROWSER GREEN: every page's math is accounted for and every graph view draws the export's counts")


if __name__ == "__main__":
    main()
