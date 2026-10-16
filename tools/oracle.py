"""oracle.py: every unit the export holds is on the built site, once, on the right page, with its content.

    python3 tools/oracle.py EXPORT DIST                      compare; exit 1 on any difference
    python3 tools/oracle.py EXPORT DIST --control [--seed N] also plant faults and require each one red
        [--build "python3 build/site.py --export {export} --out {out} --no-checks"]

Kinds: book, chapter, exercise_set, excerpt, equation, problem, erratum (from the book files), term and relation
(from graph.json and books.json). For each unit the export holds:
  - presence: its id is on the site exactly once (missing, extra and duplicated ids all fail);
  - placement: it is on the page the URL contract gives it (docs/BLUEPRINT.md): a book on the shelf, a chapter
    and an erratum on their book's page, an exercise set, excerpt or equation on the page of the chapter its own
    `chapter` field names, a problem on the page of its exercise set's chapter;
  - content: each data-field inside its element equals the export's, in order (whitespace collapsed): a
    problem's text, each printed answer and each key step; an excerpt's text; an equation's LaTeX and statement;
    an erratum's printed text, correction and context. At least one sentence of an erratum's evidence verbatim
    (the rest may be rewritten for readers). By containment: a chapter's and a book's title, a relation's shared
    concept names;
  - name (terms and relations): the whole text of the element's first child is the term's node name / the other
    book's title;
  - links (terms and relations), exactly: every <a> inside the element as (target resolved against its page, link
    text) against the export's: a term's chapters (with their titles) and its anchor on every other book's terms
    page (with that book's title); a relation's other book (its title) and this book's term for each shared
    concept the book teaches (its name). Nothing missing, nothing extra, nothing twice;
  - a term's own id is its anchor, and it sits in the data-group section of its type;
  - markup (every kind): the unit closed by its own end tag, not inside another unit (a problem in its set is
    the one exception), and for terms and relations no text before the first child.
Stated numbers (data-count): one element, all digits, equal to the export's and tied to what it describes (a
relation's count inside it, a group's inside its section, a book's term count on its page).
Every page: the markup allowlist (docs/BLUEPRINT.md): no element, attribute or stylesheet rule that can hide text,
no <base>, no inline script, a closing </html>; on a terms page the group headings and jump links match the types. Terms are walked from graph.json's taught_in, with each chapter's book taken from the book FILE
that lists it (the build reads graph.json's part_of), so the two walks do not share that assumption.
The export side is read here with its own walk of the JSON; nothing is imported from the build.

Controls (each planted fresh in a temp copy on every run, never kept as files), each must come back red with
exactly the planted findings and nothing else:
  site: delete a problem; delete an erratum; duplicate an erratum; blank a problem's text; drop an erratum's
        evidence; blank a problem whose printed answer repeats its text; blank an erratum's printed text that its
        context holds; move a problem to its book page; delete a term; drop a chapter link from a term; add a wrong
        chapter link to a term; blank a term's name; swap two terms' anchors; move a term to another group; hide
        text inside a term; leave a term unclosed; state a wrong term count; delete a relation; blank a
        relation's other title; drop a shared concept from a relation; swap two relations' counts; state a count
        as a decimal; put text before a term's name; hide a group section; wrap a term in a template; style a
        term's name invisible; hide text with the stylesheet; cut a page off inside its last term; nest an excerpt
        inside another; point a jump link at the wrong group.
  export: drop a problem; drop one taught_in edge of a term taught in two or more chapters of its book; run
        --build on each and compare that site with the TRUE export. And two the build must refuse: a
        problem_form taught_in a chapter; a chapter part_of the wrong book.
A match is reported only after every control came back red as planted.
"""
import argparse
import html
import json
import posixpath
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

KINDS = ("book", "chapter", "exercise_set", "excerpt", "equation", "problem", "erratum", "term", "relation", "text")
# the share-alike books' kinds and their figures (images/<slug>/) are judged by tools/saoracle.py against sa-books,
# named here so nothing else passes unjudged; their pages still meet the markup allowlist below
SA_KINDS = ("sa-book", "sa-page")
# URL contract (docs/BLUEPRINT.md), the parts the link check needs
TERMS_PAGE = "books/{book}/terms/index.html"
# the term types, copied from the blueprint (not imported from the build); a group per type
TERM_TYPES = ("concept", "theorem", "method", "law", "quantity", "unit", "instrument", "experiment", "person")
TERM_LABELS = {"concept": "Concepts", "theorem": "Theorems", "method": "Methods", "law": "Laws", "quantity": "Quantities",
               "unit": "Units", "instrument": "Instruments", "experiment": "Experiments", "person": "People"}
# markup the site never emits; anywhere on a page, each is red (the build hides nothing, so nothing may hide)
FORBIDDEN_TAGS = {"base", "template", "noscript", "iframe", "object", "embed", "style", "frame", "frameset"}
FORBIDDEN_ATTRS = {"hidden", "style", "aria-hidden", "inert"}
NESTING = {("exercise_set", "problem")}
# sideways clipping cuts text off instead of letting it scroll: only the graph's canvas box may clip
CLIP_ALLOWED = {".graph-canvas"}  # the only unit allowed inside another unit
HIDING_CSS = re.compile(r"(?<![\w-])(?:display\s*:\s*none|visibility\s*:|opacity\s*:\s*0|font-size\s*:\s*0|content\s*:"
                        r"|clip(?:-path)?\s*:|text-indent\s*:\s*-)", re.I)


def term_anchor(node_id):
    return "t-" + node_id.replace("/", "-")


# the chapter text pages (docs/BLUEPRINT.md, "The chapter text pages"): the oracle's own copy of what a chapter's
# text_html may hold, written from the census, not imported from build/textpage.py, so the two can disagree
TEXT_TAGS = {"a", "blockquote", "br", "caption", "div", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5",
             "hr", "img", "li", "ol", "p", "section", "span", "strong", "sup", "table", "tbody", "td", "th", "thead",
             "tr", "ul"}
TEXT_IN_ATTRS = {"id", "class", "style", "colspan", "rowspan", "src", "alt", "href", "role", "data-label",
                 "data-latex-placement", "value"}
TEXT_STYLE = re.compile(r"\s*text-align:\s*(?:left|center|right|justify)\s*;?\s*\Z"
                        r"|(?:\s*(?:width|height):\s*\d+(?:\.\d+)?(?:%|in|cm|mm|em|px|pt)\s*(?:;|\Z))+\s*\Z")
# what a text page's article may carry, once written again: these attributes; classes from this list (or ta-*, the
# alignment); every id and fragment with the c- prefix, so no book id can be one the page itself uses
TEXT_OUT_ATTRS = {"id", "class", "href", "src", "alt", "colspan", "rowspan", "value"}
TEXT_OUT_CLASSES = {"math", "inline", "display", "smallcaps", "center", "footnotes", "footnote-ref", "footnote-back",
                    "ta-left", "ta-center", "ta-right", "ta-justify", "tex", "rule-t", "rule-b", "rule-l", "rule-r"}
TEXT_PAGE = re.compile(r"books/([^/]+)/ch/([^/]+)/text/index\.html\Z")
WITHHELD = {"errata": "its book's errata do not yet say which chapter each is in",
            "macros": "its book's macros name the transcription's source"}


class _TextIn(HTMLParser):
    """What is wrong with a chapter's text_html by the oracle's own rules (empty: it may be a page)."""

    def __init__(self, book, export):
        super().__init__(convert_charrefs=True)
        self.book, self.export, self.bad, self.stack, self.ids, self.links, self.data = book, export, [], [], [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in TEXT_TAGS:
            self.bad.append(f"<{tag}>")
        for k, v in attrs:
            v = v or ""
            if k not in TEXT_IN_ATTRS:
                self.bad.append(f"{k}=")
            elif k == "style" and not TEXT_STYLE.match(v):
                self.bad.append(f"style={v[:30]!r}")
            elif k == "value" and not (tag == "li" and re.fullmatch(r"[1-9][0-9]{0,3}", v)):
                self.bad.append(f"value={v[:30]!r} on <{tag}>")
            elif k == "href":
                if not v.startswith("#"):
                    self.bad.append(f"href={v[:30]!r}")
                else:
                    self.links.append(v[1:])
            elif k == "src" and not (v.startswith(f"images/{self.book}/") and ".." not in v.split("/")
                                     and not re.search(r"[%\\?#]", v) and (Path(self.export) / v).is_file()):
                self.bad.append(f"src={v[:30]!r}")
            elif k == "id":
                self.ids.append(v)
        if tag not in ("br", "hr", "img"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("br", "hr", "img"):
            return
        if not self.stack or self.stack[-1] != tag:
            self.bad.append(f"</{tag}> unbalanced")
        else:
            self.stack.pop()

    def handle_data(self, data):
        self.data.append(data)

    def handle_comment(self, data):
        self.bad.append("comment")

    def handle_decl(self, decl):
        self.bad.append("declaration")

    def unknown_decl(self, data):
        self.bad.append("declaration")

    def handle_pi(self, data):
        self.bad.append("processing instruction")


HOLD = Path(__file__).resolve().parent.parent / "build" / "text-hold.json"


def held_reasons():
    hold = json.loads(HOLD.read_text(encoding="utf-8"))
    return set((hold.get("books") or {}).values()) | {hold["unread"]}


def hold_names_check(export, hold=None):
    """{"build/text-hold.json": [findings]}: every book the hold file names (released or held) is a book of the export;
    a name that is none (a typo, a renamed id) would withhold a released book as unread with both sides agreeing."""
    hold = hold if hold is not None else json.loads(HOLD.read_text(encoding="utf-8"))
    books = {b["id"] for b in json.loads((Path(export) / "books.json").read_text(encoding="utf-8"))["books"]}
    bad = [f"names {n}, which is not a book in the export"
           for n in list(hold.get("released") or []) + list(hold.get("books") or {}) if n not in books]
    return {"build/text-hold.json": bad} if bad else {}


def text_expectation(export, d, hold=None):
    """{chapter id: ("page", its text) or ("withheld", "errata" | "macros" | "markup" | "hold:<reason>")} for each
    chapter that has text_html: what the site must do with it, decided here from the export and the review's hold
    list (build/text-hold.json) alone."""
    bid = d["book"]["id"]
    chs = [c for c in d["chapters"] if c.get("text_html")]
    hold = hold if hold is not None else json.loads(HOLD.read_text(encoding="utf-8"))
    held = (hold.get("books") or {}).get(bid)
    if not held and bid not in (hold.get("released") or []):
        held = hold["unread"]
    if held:
        return {c["id"]: ("withheld", "hold:" + held) for c in chs}
    if any(not x.get("chapter") and x.get("printed_in_text") is not False for x in d.get("errata") or []):
        return {c["id"]: ("withheld", "errata") for c in chs}
    if re.search(r"gutenberg", json.dumps(d["book"].get("macros") or {}), re.I):
        return {c["id"]: ("withheld", "macros") for c in chs}
    targets = set()
    parsed = {}
    for c in chs:
        p = _TextIn(bid, export)
        p.feed(c["text_html"])
        p.close()
        parsed[c["id"]] = p
        targets.update(p.links)
    out = {}
    for c in chs:
        p = parsed[c["id"]]
        bad = list(p.bad) + ([f"<{p.stack[-1]}> unclosed"] if p.stack else [])
        if c["text_html"].rfind("<") > c["text_html"].rfind(">"):
            bad.append("ends inside a tag")
        if re.search(r"gutenberg", c["text_html"], re.I):
            bad.append("gutenberg")
        mine = set(p.links) | targets
        dup = [i for i in set(p.ids) if i in mine and p.ids.count(i) > 1]
        if dup:
            bad.append(f"id {dup[0]!r} twice")
        out[c["id"]] = ("withheld", "markup") if bad else ("page", "".join(p.data))
    return out


VOID = {"br", "meta", "link", "img", "hr", "input", "source", "wbr", "area", "base", "col", "embed", "track"}


def norm(s):
    return " ".join(str(s).split())


# a formula in an excerpt's markdown, as the oracle reads it: \$ is an escaped dollar, never a delimiter
ORACLE_MATH = re.compile(r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<!\\)\$(?:\\.|[^$\\])*\$")


def plain_markers(s):
    """An excerpt's words with every star outside a formula set aside, on the export's side and the page's alike:
    the build renders the star runs as emphasis (CommonMark's rule, site.py), and the oracle does not re-run that
    rule; it requires the words to survive, and excerpt_links_check counts the excerpts that still show a star
    against a ceiling, so a renderer that stopped pairing them would go red there (docs/BLUEPRINT.md)."""
    if not isinstance(s, str):
        return s
    out, last = [], 0
    for m in ORACLE_MATH.finditer(s):
        out.append(s[last:m.start()].replace("*", ""))
        out.append(m.group())
        last = m.end()
    out.append(s[last:].replace("*", ""))
    return "".join(out)


def export_units(export):
    """{(kind, id): {"page": rel path, "text": [fragments]}}, plus a count per (kind, id) for duplicates."""
    export = Path(export)
    index = json.loads((export / "books.json").read_text(encoding="utf-8"))
    listed = [b["id"] for b in index["books"]]
    files = sorted(p.stem for p in (export / "books").glob("*.json"))
    if sorted(listed) != files:
        raise SystemExit(f"oracle: books.json lists {sorted(set(listed) - set(files))} without a file, "
                         f"files {sorted(set(files) - set(listed))} unlisted")
    units, counts = {}, defaultdict(int)
    stated = {}  # (page, key) -> the number the page must state

    def add(kind, i, page, *text, evidence=None, anchors=None, lead=None, anchor_id=None, group=None, unit_counts=None,
            fields=None, withheld=None):
        counts[(kind, i)] += 1
        units[(kind, i)] = {"page": page, "text": [norm(t) for t in text if isinstance(t, str) and t.strip()],
                            "evidence": [norm(t) for t in re.split(r"(?<=[.;])\s+", evidence or "") if len(t.strip()) > 20],
                            "anchors": anchors, "lead": norm(lead) if lead is not None else None,
                            "anchor_id": anchor_id, "group": group, "counts": unit_counts or {},
                            "fields": None if fields is None else
                            {k: [norm(v) for v in vs if isinstance(v, str) and v.strip()] for k, vs in fields.items()},
                            "withheld": withheld}
    chapter_book, chapter_label = {}, {}

    for b in listed:
        d = json.loads((export / "books" / f"{b}.json").read_text(encoding="utf-8"))
        bid = d["book"]["id"]
        book_page = f"books/{bid}/index.html"
        chapters = {c["id"] for c in d["chapters"]}

        def ch_page(chapter_id):
            if chapter_id in chapters and chapter_id.startswith(bid + "/"):
                return f"books/{bid}/ch/{chapter_id[len(bid) + 1:]}/index.html"
            return book_page

        add("book", bid, "index.html", d["book"].get("title"))
        if d["book"].get("macros"):  # KaTeX takes these from <main data-macros>: exactly the export's, on its math pages
            want_macros = json.dumps(d["book"]["macros"], sort_keys=True, ensure_ascii=False)
            for page in [book_page] + [f"books/{bid}/ch/{c['id'][len(bid) + 1:]}/index.html" for c in d["chapters"]]:
                stated[(page, "macros")] = want_macros
        for c in d["chapters"]:
            chapter_book[c["id"]] = bid
            chapter_label[c["id"]] = norm(c.get("title") or c.get("number") or c["id"][len(bid) + 1:])
            add("chapter", c["id"], book_page, c.get("title") or c.get("number"))
        set_chapter = {}
        for s in d.get("exercise_sets", []):
            set_chapter[s["id"]] = s.get("chapter")
            add("exercise_set", s["id"], ch_page(s.get("chapter")))
        for x in d.get("excerpts", []):
            add("excerpt", x["id"], ch_page(x.get("chapter")), plain_markers(x.get("markdown")),
                fields={"text": [plain_markers(x.get("markdown"))]})
        for x in d.get("equations", []):
            add("equation", x["id"], ch_page(x.get("chapter")), x.get("latex"),
                fields={"latex": [x.get("latex")], "statement": [x.get("statement")]})
        for p in d.get("problems", []):
            steps = [s for k in p.get("keys") or [] for s in k.get("steps") or []]
            add("problem", p["id"], ch_page(set_chapter.get(p.get("set"))),
                p.get("markdown"), *(p.get("answer_markdown") or []), *steps,
                fields={"text": [p.get("markdown")], "answer": p.get("answer_markdown") or [], "step": steps})
        for cid, (what, val) in sorted(text_expectation(export, d).items()):
            text_page = f"books/{bid}/ch/{cid[len(bid) + 1:]}/text/index.html"
            if what == "page":
                add("text", cid, text_page, fields={"body": [val]})
                if d["book"].get("macros"):
                    stated[(text_page, "macros")] = json.dumps(d["book"]["macros"], sort_keys=True, ensure_ascii=False)
            else:
                add("text", cid, ch_page(cid), withheld=val)
        for x in d.get("errata", []):
            add("erratum", x["id"], book_page, x.get("printed"), x.get("corrected"), x.get("context"),
                evidence=x.get("evidence"),
                fields={"printed": [x.get("printed")], "corrected": [x.get("corrected")], "context": [x.get("context")]})

    # terms: a node of a term type -taught_in-> a chapter; the chapter's book is the book FILE that lists it (not
    # the graph's part_of, which the build reads: two sources, so a disagreement between them shows up red)
    graph = json.loads((export / "graph.json").read_text(encoding="utf-8"))
    node = {n["id"]: n for n in graph["nodes"]}
    taught = defaultdict(lambda: defaultdict(set))  # book -> node -> chapters
    for l in graph["links"]:
        if (l["type"] == "taught_in" and l["target"] in chapter_book
                and node.get(l["source"], {}).get("type") in TERM_TYPES):
            taught[chapter_book[l["target"]]][l["source"]].add(l["target"])
    teaching = defaultdict(set)  # node -> books
    for b, terms in taught.items():
        for n in terms:
            teaching[n].add(b)
    title = {b["id"]: norm(b.get("title") or "") for b in index["books"]}
    for b in listed:
        terms = taught.get(b, {})
        stated[(f"books/{b}/index.html", "terms")] = len(terms)
        for t in TERM_TYPES:
            k = sum(1 for n in terms if node[n]["type"] == t)
            if k:
                stated[(TERMS_PAGE.format(book=b), f"group:{t}")] = k
        for n, chs in terms.items():
            anchors = defaultdict(int)
            for c in chs:
                anchors[(f"books/{b}/ch/{c[len(b) + 1:]}/index.html", chapter_label[c])] += 1
            for o in teaching[n] - {b}:
                anchors[(TERMS_PAGE.format(book=o) + "#" + term_anchor(n), title[o])] += 1
            name = node[n].get("name") or n
            add("term", f"{b}|{n}", TERMS_PAGE.format(book=b), name, anchors=dict(anchors), lead=name,
                anchor_id=term_anchor(n), group=node[n]["type"])
    # relations: one unit per book a relation names, on that book's page
    for r in index.get("relations") or []:
        if len(r["books"]) != 2 or len(set(r["books"])) != 2 or not set(r["books"]) <= set(listed):
            raise SystemExit(f"oracle: relation {r['books']} does not name two books of the shelf")
        for b in r["books"]:
            o = next(x for x in r["books"] if x != b)
            if ("relation", f"{b}~{o}") in units:
                raise SystemExit(f"oracle: the export relates {b} and {o} twice")
            shared = r.get("shared_concepts") or []
            anchors = defaultdict(int)
            anchors[(f"books/{o}/index.html", title[o])] += 1
            for n in shared:
                if n in taught[b]:
                    anchors[(TERMS_PAGE.format(book=b) + "#" + term_anchor(n), norm(node[n].get("name") or n))] += 1
            add("relation", f"{b}~{o}", f"books/{b}/index.html", title[o],
                *[node.get(n, {}).get("name") or n for n in shared], anchors=dict(anchors), lead=title[o],
                unit_counts={"shared": len(shared)})
            units[("relation", f"{b}~{o}")]["shared_order"] = [
                (norm(node.get(n, {}).get("name") or n), n in taught[b]) for n in shared]
    return units, counts, stated


class _Units(HTMLParser):
    """Every element with data-kind, with: the text inside it; each <a> inside it as (href, its text); its own id;
    the text of its first child element and whether text came before it; the data-group around it; the numbers
    stated inside it; whether it nests where it may not or was left unclosed. Per page: the stated numbers outside
    units, each data-group section's heading label, the jump links, and every piece of forbidden markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found, self.counts, self.bad, self.fields = [], [], [], [], []
        self.headings, self.jumps, self.ended = {}, [], False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in FORBIDDEN_TAGS:
            self.bad.append(f"<{tag}>")
        for k in FORBIDDEN_ATTRS & set(a):
            self.bad.append(f"<{tag} {k}>")
        if tag == "script" and "src" not in a:
            self.bad.append("<script> without src")
        if re.search(r"(^|\s)katex", a.get("class") or ""):
            self.bad.append(f"<{tag} class={a['class']!r}>: a vendor stylesheet's class in the built page")
        parent = self.stack[-1] if self.stack else None
        group = a.get("data-group") or (parent["group"] if parent else None)
        first_of = None
        if parent is not None and parent["unit"] is not None and parent["unit"]["first"] is None:
            parent["unit"]["first"] = []
            first_of = parent["unit"]
        anchor = None
        if tag == "a":
            anchor = [a.get("href"), []]
            for e in self.stack:
                if e["unit"] is not None:
                    e["unit"]["anchors"].append(anchor)
            if any(e["tag"] == "nav" and "jump" in (e["class"] or "").split() for e in self.stack):
                self.jumps.append(anchor)
        unit = None
        if "data-kind" in a:
            outer = next((e["unit"] for e in reversed(self.stack) if e["unit"] is not None), None)
            unit = {"kind": a["data-kind"], "id": a.get("data-id"), "text": [], "anchors": [], "id_attr": a.get("id"),
                    "withheld": a.get("data-withheld"),
                    "first": None, "before": False, "group": parent["group"] if parent else None, "counts": [],
                    "nested": outer is not None and (outer["kind"], a["data-kind"]) not in NESTING, "unclosed": False}
            self.found.append(unit)
        fld = None
        if "data-field" in a:
            owner = unit or next((e["unit"] for e in reversed(self.stack) if e["unit"] is not None), None)
            fld = [a["data-field"], [], owner]
            self.fields.append(fld)
        if tag == "main" and a.get("data-macros") is not None:
            try:
                macros = json.dumps(json.loads(a["data-macros"]), sort_keys=True, ensure_ascii=False)
            except ValueError:
                macros = "(not JSON)"
            self.counts.append(["macros", [macros], None, None])
        count = None
        if "data-count" in a:
            owner = next((e["unit"] for e in reversed(self.stack) if e["unit"] is not None), None)
            count = [a["data-count"], [], owner, group]
            self.counts.append(count)
        heading = None
        if tag == "h2" and parent is not None and parent["tag"] == "section" and parent["data_group"]:
            heading = self.headings.setdefault(parent["data_group"], [])
        if tag not in VOID:
            self.stack.append({"tag": tag, "unit": unit, "anchor": anchor, "first_of": first_of, "count": count,
                               "group": group, "class": a.get("class"), "data_group": a.get("data-group"),
                               "heading": heading, "script": tag == "script", "field": fld})

    def handle_endtag(self, tag):
        if tag == "html":
            self.ended = True
        for j in range(len(self.stack) - 1, -1, -1):
            if self.stack[j]["tag"] == tag:
                for e in self.stack[j + 1:]:  # closed only because an outer element closed: the markup is broken
                    if e["unit"] is not None:
                        e["unit"]["unclosed"] = True
                del self.stack[j:]
                return

    def handle_data(self, data):
        if self.stack and self.stack[-1]["script"] and data.strip():
            self.bad.append("text inside <script>")
        top = self.stack[-1] if self.stack else None
        if top is not None and top["unit"] is not None and top["unit"]["first"] is None and data.strip():
            top["unit"]["before"] = True
        for e in self.stack:
            if e["unit"] is not None:
                e["unit"]["text"].append(data)
            if e["anchor"] is not None:
                e["anchor"][1].append(data)
            if e["first_of"] is not None:
                e["first_of"]["first"].append(data)
            if e["count"] is not None:
                e["count"][1].append(data)
            if e["heading"] is not None:
                e["heading"].append(data)
            if e["field"] is not None:
                e["field"][1].append(data)

    def finish(self):
        self.close()
        for e in self.stack:  # still open at the end of the file: the page was cut off
            if e["unit"] is not None:
                e["unit"]["unclosed"] = True
        if not self.ended:
            self.bad.append("no </html>: the page is cut off")


def resolve(page, href):
    """A site-relative path (with #fragment) for an href on page; None for an outside link."""
    if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:|//", href):
        return None
    path, _, frag = href.partition("#")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(page), path)) if path else page
    if path.endswith("/"):
        target += "/index.html"
    return target + ("#" + frag if frag else "")


class _TextOut(HTMLParser):
    """A text page's article as built: each attribute outside TEXT_OUT_ATTRS, each link that leaves the book's text
    pages, each image (its src)."""

    def __init__(self, book, chapter):
        super().__init__(convert_charrefs=True)
        self.book, self.chapter, self.depth, self.bad, self.images = book, chapter, 0, [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and a.get("data-kind") == "text":
            self.depth = 1
            return
        if not self.depth:
            return
        if tag not in VOID:
            self.depth += 1
        if tag not in TEXT_TAGS:
            self.bad.append(f"<{tag}> in a chapter's text")
        for k, v in attrs:
            v = v or ""
            if k not in TEXT_OUT_ATTRS:
                self.bad.append(f"<{tag} {k}=...> in a chapter's text")
            elif k == "value" and not (tag == "li" and re.fullmatch(r"[1-9][0-9]{0,3}", v)):
                self.bad.append(f"value {v[:20]!r} on <{tag}> in a chapter's text")
            elif k == "class" and not set(v.split()) <= TEXT_OUT_CLASSES:
                self.bad.append(f"class {v[:40]!r} in a chapter's text")
            elif k == "id" and not (v.startswith("c-") or re.fullmatch(r"b-[1-9][0-9]*", v)):
                self.bad.append(f"id {v[:40]!r} in a chapter's text, not c- or b-N")
            elif k == "href" and not (re.fullmatch(r"#c-[^\s\\\"<>]+", v)
                                      or re.fullmatch(r"\.\./\.\./[a-z0-9-]+/text/index\.html#c-[^\s\\\"<>]+", v)):
                self.bad.append(f"a link that leaves the book's text pages: {v[:40]!r}")
            elif k == "src":
                prefix = f"../../../../../images/{self.book}/"
                if not v.startswith(prefix) or ".." in v[len(prefix):].split("/"):
                    self.bad.append(f"an image from outside the book's images: {v[:40]!r}")
                else:
                    self.images.append(v[len("../../../../../"):])

    def handle_endtag(self, tag):
        if self.depth and tag not in VOID:
            self.depth -= 1


def text_pages_check(dist, export):
    """{page: [findings]}: what the text pages hold beyond their text, and the images they use."""
    bad, used = defaultdict(list), set()
    for page in sorted(Path(dist).glob("books/*/ch/*/text/index.html")):
        rel = page.relative_to(dist).as_posix()
        book, chapter = TEXT_PAGE.match(rel).groups()
        raw = page.read_text(encoding="utf-8")
        if re.search(r"gutenberg", raw, re.I):
            bad[rel].append('"gutenberg" on a text page')
        p = _TextOut(book, chapter)
        p.feed(raw)
        bad[rel].extend(p.bad)
        for src in p.images:
            used.add(src)
            mine, theirs = Path(dist) / src, Path(export) / src
            if not mine.is_file() or not theirs.is_file() or mine.read_bytes() != theirs.read_bytes():
                bad[rel].append(f"image {src} is not the export's, byte for byte")
    sa = {b.parent.name for b in Path(dist).glob("books/*/index.html") if 'data-kind="sa-book"' in b.read_text(encoding="utf-8")}
    for f in sorted(Path(dist).glob("images/**/*")):
        if f.relative_to(dist).parts[1] in sa:
            continue  # a share-alike book's figure: saoracle.py compares it with sa-books' file
        if f.is_file() and f.relative_to(dist).as_posix() not in used:
            bad[f.relative_to(dist).as_posix()].append("an image no text page uses")
    return bad


# the elements whose edges part two words: a reader sees 1<em>b</em> as the one word 1b, a<br>b as two
PARTS_WORDS = {"p", "div", "li", "ul", "ol", "td", "th", "tr", "table", "tbody", "thead", "br", "blockquote",
               "figure", "figcaption", "caption", "section", "h1", "h2", "h3", "h4", "h5", "hr", "img"}


class _Blocks(HTMLParser):
    """A text page's article as its top-level elements: [(id, [words])], formulas left out. Its own reading, apart
    from the build's textpage.blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.math, self.out = 0, 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and a.get("data-kind") == "text":
            self.depth = 1
            return
        if not self.depth:
            return
        if self.depth == 1 and tag not in VOID:
            self.out.append([a.get("id"), []])
        if self.out and tag in PARTS_WORDS:
            self.out[-1][1].append(" ")
        if tag not in VOID:
            self.depth += 1
            if self.math or (tag == "span" and "math" in (a.get("class") or "").split()):
                self.math += 1

    def handle_endtag(self, tag):
        if self.depth > 1 and tag not in VOID:
            self.depth -= 1
            if self.math:
                self.math -= 1
            if self.out and tag in PARTS_WORDS:
                self.out[-1][1].append(" ")
        elif self.depth == 1 and tag == "article":
            self.depth = 0

    def handle_data(self, data):
        if self.depth > 1 and self.out and not self.math:
            self.out[-1][1].append(data)


def oracle_words(s):
    return re.findall(r"[a-z0-9]+", s.lower())


EXCERPT_CEILING = Path(__file__).resolve().parent.parent / "build" / "excerpt-ceiling.json"


def excerpt_links_check(dist, export):
    """{page: [findings]}: on each chapter page, an excerpt links into its chapter's text exactly when that text page
    exists; where the excerpt's words stand exactly once in that text (all of them, else its first 8), the link names
    the top-level block they begin in, and elsewhere it goes to the page's top; the excerpts linked to the top, and
    those that still show a star, number no more than build/excerpt-ceiling.json allows."""
    bad, unplaced, starred = defaultdict(list), [], []
    md = {}
    for f in sorted((Path(export) / "books").glob("*.json")):
        for x in json.loads(f.read_text(encoding="utf-8"))["excerpts"]:
            md[x["id"]] = x.get("markdown") or ""
    for page in sorted(Path(dist).glob("books/*/ch/*/index.html")):
        rel = page.relative_to(dist).as_posix()
        raw = page.read_text(encoding="utf-8")
        tpage = page.parent / "text" / "index.html"
        blocks = None
        if tpage.is_file():
            b = _Blocks()
            b.feed(tpage.read_text(encoding="utf-8"))
            blocks = [(i, oracle_words("".join(w))) for i, w in b.out]
        # an excerpt's link is in its first line (its location and page), read alone so that a broken nesting,
        # which the unit check reports, is not read here as a second link
        for m in re.finditer(r'<li class="excerpt" data-kind="excerpt" data-id="([^"]+)"[^>]*><p class="loc">(.*?)</p>',
                             raw, re.S):
            xid = html.unescape(m.group(1))
            links = re.findall(r'<a class="intext" href="([^"]*)"', m.group(2))
            quote = re.search(r"<blockquote>(.*?)</blockquote>", raw[m.end():], re.S)
            if quote and "*" in ORACLE_MATH.sub(" ", html.unescape(re.sub(r"<[^>]+>", "", quote.group(1)))):
                starred.append(xid)
            if blocks is None:
                if links:
                    bad[rel].append(f"excerpt {xid} links to a text page that does not exist")
                continue
            if len(links) != 1 or not links[0].startswith("text/index.html"):
                bad[rel].append(f"excerpt {xid}: {len(links)} links into its chapter's text, expected 1")
                continue
            frag = html.unescape(links[0])[len("text/index.html"):]
            # where the excerpt's words stand once in the text (all of them, else its first 8): the block that link
            # must name; where they stand nowhere, or more than once, the link goes to the page's top
            probe_all = oracle_words(ORACLE_MATH.sub(" ", plain_markers(md.get(xid, ""))))
            flat, owner = [], []
            for n, (_, w) in enumerate(blocks):
                flat.extend(w)
                owner.extend([n] * len(w))
            home = None
            for probe in (probe_all, probe_all[:8]):
                if len(probe) < 3:
                    continue
                at = [s for s in range(len(flat) - len(probe) + 1) if flat[s:s + len(probe)] == probe]
                if len(at) == 1:
                    home = blocks[owner[at[0]]][0]
                    break
            if not frag:
                if home is not None:
                    bad[rel].append(f"excerpt {xid} links to its text page's top; its words stand once, in #{home}")
                unplaced.append(xid)
                continue
            frag = frag[1:]
            if sum(1 for i, _ in blocks if i == frag) != 1:
                bad[rel].append(f"excerpt {xid} links to #{frag}, which is not one top-level block of the text")
            elif frag != home:
                bad[rel].append(f"excerpt {xid} links to #{frag}; its words stand once in "
                                f"{'#' + home if home else 'no block'}")
    ceiling = json.loads(EXCERPT_CEILING.read_text(encoding="utf-8"))
    if len(unplaced) > ceiling["unplaced"]:
        bad["build/excerpt-ceiling.json"].append(f"{len(unplaced)} excerpts link to their text page's top, "
                                                 f"the ceiling is {ceiling['unplaced']}")
    if len(starred) > ceiling["stars"]:
        bad["build/excerpt-ceiling.json"].append(f"{len(starred)} excerpts show a star outside a formula, the ceiling "
                                                 f"is {ceiling['stars']} (e.g. {starred[0]})")
    return bad


def scan_links_check(dist, export):
    """{page: [findings]}: every excerpt and problem with a page shows its page label once, in its first line; in a
    book transcribed from a scan (books.json transcription.page_scans) the label is a link (a.pg) to exactly that
    page's scan, and in any other book it is plain text (span.pg) with no link."""
    bad = defaultdict(list)
    index = json.loads((Path(export) / "books.json").read_text(encoding="utf-8"))
    scans = {b["id"]: (b.get("transcription") or {}).get("page_scans") or {} for b in index["books"]}
    rec = {}
    for f in sorted((Path(export) / "books").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for kind in ("excerpts", "problems"):
            for x in d[kind]:
                rec[x["id"]] = (d["book"]["id"], x.get("page"))
    for page in sorted(Path(dist).glob("books/*/**/index.html")):
        rel = page.relative_to(dist).as_posix()
        raw = page.read_text(encoding="utf-8")
        for m in re.finditer(r'<li class="(?:excerpt|problem)" data-kind="(excerpt|problem)" data-id="([^"]+)"[^>]*>'
                             r'<p class="loc">(.*?)</p>', raw, re.S):
            uid = html.unescape(m.group(2))
            if uid not in rec:
                continue  # a unit the export does not hold: the unit check reports it
            bid, pg = rec[uid]
            links = [html.unescape(h) for h in re.findall(r'<a class="pg" href="([^"]*)"', m.group(3))]
            plain = len(re.findall(r'<span class="pg">', m.group(3)))
            want = scans.get(bid, {}).get(str(pg)) if pg else None
            if not pg:
                if links or plain:
                    bad[rel].append(f"{m.group(1)} {uid} shows a page label; its record has no page")
            elif want:
                if links != [want] or plain:
                    bad[rel].append(f"{m.group(1)} {uid}, p. {pg}: its label links to {links or 'nothing'}, "
                                    f"the scan of that page is {want}")
            elif links or plain != 1:
                bad[rel].append(f"{m.group(1)} {uid}, p. {pg}: {len(links)} scan links and {plain} plain labels, "
                                f"expected one plain label (its book links no scan for that page)")
    return bad


def site_units(dist, export=None):
    """({(kind, id): [hit, ...]}, {(page, key): [stated text, ...]}, {page: [markup findings]}); a hit is a dict.
    With the export, the text pages' own checks too (text_pages_check)."""
    out, stated, pages = defaultdict(list), defaultdict(list), defaultdict(list)
    dist = Path(dist)
    if export is not None:
        for rel, found in text_pages_check(dist, export).items():
            pages[rel].extend(found)
        for rel, found in excerpt_links_check(dist, export).items():
            pages[rel].extend(found)
        for rel, found in scan_links_check(dist, export).items():
            pages[rel].extend(found)
        for rel, found in hold_names_check(export).items():
            pages[rel].extend(found)
    for css in sorted(dist.rglob("*.css")):
        if css.relative_to(dist).parts[0] == "vendor":
            continue  # KaTeX's own rules (proven upstream by vendorcheck) style only what KaTeX makes at run time;
            # the rule below keeps any built element out of their reach
        text = css.read_text(encoding="utf-8")
        for m in HIDING_CSS.finditer(text):
            pages[css.relative_to(dist).as_posix()].append(f"a stylesheet rule that can hide text: {m.group()!r}")
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", text, flags=re.S)):
            selector = " ".join(rule.group(1).split())
            for decl in rule.group(2).split(";"):
                # "overflow: hidden" clips both ways; "overflow-x: hidden" or "overflow: hidden auto" clips sideways
                d = " ".join(decl.split()).lower()
                clips = (re.fullmatch(r"overflow-x\s?:\s?(hidden|clip)", d)
                         or re.fullmatch(r"overflow\s?:\s?(hidden|clip)(\s+\S+)?", d))
                if clips and selector not in CLIP_ALLOWED:
                    pages[css.relative_to(dist).as_posix()].append(f"{selector} clips sideways: {d!r}")
    for page in sorted(dist.rglob("*.html")):
        p = _Units()
        p.feed(page.read_text(encoding="utf-8"))
        p.finish()
        rel = page.relative_to(dist).as_posix()
        pages[rel].extend(p.bad)
        for g, text in p.headings.items():
            label = norm("".join(text)).split(" (")[0]
            if g not in TERM_LABELS or label != TERM_LABELS[g]:
                pages[rel].append(f"group {g!r} is headed {label!r}")
        if p.headings or p.jumps:
            jumps = sorted((h or "", norm("".join(t))) for h, t in p.jumps)
            want = sorted((f"#g-{g}", TERM_LABELS.get(g, "?")) for g in p.headings)
            if jumps != want:
                pages[rel].append(f"jump links {jumps[:3]} do not match the groups {want[:3]}")
        for u in p.found:
            if u["kind"] == "excerpt":
                u["text"] = [plain_markers("".join(u["text"]))]
            anchors = defaultdict(int)
            for href, text in u["anchors"]:
                anchors[(resolve(rel, href) if href else "(no href)", norm("".join(text)))] += 1
            out[(u["kind"], u["id"])].append({
                "page": rel, "text": norm("".join(u["text"])), "anchors": dict(anchors), "id_attr": u["id_attr"],
                "first": norm("".join(u["first"] or [])), "before": u["before"], "group": u["group"],
                "nested": u["nested"], "unclosed": u["unclosed"], "counts": defaultdict(list),
                "fields": defaultdict(list), "withheld": u["withheld"]})
            u["hit"] = out[(u["kind"], u["id"])][-1]
        for name, text, owner in p.fields:
            if owner is None:
                pages[rel].append(f"a data-field {name!r} outside every unit")
            else:
                said = "".join(text)
                owner["hit"]["fields"][name].append(norm(plain_markers(said) if owner["kind"] == "excerpt" else said))
        for key, text, owner, group in p.counts:
            if owner is not None:
                owner["hit"]["counts"][key].append(norm("".join(text)))
            elif key == "macros":  # KaTeX gets these bytes: compared exactly, never whitespace-normalized
                stated[(rel, key)].append("".join(text))
            else:
                stated[(rel, f"group:{group}" if key == "group" else key)].append(norm("".join(text)))
    return out, stated, pages


def stated_number(texts):
    """The one number a page states: exactly one element, whose whole text is digits; else None."""
    return int(texts[0]) if len(texts) == 1 and re.fullmatch(r"\d+", texts[0]) else None


def compare(units, counts, site, stated=None, site_stated=None, pages=None):
    """[(kind, id, category, detail)]; category is missing|extra|duplicate|page|content|link|anchor|group|markup|
    unknown-kind, and for a stated number (kind "count", id "page key") missing|extra|count."""
    out = []
    for (kind, i), hits in sorted(site.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if kind in SA_KINDS:
            continue
        if kind not in KINDS:
            out.append((kind, i, "unknown-kind", f"on {hits[0]['page']}"))
        elif (kind, i) not in units:
            out.append((kind, i, "extra", f"on {hits[0]['page']}, not in the export"))
    for (kind, i), want in sorted(units.items()):
        hits = site.get((kind, i), [])
        if not hits:
            out.append((kind, i, "missing", "not on the site"))
            continue
        if len(hits) != counts[(kind, i)]:
            out.append((kind, i, "duplicate", f"{len(hits)} times on the site, {counts[(kind, i)]} in the export"))
        hit = hits[0]
        page, text = hit["page"], hit["text"]
        if hit["nested"] or hit["unclosed"]:
            out.append((kind, i, "markup", "inside another unit" if hit["nested"] else "its element is not closed"))
        if kind == "text" and (want["withheld"] is not None or hit["withheld"] is not None):
            # a chapter's text is a page, or a line on its chapter page saying why not; the oracle decides which
            reason = (want["withheld"][5:] if str(want["withheld"]).startswith("hold:")
                      else WITHHELD.get(want["withheld"]))
            if want["withheld"] is None:
                out.append((kind, i, "withheld", f"withheld ({str(hit['withheld'])[:60]}) where the export makes a page"))
            elif hit["withheld"] is None:
                out.append((kind, i, "withheld", f"a page where it must be withheld ({want['withheld']})"))
            elif page != want["page"] or (reason is not None and hit["withheld"] != reason) or (
                    reason is None and (hit["withheld"] in WITHHELD.values() or hit["withheld"] in held_reasons())) or (
                    hit["text"] != norm(f"The chapter's text is not shown yet: {hit['withheld']}.")):
                out.append((kind, i, "withheld", f"withheld on {page} for {hit['withheld'][:60]!r}, expected "
                                                 f"{want['page']} for {want['withheld']}"))
            continue
        if page != want["page"]:
            out.append((kind, i, "page", f"on {page}, expected {want['page']}"))
        lost = [t for t in want["text"] if t not in text]
        # evidence is rewritten for readers (seat credits), so not every sentence survives verbatim; at
        # least one must, or the evidence was dropped
        # a term's name (a relation's other title) is the whole text of the element's first child: by containment, a
        # short name like "sine" could be found in a chapter title, and by prefix "Bachet" in "Bachet's weights"
        # each rendered field exactly, in order: containment alone passes a blanked problem whose printed answer
        # repeats its text (Hardy ex-xl/1), or a blanked printed text that its context contains
        if want["fields"] is not None:
            for k in sorted(set(want["fields"]) | set(hit["fields"])):
                if want["fields"].get(k, []) != hit["fields"].get(k, []):
                    lost.append(f"(field {k}: the site has {len(hit['fields'].get(k, []))}, the export "
                                f"{len(want['fields'].get(k, []))}, or they differ)")
        elif hit["fields"]:
            lost.append(f"(fields {sorted(hit['fields'])} on a kind that has none)")
        if want["lead"] is not None and hit["first"] != want["lead"]:
            lost.append(f"(the first child says {hit['first'][:40]!r}, the export {want['lead'][:40]!r})")
        if want["lead"] is not None and hit["before"]:
            lost.append("(text comes before the name)")
        if want["evidence"] and not any(t in text for t in want["evidence"]):
            lost.append("(the evidence: none of its sentences is on the site)")
        if lost:
            out.append((kind, i, "content", f"{len(lost)} of {len(want['text'])} texts missing, e.g. {lost[0][:60]!r}"))
        if want["anchors"] is not None and hit["anchors"] != want["anchors"]:
            gone = sorted(set(want["anchors"]) - set(hit["anchors"]))
            more = sorted(set(hit["anchors"]) - set(want["anchors"]))
            twice = sorted(k for k in want["anchors"] if k in hit["anchors"] and hit["anchors"][k] != want["anchors"][k])
            out.append((kind, i, "link", f"{len(gone)} links missing, {len(more)} extra, {len(twice)} miscounted: "
                        f"e.g. {(gone or more or twice)[0]}"))
        if want["anchor_id"] is not None and hit["id_attr"] != want["anchor_id"]:
            out.append((kind, i, "anchor", f"id {hit['id_attr']!r}, expected {want['anchor_id']!r}"))
        if want["group"] is not None and hit["group"] != want["group"]:
            out.append((kind, i, "group", f"under {hit['group']!r}, expected {want['group']!r}"))
        got_counts = {k: stated_number(v) for k, v in hit["counts"].items()}
        if got_counts != want["counts"]:
            out.append((kind, i, "count", f"states {dict(hit['counts'])}, the export has {want['counts']}"))
    if stated is not None:
        for key in sorted(set(stated) | set(site_stated)):
            said = site_stated.get(key, [])
            label = f"{key[0]} {key[1]}"
            if key not in stated:
                out.append(("count", label, "extra", f"the page states {said[0][:60]!r}, the export has no such value"))
            elif not said:
                out.append(("count", label, "missing", f"the export has {stated[key]}, the page does not state it"))
            elif key[1] == "macros":
                if said != [stated[key]]:
                    out.append(("count", label, "macros", f"the page's macros {said[0][:60]!r} are not the export's"))
            elif stated_number(said) != stated[key]:
                out.append(("count", label, "count", f"the page states {said}, the export has {stated[key]}"))
    for page, bad in sorted((pages or {}).items()):
        if bad:
            out.append(("page", page, "markup", f"{len(bad)}: {bad[0]}"))
    return out


def report(units, site):
    per = defaultdict(lambda: [0, 0])
    for kind, _ in units:
        per[kind][0] += 1
    for (kind, _), hits in site.items():
        if kind in KINDS:
            per[kind][1] += len(hits)
    return "  ".join(f"{k} {per[k][0]}/{per[k][1]}" for k in KINDS)


# ---- controls -------------------------------------------------------------------------------------------

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")


def element_span(html, kind, i):
    """(start, end) of the whole element carrying data-kind=kind data-id=i, depth-counted on its tag name."""
    m = re.search(r'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bdata-kind="%s"[^>]*\bdata-id="%s"[^>]*>'
                  % (re.escape(kind), re.escape(i)), html)
    if not m:
        return None
    tag, depth = m.group(1).lower(), 1
    for t in _TAG.finditer(html, m.end()):
        if t.group(2).lower() != tag or t.group(3):
            continue
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return m.start(), t.end()
    return None


def _find(copy, kind, i):
    for page in sorted(copy.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        span = element_span(text, kind, i)
        if span:
            return page, text, span
    raise SystemExit(f"oracle control: could not find {kind} {i} on the site")


def plant_delete(copy, kind, i):
    page, text, (a, b) = _find(copy, kind, i)
    page.write_text(text[:a] + text[b:], encoding="utf-8")


def plant_duplicate(copy, kind, i):
    page, text, (a, b) = _find(copy, kind, i)
    page.write_text(text[:b] + text[a:b] + text[b:], encoding="utf-8")


def plant_blank(copy, kind, i, field="text"):
    """Empty the element's first field of that name (a problem's own text, an erratum's printed text)."""
    page, text, (a, b) = _find(copy, kind, i)
    el = text[a:b]
    new = re.sub(r'(<[a-z]+ [^>]*data-field="%s"[^>]*>)(.*?)(</[a-z]+>)' % field, r"\1\3", el, count=1, flags=re.S)
    assert new != el, f"no text span in {kind} {i}"
    page.write_text(text[:a] + new + text[b:], encoding="utf-8")


def plant_drop_evidence(copy, i):
    page, text, (a, b) = _find(copy, "erratum", i)
    el = text[a:b]
    new = re.sub(r'<p class="ev">.*?</p>', "", el, count=1, flags=re.S)
    assert new != el, f"no evidence line in erratum {i}"
    page.write_text(text[:a] + new + text[b:], encoding="utf-8")


def plant_move(copy, kind, i, to_page):
    page, text, (a, b) = _find(copy, kind, i)
    el = text[a:b]
    page.write_text(text[:a] + text[b:], encoding="utf-8")
    dest = copy / to_page
    d = dest.read_text(encoding="utf-8")
    dest.write_text(d.replace("</main>", f"<ul>{el}</ul></main>", 1), encoding="utf-8")


def drop_problem(victim):
    def mutate(copy):
        book = next(f for f in sorted((copy / "books").glob("*.json")) if victim.startswith(f.stem + "/"))
        d = json.loads(book.read_text(encoding="utf-8"))
        before = len(d["problems"])
        d["problems"] = [p for p in d["problems"] if p["id"] != victim]
        assert len(d["problems"]) == before - 1, victim
        book.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return mutate


def drop_edge(source, target, kind):
    def mutate(copy):
        f = copy / "graph.json"
        g = json.loads(f.read_text(encoding="utf-8"))
        before = len(g["links"])
        g["links"] = [l for l in g["links"] if (l["source"], l["target"], l["type"]) != (source, target, kind)]
        assert len(g["links"]) == before - 1, (source, target)
        f.write_text(json.dumps(g, ensure_ascii=False) + "\n", encoding="utf-8")
    return mutate


def control_export(export, build, mutate, refused=None):
    """Build from a mutated copy of the export. With refused=TEXT the build must refuse, saying TEXT."""
    with tempfile.TemporaryDirectory() as tmp:
        copy, out = Path(tmp) / "export", Path(tmp) / "dist"
        shutil.copytree(export, copy)
        mutate(copy)
        r = subprocess.run([a.format(export=copy, out=out) for a in shlex.split(build)], capture_output=True, text=True)
        if refused is not None:
            said = r.stdout + r.stderr
            if r.returncode == 0 or "REFUSED" not in said or refused not in said or out.exists():
                return f"the build did not refuse as planted (exit {r.returncode}): {said[-200:]!r}"
            return None
        if r.returncode != 0:
            raise SystemExit(f"oracle export control: build failed: {r.stdout[-300:]}{r.stderr[-300:]}")
        return site_units(out, copy)


def add_edge(source_type, target, kind):
    def mutate(copy):
        f = copy / "graph.json"
        g = json.loads(f.read_text(encoding="utf-8"))
        n = next(x for x in g["nodes"] if x["type"] == source_type)
        g["links"].append({"source": n["id"], "target": target, "type": kind})
        f.write_text(json.dumps(g, ensure_ascii=False) + "\n", encoding="utf-8")
    return mutate


def move_chapter(chapter, to_book):
    def mutate(copy):
        f = copy / "graph.json"
        g = json.loads(f.read_text(encoding="utf-8"))
        hit = [l for l in g["links"] if l["type"] == "part_of" and l["source"] == chapter]
        assert len(hit) == 1, chapter
        hit[0]["target"] = to_book
        f.write_text(json.dumps(g, ensure_ascii=False) + "\n", encoding="utf-8")
    return mutate


def plant_unlink(copy, kind, i, prefix):
    """Remove the first <a> inside the element whose href starts with prefix (the text goes with it)."""
    page, text, (a, b) = _find(copy, kind, i)
    el = text[a:b]
    new = re.sub(r'<a href="%s[^"]*">.*?</a>' % re.escape(prefix), "", el, count=1, flags=re.S)
    assert new != el, f"no {prefix} link in {kind} {i}"
    page.write_text(text[:a] + new + text[b:], encoding="utf-8")


def plant_blank_lead(copy, kind, i):
    """Empty the element's leading name (a term's name span, a relation's first link text)."""
    page, text, (a, b) = _find(copy, kind, i)
    el = text[a:b]
    new = re.sub(r'(<(span class="tn"|a href="[^"]*")>)(.*?)(</(span|a)>)', r"\1\4", el, count=1, flags=re.S)
    assert new != el, f"no lead in {kind} {i}"
    page.write_text(text[:a] + new + text[b:], encoding="utf-8")


def plant_in(copy, kind, i, html_text):
    """Insert html_text just before the element's own closing tag."""
    page, text, (a, b) = _find(copy, kind, i)
    close = text.rindex("</", a, b)
    page.write_text(text[:close] + html_text + text[close:], encoding="utf-8")


def plant_swap_ids(copy, x, y):
    page, text, _ = _find(copy, "term", x)
    ix, iy = term_anchor(x.split("|")[1]), term_anchor(y.split("|")[1])
    assert f'id="{ix}"' in text and f'id="{iy}"' in text
    page.write_text(text.replace(f'id="{ix}"', 'id="@@"').replace(f'id="{iy}"', f'id="{ix}"').replace('id="@@"', f'id="{iy}"'),
                    encoding="utf-8")


def plant_regroup(copy, i, to_group):
    page, text, (a, b) = _find(copy, "term", i)
    el = text[a:b]
    text = text[:a] + text[b:]
    m = re.search(r'<section[^>]*data-group="%s"[^>]*>.*?<ul class="terms">' % re.escape(to_group), text, re.S)
    assert m, to_group
    page.write_text(text[:m.end()] + el + text[m.end():], encoding="utf-8")


def plant_count(copy, page_rel, key, delta):
    page = copy / page_rel
    text = page.read_text(encoding="utf-8")
    m = re.search(r'(data-count="%s"[^>]*>)(\d+)' % re.escape(key), text)
    assert m, (page_rel, key)
    page.write_text(text[:m.start(2)] + str(int(m.group(2)) + delta) + text[m.end(2):], encoding="utf-8")


def plant_unclose(copy, i):
    """Drop the term's closing tag, so its next sibling term falls inside it."""
    page, text, (a, b) = _find(copy, "term", i)
    assert text[b:].startswith('<li class="term"'), i
    page.write_text(text[:b - len("</li>")] + text[b:], encoding="utf-8")


def plant_after_article(copy, page_rel, html_text):
    """Insert html_text just inside a text page's article."""
    page = copy / page_rel
    text = page.read_text(encoding="utf-8")
    a = text.index('<article class="text"')
    b = text.index(">", a) + 1
    page.write_text(text[:b] + html_text + text[b:], encoding="utf-8")


def plant_drop_paragraph(copy, page_rel):
    """Remove the article's first paragraph that holds text (a top-level one carries its block id, b-N). The search
    stays inside the article: once top-level paragraphs gained ids, a search for a bare <p> ran on to the footer's,
    and this control passed with nothing planted in the text (2026-10-15)."""
    page = copy / page_rel
    text = page.read_text(encoding="utf-8")
    i = text.index('<article class="text"')
    end = text.index("</article>", i)
    for m in re.finditer(r'<p(?: id="b-[0-9]+")?>', text[i:end]):
        a = i + m.start()
        b = text.index("</p>", a) + len("</p>")
        if re.sub(r"<[^>]+>", "", text[a:b]).strip():
            break
    else:
        raise AssertionError(f"no paragraph with text in {page_rel}'s article")
    assert b <= end, page_rel
    page.write_text(text[:a] + text[b:], encoding="utf-8")


def plant_flip_image(copy, rel):
    f = copy / rel
    data = bytearray(f.read_bytes())
    data[len(data) // 2] ^= 1
    f.write_bytes(bytes(data))


def plant_withhold(copy, chapter_page, text_page, cid):
    """Say a chapter's text is withheld (as the build words it) and take its page away, with its excerpts' links into
    it (as the build would: the withholding alone is what this control plants)."""
    page = copy / chapter_page
    text = page.read_text(encoding="utf-8")
    old = '<p class="read"><a href="text/index.html">Read the chapter\'s text</a></p>'
    assert text.count(old) == 1, chapter_page
    new = (f'<p class="withheld" data-kind="text" data-id="{html.escape(cid)}" data-withheld="no cause">'
           "The chapter's text is not shown yet: no cause.</p>")
    text = re.sub(r' <a class="intext" href="text/index\.html[^"]*">In the text</a>', "", text.replace(old, new))
    page.write_text(text, encoding="utf-8")
    (copy / text_page).unlink()


def plant_unwithhold(copy, chapter_page, from_page, cid):
    """Give a chapter that must be withheld a page: another text page's, with this chapter's id."""
    page = copy / chapter_page
    text = page.read_text(encoding="utf-8")
    text = re.sub(r'<p class="withheld" data-kind="text"[^>]*>.*?</p>',
                  '<p class="read"><a href="text/index.html">Read the chapter\'s text</a></p>', text, count=1, flags=re.S)
    page.write_text(text, encoding="utf-8")
    src = (copy / from_page).read_text(encoding="utf-8")
    src = re.sub(r'(<article class="text" data-kind="text" data-id=")[^"]*', lambda m: m.group(1) + html.escape(cid), src)
    out = copy / chapter_page.replace("/index.html", "/text/index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf-8")


def script_in_text(chapter):
    def mutate(copy):
        book = next(f for f in sorted((copy / "books").glob("*.json")) if chapter.startswith(f.stem + "/"))
        d = json.loads(book.read_text(encoding="utf-8"))
        c = next(c for c in d["chapters"] if c["id"] == chapter)
        c["text_html"] = "<script>x</script>" + c["text_html"]
        book.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return mutate


def plant_emphasis_stars(copy, page_rel, i):
    """An excerpt's first <em>x</em> written back as *x*: the page then shows the marker as text."""
    p = copy / page_rel
    s = p.read_text(encoding="utf-8")
    a, b = element_span(s, "excerpt", i)
    unit = s[a:b]
    m = re.search(r"<em>(.*?)</em>", unit, re.S)
    assert m, f"no emphasis in {i}"
    p.write_text(s[:a] + unit[:m.start()] + "*" + m.group(1) + "*" + unit[m.end():] + s[b:], encoding="utf-8")


def plant_text(copy, page_rel, old, new):
    page = copy / page_rel
    text = page.read_text(encoding="utf-8")
    assert text.count(old) >= 1, (page_rel, old)
    page.write_text(text.replace(old, new, 1), encoding="utf-8")


def plant_macros(copy, page_rel, value):
    """Give a page these macros: replace its data-macros, or add one to a page that has none."""
    page = copy / page_rel
    text = page.read_text(encoding="utf-8")
    if 'data-macros="' in text:
        start = text.index('data-macros="') + len('data-macros="')
        text = text[:start] + value + text[text.index('"', start):]
    else:
        assert "<main>" in text, page_rel
        text = text.replace("<main>", f'<main data-macros="{value}">', 1)
    page.write_text(text, encoding="utf-8")


def plant_macro_space(copy, page_rel):
    """Double one space inside a macro's value: the same macros to a reader, a different definition to KaTeX."""
    import html as _html
    page = copy / page_rel
    text = page.read_text(encoding="utf-8")
    start = text.index('data-macros="') + len('data-macros="')
    end = text.index('"', start)
    macros = json.loads(_html.unescape(text[start:end]))
    spaced = [k for k in sorted(macros) if " " in macros[k]]
    if spaced:
        macros[spaced[0]] = macros[spaced[0]].replace(" ", "  ", 1)
    else:  # no value holds a space: add one, still a different definition to KaTeX
        first = sorted(macros)[0]
        macros[first] = " " + macros[first]
    value = _html.escape(json.dumps(macros, ensure_ascii=False, sort_keys=True), quote=True)
    page.write_text(text[:start] + value + text[end:], encoding="utf-8")


def plant_before_name(copy, i):
    page, text, (a, b) = _find(copy, "term", i)
    el = text[a:b]
    new = el.replace('<span class="tn">', 'x <span class="tn">', 1)
    page.write_text(text[:a] + new + text[b:], encoding="utf-8")


def plant_swap_counts(copy, x, y):
    """Swap the stated shared counts of two relations on one page."""
    page, text, (a, b) = _find(copy, "relation", x)
    _, _, (c, d) = _find(copy, "relation", y)
    get = lambda el: re.search(r'data-count="shared">(\d+)<', el)
    mx, my = get(text[a:b]), get(text[c:d])
    assert mx and my and mx.group(1) != my.group(1), (x, y)
    spans = sorted([(a + mx.start(1), a + mx.end(1), my.group(1)), (c + my.start(1), c + my.end(1), mx.group(1))], reverse=True)
    for start, end, val in spans:
        text = text[:start] + val + text[end:]
    page.write_text(text, encoding="utf-8")


def plant_truncate(copy, i):
    """Cut the page off just after the term's name: the rest of the term and of the page are gone."""
    page, text, (a, b) = _find(copy, "term", i)
    cut = text.index("</span>", a) + len("</span>")
    page.write_text(text[:cut], encoding="utf-8")


def plant_nest(copy, x, y):
    """Move excerpt x inside excerpt y (both on one page)."""
    page, text, (a, b) = _find(copy, "excerpt", x)
    el = text[a:b]
    text = text[:a] + text[b:]
    page.write_text(text, encoding="utf-8")
    page, text, (c, d) = _find(copy, "excerpt", y)
    close = text.rindex("</", c, d)
    page.write_text(text[:close] + el + text[close:], encoding="utf-8")


def run_controls(export, dist, units, counts, stated, build, seed):
    rng = random.Random(seed)
    problems = sorted(i for k, i in units if k == "problem" and units[(k, i)]["text"])
    errata = sorted(i for k, i in units if k == "erratum")
    p1, p2, p3, p4 = rng.sample(problems, 4)
    # the cases containment cannot see: a problem whose printed answer repeats its text, an erratum whose source
    # context contains its printed text
    echo = lambda w, a, b: w["fields"][a] and any(w["fields"][a][0] in x for x in w["fields"][b])
    p5 = rng.choice([i for i in problems if echo(units[("problem", i)], "text", "answer")])
    e4 = rng.choice(sorted(i for k, i in units if k == "erratum" and echo(units[(k, i)], "printed", "context")))
    e1, e2 = rng.sample(errata, 2)
    e3 = rng.choice(sorted(i for k, i in units if k == "erratum" and units[(k, i)]["evidence"]))
    terms = sorted(i for k, i in units if k == "term")
    t1, t2, t3, t5, t9 = rng.sample(terms, 5)
    chapter_links = lambda i: sorted(h for h, _ in units[("term", i)]["anchors"] if "/ch/" in h)
    t4 = rng.choice([i for i in terms if len(chapter_links(i)) >= 2])
    t4_book, t4_node = t4.split("|")
    t4_chapter = t4_book + "/" + chapter_links(t4)[0].split("/ch/")[1].rsplit("/index.html", 1)[0]
    # a chapter of t5's book that does not teach t5, for a wrong link
    b5 = t5.split("|")[0]
    taught5 = set(chapter_links(t5))
    wrong5 = sorted({h for i in terms if i.startswith(b5 + "|") for h in chapter_links(i)} - taught5)[0]
    t6 = rng.choice(terms)
    t6b = rng.choice([i for i in terms if i.split("|")[0] == t6.split("|")[0] and i != t6])
    t7 = rng.choice(terms)
    other_groups = sorted({units[("term", i)]["group"] for i in terms if i.split("|")[0] == t7.split("|")[0]}
                          - {units[("term", i)]["group"] for i in [t7]})
    to7 = rng.choice(other_groups)
    page8 = rng.choice(sorted(k for k in stated if k[1] == "terms"))
    t10, after10 = None, []
    for i in rng.sample(terms, len(terms)):
        page, text, (a, b) = _find(Path(dist), "term", i)
        if text[b:].startswith('<li class="term"'):
            # with t10 unclosed, every later term of its list falls inside it
            t10 = i
            rest = text[b:text.index("</ul>", b)]
            after10 = [html.unescape(x) for x in re.findall(r'data-kind="term" data-id="([^"]+)"', rest)]
            break
    rels = sorted(i for k, i in units if k == "relation")
    r1, r2 = rng.sample(rels, 2)
    def first_linked_unique(i):
        """The relation's first linked shared name is not inside any other text of the relation, so dropping it
        must show as content as well as link."""
        want = units[("relation", i)]
        linked = [n for n, ok in want["shared_order"] if ok]
        others = [want["text"][0]] + [n for n, _ in want["shared_order"]][1:]
        return bool(linked) and want["shared_order"][0] == (linked[0], True) and not any(linked[0] in t for t in others)
    r3 = rng.choice([i for i in rels if first_linked_unique(i)])
    r4 = rng.choice(rels)
    page4 = units[("relation", r4)]["page"]
    r4b = rng.choice([i for i in rels if units[("relation", i)]["page"] == page4
                      and units[("relation", i)]["counts"] != units[("relation", r4)]["counts"]])
    terms_page = lambda i: units[("term", i)]["page"]
    t11 = rng.choice(terms)
    t12 = rng.choice(terms)
    # the last term of a page (to cut the page off inside it)
    last_of = []
    for page in sorted({terms_page(i) for i in terms}):
        ids = re.findall(r'data-kind="term" data-id="([^"]+)"', (Path(dist) / page).read_text(encoding="utf-8"))
        last_of.append(html.unescape(ids[-1]))
    t13 = rng.choice(last_of)
    by_page = defaultdict(list)
    for k, i in units:
        if k == "excerpt":
            by_page[units[(k, i)]["page"]].append(i)
    x1, x2 = rng.sample(rng.choice(sorted(v for v in by_page.values() if len(v) >= 2)), 2)
    tp = rng.choice(sorted({terms_page(i) for i in terms}))
    with_macros = sorted(k[0] for k, v in stated.items() if k[1] == "macros" and json.loads(v))
    space_page = with_macros[0] if with_macros else None
    macro_page = rng.choice(sorted({units[(k, i)]["page"] for k, i in units if k == "equation" and "/ch/" in units[(k, i)]["page"]}))
    groups_on = sorted({units[("term", i)]["group"] for i in terms if terms_page(i) == tp})
    book_of = lambda i: f"books/{i.split('/')[0]}/index.html"
    site_plants = [
        ("delete a problem", lambda c: plant_delete(c, "problem", p1), {("problem", p1, "missing")}),
        ("delete an erratum", lambda c: plant_delete(c, "erratum", e1), {("erratum", e1, "missing")}),
        ("duplicate an erratum", lambda c: plant_duplicate(c, "erratum", e2), {("erratum", e2, "duplicate")}),
        ("blank a problem's text", lambda c: plant_blank(c, "problem", p2), {("problem", p2, "content")}),
        ("drop an erratum's evidence", lambda c: plant_drop_evidence(c, e3), {("erratum", e3, "content")}),
        ("blank a problem whose answer repeats its text", lambda c: plant_blank(c, "problem", p5), {("problem", p5, "content")}),
        ("blank an erratum's printed text that its context holds", lambda c: plant_blank(c, "erratum", e4, "printed"),
         {("erratum", e4, "content")}),
        ("move a problem to its book page", lambda c: plant_move(c, "problem", p3, book_of(p3)), {("problem", p3, "page")}),
        ("delete a term", lambda c: plant_delete(c, "term", t1), {("term", t1, "missing")}),
        ("drop a chapter link from a term", lambda c: plant_unlink(c, "term", t2, "../ch/"), {("term", t2, "link")}),
        ("add a wrong chapter link to a term",
         lambda c: plant_in(c, "term", t5, f'<a href="../ch/{wrong5.split("/ch/")[1]}">x</a>'), {("term", t5, "link")}),
        ("blank a term's name", lambda c: plant_blank_lead(c, "term", t3), {("term", t3, "content")}),
        ("swap two terms' anchors", lambda c: plant_swap_ids(c, t6, t6b), {("term", t6, "anchor"), ("term", t6b, "anchor")}),
        ("move a term to another group", lambda c: plant_regroup(c, t7, to7), {("term", t7, "group")}),
        ("hide text inside a term", lambda c: plant_in(c, "term", t9, "<span hidden>x</span>"), {("page", terms_page(t9), "markup")}),
        ("leave a term unclosed", lambda c: plant_unclose(c, t10),
         {("term", t10, "markup"), ("term", t10, "link")} | {("term", x, "markup") for x in after10}),
        ("state a wrong term count", lambda c: plant_count(c, page8[0], "terms", 1),
         {("count", f"{page8[0]} terms", "count")}),
        ("delete a relation", lambda c: plant_delete(c, "relation", r1), {("relation", r1, "missing")}),
        ("blank a relation's other title", lambda c: plant_blank_lead(c, "relation", r2),
         {("relation", r2, "content"), ("relation", r2, "link")}),
        ("drop a shared concept from a relation", lambda c: plant_unlink(c, "relation", r3, "terms/index.html#"),
         {("relation", r3, "link"), ("relation", r3, "content")}),
        ("swap two relations' counts", lambda c: plant_swap_counts(c, r4, r4b), {("relation", r4, "count"), ("relation", r4b, "count")}),
        ("state a count as a decimal", lambda c: plant_text(c, page8[0], f'data-count="terms">{stated[page8]}<',
                                                             f'data-count="terms">{stated[page8]}.9<'),
         {("count", f"{page8[0]} terms", "count")}),
        ("put text before a term's name", lambda c: plant_before_name(c, t11), {("term", t11, "content")}),
        ("hide a group section", lambda c: plant_text(c, tp, f'data-group="{groups_on[0]}"', f'data-group="{groups_on[0]}" hidden'),
         {("page", tp, "markup")}),
        ("wrap a term in a template", lambda c: plant_in(c, "term", t12, "<template></template>"), {("page", terms_page(t12), "markup")}),
        ("style a term's name invisible", lambda c: plant_text(c, terms_page(t12), '<span class="tn">', '<span class="tn" style="visibility:hidden">'),
         {("page", terms_page(t12), "markup")}),
        ("clip the page sideways", lambda c: plant_text(c, "site.css", "main {", "main { overflow-x: hidden; ")
         if "main {" in (Path(dist) / "site.css").read_text(encoding="utf-8")
         else plant_text(c, "site.css", ".top, main, .foot {", ".top, main, .foot { overflow: hidden; "),
         {("page", "site.css", "markup")}),
        ("hide text with the stylesheet", lambda c: plant_text(c, "site.css", ".tn {", ".tn { display: none; "), {("page", "site.css", "markup")}),
        ("cut a page off inside its last term", lambda c: plant_truncate(c, t13),
         {("term", t13, "markup"), ("term", t13, "link"), ("page", terms_page(t13), "markup")}),
        ("nest an excerpt inside another", lambda c: plant_nest(c, x1, x2), {("excerpt", x1, "markup")}),
        ("give a page macros the export does not", lambda c: plant_macros(c, macro_page, '{&quot;\\\\frac&quot;: &quot;\\\\binom&quot;}'),
         {("count", f"{macro_page} macros", "extra" if (macro_page, "macros") not in stated else "macros")}),
    ] + ([("change only the whitespace in a page's macros", lambda c: plant_macro_space(c, space_page),
           {("count", f"{space_page} macros", "macros")})] if space_page else []) + [
        ("point a jump link at the wrong group", lambda c: plant_text(c, tp, f'<a href="#g-{groups_on[0]}">', '<a href="#g-nowhere">'),
         {("page", tp, "markup")}),
    ]
    texts = sorted(i for k, i in units if k == "text" and units[(k, i)]["withheld"] is None)
    held = sorted(i for k, i in units if k == "text" and units[(k, i)]["withheld"] is not None)
    if texts:
        tx = rng.choice(texts)
        tx_page = units[("text", tx)]["page"]
        tx_ch = tx_page.replace("/text/index.html", "/index.html")
        # a paragraph is dropped from a chapter whose excerpts do not link into its text, so the text check alone
        # answers for it (an excerpt whose home paragraph went would be seen as well, rightly, by excerpt_links_check)
        quiet = [i for i in texts if 'class="intext"' not in (Path(dist) / units[("text", i)]["page"].replace(
            "/text/index.html", "/index.html")).read_text(encoding="utf-8")]
        dx = rng.choice(quiet or texts)
        dx_page = units[("text", dx)]["page"]
        macros_want = lambda rel, cat: {("count", f"{rel} macros", cat)} if (rel, "macros") in stated else set()
        with_img = [i for i in texts if "<img" in (Path(dist) / units[("text", i)]["page"]).read_text(encoding="utf-8")]
        img_page = units[("text", rng.choice(with_img))]["page"] if with_img else None
        img = (re.search(r'<img[^>]*src="\.\./\.\./\.\./\.\./\.\./([^"]+)"', (Path(dist) / img_page).read_text(encoding="utf-8"))
               .group(1) if img_page else None)
        plain = [i for i in texts if "<img" not in (Path(dist) / units[("text", i)]["page"]).read_text(encoding="utf-8")]
        from_page = units[("text", rng.choice(plain))]["page"]
        tw = rng.choice(plain)
        tw_page = units[("text", tw)]["page"]
        tw_ch = tw_page.replace("/text/index.html", "/index.html")
        site_plants += [
            ("drop a paragraph from a chapter's text", lambda c: plant_drop_paragraph(c, dx_page), {("text", dx, "content")}),
            ("put an event handler in a chapter's text", lambda c: plant_after_article(c, tx_page, '<b onclick="x"></b>'),
             {("page", tx_page, "markup")}),
            ("link a chapter's text off the site", lambda c: plant_after_article(c, tx_page, '<a href="https://example.org/"></a>'),
             {("page", tx_page, "markup")}),
            ("put a javascript: link in a chapter's text", lambda c: plant_after_article(c, tx_page, '<a href="javascript:x"></a>'),
             {("page", tx_page, "markup")}),
            ("put an iframe in a chapter's text", lambda c: plant_after_article(c, tx_page, "<iframe></iframe>"),
             {("page", tx_page, "markup")}),
            # a book class or id that is one of the page's own: the stylesheet would clip it, site.js would overwrite it
            ("give a chapter's text a class the site styles", lambda c: plant_after_article(c, tx_page, '<div class="graph-canvas"></div>'),
             {("page", tx_page, "markup")}),
            ("give a chapter's text an id the page uses", lambda c: plant_after_article(c, tx_page, '<span id="math-report"></span>'),
             {("page", tx_page, "markup")}),
            ("put a dialog in a chapter's text", lambda c: plant_after_article(c, tx_page, "<dialog></dialog>"),
             {("page", tx_page, "markup")}),
            ("name the transcription's source on a text page",
             lambda c: plant_text(c, tx_page, '<aside class="errata-here">', '<aside class="errata-here"><p>Project Gutenberg</p>'),
             {("page", tx_page, "markup")}),
            # a chapter without images: withheld, its images would also be unused (the build never copies them)
            ("withhold a chapter's text without cause", lambda c: plant_withhold(c, tw_ch, tw_page, tw),
             {("text", tw, "withheld")} | macros_want(tw_page, "missing")),
        ]
        if img:
            site_plants += [
                # every text page that shows the image sees the change (De Morgan uses one figure in two chapters)
                ("change one bit of a text page's image", lambda c: plant_flip_image(c, img),
                 {("page", units[("text", i)]["page"], "markup") for i in texts
                  if f'src="../../../../../{img}"' in (Path(dist) / units[("text", i)]["page"]).read_text(encoding="utf-8")}),
                ("copy an image no page uses", lambda c: shutil.copyfile(c / img, c / (img + ".planted.png")),
                 {("page", img + ".planted.png", "markup")}),
            ]
        else:
            print("controls on text pages' images: NOT RUN, no text page has an image")
        if held:
            hx = rng.choice(held)
            hx_ch = units[("text", hx)]["page"]
            hx_page = hx_ch.replace("/index.html", "/text/index.html")
            hx_macros = "data-macros" in (Path(dist) / from_page).read_text(encoding="utf-8")
            # its excerpts then have a text page and no link into it, which the excerpt check sees too
            hx_excerpts = 'class="excerpt" data-kind="excerpt"' in (Path(dist) / hx_ch).read_text(encoding="utf-8")
            site_plants.append(("give a page to a chapter that must be withheld",
                                lambda c: plant_unwithhold(c, hx_ch, from_page, hx),
                                {("text", hx, "withheld")} | ({("count", f"{hx_page} macros", "extra")} if hx_macros else set())
                                | ({("page", hx_ch, "markup")} if hx_excerpts else set())))
        else:
            print("control 'give a page to a chapter that must be withheld': NOT RUN, no chapter is withheld")
    else:
        print("controls on chapter text pages: NOT RUN, no chapter has a text page")
    if not space_page:
        print("control 'change only the whitespace in a page's macros': NOT RUN, no book in this export has macros")
    # an excerpt linked to its block (and a next block to move the link to), and an excerpt with emphasis
    placed = []
    for page in sorted(Path(dist).glob("books/*/ch/*/index.html")):
        raw = page.read_text(encoding="utf-8")
        tx_raw = (page.parent / "text" / "index.html")
        for m in re.finditer(r'class="intext" href="text/index\.html#(b-([0-9]+))"', raw):
            if tx_raw.is_file() and f'id="b-{int(m.group(2)) + 1}"' in tx_raw.read_text(encoding="utf-8"):
                placed.append((page.relative_to(dist).as_posix(), m.group(1), f"b-{int(m.group(2)) + 1}"))
    emph, cached = [], {}
    for k, i in sorted(units):
        if k == "excerpt":
            pg = units[(k, i)]["page"]
            s = cached.setdefault(pg, (Path(dist) / pg).read_text(encoding="utf-8"))
            span = element_span(s, "excerpt", i)
            if span and "<em>" in s[span[0]:span[1]]:
                emph.append((pg, i))
    if placed and emph:
        xp, xfrom, xto = rng.choice(placed)
        xt = xp.replace("/index.html", "/text/index.html")
        ep, ei = rng.choice(sorted(emph))
        site_plants += [
            ("move an excerpt's link to the next block", lambda c: plant_text(c, xp, f'#{xfrom}"', f'#{xto}"'),
             {("page", xp, "markup")}),
            ("take an excerpt's target id off its text page",
             lambda c: plant_text(c, xt, f' id="{xfrom}"', ""), {("page", xp, "markup")}),
            # the words survive (stars are set aside in the comparison); the star ceiling is what sees it
            ("show an excerpt's emphasis as stars", lambda c: plant_emphasis_stars(c, ep, ei),
             {("page", "build/excerpt-ceiling.json", "markup")}),
        ]
    else:
        print("controls on excerpt links: NOT RUN, no excerpt links to a block, or none has emphasis")
    # a page label linked to its scan, and one in a book with no scans: point the first at another page's scan, make
    # it plain, and give the second a link
    linked, plain = [], []
    for page in sorted(Path(dist).glob("books/*/**/index.html")):
        raw = page.read_text(encoding="utf-8")
        rel = page.relative_to(dist).as_posix()
        hrefs = re.findall(r'<a class="pg" href="([^"]+)"', raw)
        if hrefs and len(set(hrefs)) > 1:
            linked.append((rel, hrefs))
        elif not hrefs and '<span class="pg">' in raw:
            plain.append(rel)
    if linked and plain:
        lp, hrefs = rng.choice(linked)
        other = next(h for h in hrefs if h != hrefs[0])
        pp = rng.choice(plain)
        site_plants += [
            ("point a page label at another page's scan",
             lambda c: plant_text(c, lp, f'<a class="pg" href="{hrefs[0]}"', f'<a class="pg" href="{other}"'),
             {("page", lp, "markup")}),
            ("make a scan-linked page label plain",
             lambda c: plant_text(c, lp, f'<a class="pg" href="{hrefs[0]}" title="This page in the scan of the printed '
                                      f'book">', '<span class="pg" data-planted="">'), {("page", lp, "markup")}),
            ("link a page label in a book with no scans",
             lambda c: plant_text(c, pp, '<span class="pg">', '<a class="pg" href="https://archive.org/">'),
             {("page", pp, "markup")}),
        ]
    else:
        print("controls on scan links: NOT RUN, no page links two scans, or none has a plain page label")
    # the hold file's names: a released book renamed by one character must be seen (the site refuses it too)
    hold = json.loads(HOLD.read_text(encoding="utf-8"))
    if hold.get("released"):
        typo = dict(hold, released=[hold["released"][0] + "x"] + hold["released"][1:])
        if not hold_names_check(export, typo) or hold_names_check(export):
            print(f"control 'misname a released book in the hold file' (seed {seed}): FAILED")
            sys.exit(2)
        print(f"control 'misname a released book in the hold file' (seed {seed}): RED as planted, {typo['released'][0]}")
    for name, plant, want in site_plants:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dist"
            shutil.copytree(dist, copy)
            plant(copy)
            got = {(k, i, cat) for k, i, cat, _ in compare(units, counts, *site_pair(site_units(copy, export), stated))}
        if got != want:
            print(f"control '{name}' (seed {seed}): FAILED, planted {sorted(want)}, oracle said {sorted(got)[:5]}")
            sys.exit(2)
        print(f"control '{name}' (seed {seed}): RED as planted, {next(iter(want))[1]}")
    export_plants = [
        ("drop a problem from the export", drop_problem(p4), {("problem", p4, "missing")}),
        ("drop a taught_in edge from the export", drop_edge(t4_node, t4_chapter, "taught_in"), {("term", t4, "link")}),
    ] + ([("put a <script> in a chapter's text_html", script_in_text(tx),
           {("text", tx, "withheld")} | macros_want(tx_page, "missing"))] if texts else [])
    for name, mutate, want in export_plants:
        got = {(k, i, cat) for k, i, cat, _ in compare(units, counts, *site_pair(control_export(export, build, mutate), stated))}
        if got != want:
            print(f"control '{name}' (seed {seed}): FAILED, planted {sorted(want)}, oracle said {sorted(got)[:5]}")
            sys.exit(2)
        print(f"control '{name}' (seed {seed}): RED as planted, {next(iter(want))[1]}")
    a_chapter = t4_chapter
    other_book = rng.choice(sorted({i.split("|")[0] for i in terms} - {t4_book}))
    refusals = [
        ("a problem_form taught_in a chapter", add_edge("problem_form", a_chapter, "taught_in"), "taught_in"),
        ("a chapter part_of the wrong book", move_chapter(a_chapter, other_book), "part_of"),
    ]
    for name, mutate, says in refusals:
        bad = control_export(export, build, mutate, refused=says)
        if bad:
            print(f"control 'refuse {name}' (seed {seed}): FAILED, {bad}")
            sys.exit(2)
        print(f"control 'refuse {name}' (seed {seed}): REFUSED as planted, {a_chapter}")


def site_pair(site_and_stated, stated):
    site, site_stated, pages = site_and_stated
    return site, stated, site_stated, pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--build", default="python3 build/site.py --export {export} --out {out} --no-checks")
    a = ap.parse_args()
    units, counts, stated = export_units(a.export)
    if a.control:
        seed = a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 30)
        run_controls(a.export, a.dist, units, counts, stated, a.build, seed)
    site, site_stated, pages = site_units(a.dist, a.export)
    diff = compare(units, counts, site, stated, site_stated, pages)
    print(f"export/site: {report(units, site)}")
    if diff:
        print(f"ORACLE RED: {len(diff)} differences")
        for k, i, cat, why in diff[:30]:
            print(f"  {cat} {k} {i}: {why}")
        sys.exit(1)
    print("ORACLE GREEN: every unit in the export is on the site once, on its page, with its text"
          + (", after every control went red" if a.control else " (controls not run)"))


if __name__ == "__main__":
    main()
