"""oracle.py: every unit the export holds is on the built site, once, on the right page, with its content.

    python3 tools/oracle.py EXPORT DIST                      compare; exit 1 on any difference
    python3 tools/oracle.py EXPORT DIST --control [--seed N] also plant faults and require each one red
        [--build "python3 build/site.py --export {export} --out {out} --no-checks"]

Kinds: book, chapter, exercise_set, excerpt, equation, problem, erratum. For each unit the export holds:
  - presence: its id is on the site exactly once (missing, extra and duplicated ids all fail);
  - placement: it is on the page the URL contract gives it (docs/BLUEPRINT.md): a book on the shelf, a chapter
    and an erratum on their book's page, an exercise set, excerpt or equation on the page of the chapter its own
    `chapter` field names, a problem on the page of its exercise set's chapter;
  - content: the text the export holds for it appears inside its element (whitespace collapsed): a problem's
    text, each printed answer and each key's steps; an excerpt's text; an equation's LaTeX; an erratum's
    printed and corrected text and its context, and at least one sentence of its evidence verbatim (the rest
    may be rewritten for readers); a chapter's and a book's title.
The export side is read here with its own walk of the JSON; nothing is imported from the build.

Controls (each planted fresh in a temp copy on every run, never kept as files), each must come back red with
exactly the planted finding and nothing else:
  site: delete a problem; delete an erratum; duplicate an erratum; blank a problem's text; drop an erratum's
        evidence; move a problem to its book page.
  export: drop a problem from a copy of the export, run --build, compare that site with the TRUE export.
A match is reported only after every control came back red as planted.
"""
import argparse
import json
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

KINDS = ("book", "chapter", "exercise_set", "excerpt", "equation", "problem", "erratum")
VOID = {"br", "meta", "link", "img", "hr", "input", "source", "wbr", "area", "base", "col", "embed", "track"}


def norm(s):
    return " ".join(str(s).split())


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

    def add(kind, i, page, *text, evidence=None):
        counts[(kind, i)] += 1
        units[(kind, i)] = {"page": page, "text": [norm(t) for t in text if isinstance(t, str) and t.strip()],
                            "evidence": [norm(t) for t in re.split(r"(?<=[.;])\s+", evidence or "") if len(t.strip()) > 20]}

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
        for c in d["chapters"]:
            add("chapter", c["id"], book_page, c.get("title") or c.get("number"))
        set_chapter = {}
        for s in d.get("exercise_sets", []):
            set_chapter[s["id"]] = s.get("chapter")
            add("exercise_set", s["id"], ch_page(s.get("chapter")))
        for x in d.get("excerpts", []):
            add("excerpt", x["id"], ch_page(x.get("chapter")), x.get("markdown"))
        for x in d.get("equations", []):
            add("equation", x["id"], ch_page(x.get("chapter")), x.get("latex"))
        for p in d.get("problems", []):
            steps = [s for k in p.get("keys") or [] for s in k.get("steps") or []]
            add("problem", p["id"], ch_page(set_chapter.get(p.get("set"))),
                p.get("markdown"), *(p.get("answer_markdown") or []), *steps)
        for x in d.get("errata", []):
            add("erratum", x["id"], book_page, x.get("printed"), x.get("corrected"), x.get("context"),
                evidence=x.get("evidence"))
    return units, counts


class _Units(HTMLParser):
    """Every element with data-kind: (kind, id, the text inside it)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        unit = None
        if "data-kind" in a:
            unit = [a["data-kind"], a.get("data-id"), []]
            self.found.append(unit)
        if tag not in VOID:
            self.stack.append((tag, unit))

    def handle_endtag(self, tag):
        for j in range(len(self.stack) - 1, -1, -1):
            if self.stack[j][0] == tag:
                del self.stack[j:]
                return

    def handle_data(self, data):
        for _, unit in self.stack:
            if unit is not None:
                unit[2].append(data)


def site_units(dist):
    """{(kind, id): [(page, text), ...]}"""
    out = defaultdict(list)
    dist = Path(dist)
    for page in sorted(dist.rglob("*.html")):
        p = _Units()
        p.feed(page.read_text(encoding="utf-8"))
        rel = page.relative_to(dist).as_posix()
        for kind, i, text in p.found:
            out[(kind, i)].append((rel, norm("".join(text))))
    return out


def compare(units, counts, site):
    """[(kind, id, category, detail)]; category is missing|extra|duplicate|page|content|unknown-kind."""
    out = []
    for (kind, i), hits in sorted(site.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if kind not in KINDS:
            out.append((kind, i, "unknown-kind", f"on {hits[0][0]}"))
        elif (kind, i) not in units:
            out.append((kind, i, "extra", f"on {hits[0][0]}, not in the export"))
    for (kind, i), want in sorted(units.items()):
        hits = site.get((kind, i), [])
        if not hits:
            out.append((kind, i, "missing", "not on the site"))
            continue
        if len(hits) != counts[(kind, i)]:
            out.append((kind, i, "duplicate", f"{len(hits)} times on the site, {counts[(kind, i)]} in the export"))
        page, text = hits[0]
        if page != want["page"]:
            out.append((kind, i, "page", f"on {page}, expected {want['page']}"))
        lost = [t for t in want["text"] if t not in text]
        # evidence is rewritten for readers (seat credits), so not every sentence survives verbatim; at
        # least one must, or the evidence was dropped
        if want["evidence"] and not any(t in text for t in want["evidence"]):
            lost.append("(the evidence: none of its sentences is on the site)")
        if lost:
            out.append((kind, i, "content", f"{len(lost)} of {len(want['text'])} texts missing, e.g. {lost[0][:60]!r}"))
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


def plant_blank(copy, kind, i):
    """Empty the first text span inside the element (the problem's own text)."""
    page, text, (a, b) = _find(copy, kind, i)
    el = text[a:b]
    new = re.sub(r'(<span class="tx">)(.*?)(</span>)', r"\1\3", el, count=1, flags=re.S)
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


def control_export(export, units, counts, build, victim):
    with tempfile.TemporaryDirectory() as tmp:
        copy, out = Path(tmp) / "export", Path(tmp) / "dist"
        shutil.copytree(export, copy)
        book = next(f for f in sorted((copy / "books").glob("*.json")) if victim.startswith(f.stem + "/"))
        d = json.loads(book.read_text(encoding="utf-8"))
        before = len(d["problems"])
        d["problems"] = [p for p in d["problems"] if p["id"] != victim]
        assert len(d["problems"]) == before - 1, victim
        book.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        r = subprocess.run([a.format(export=copy, out=out) for a in shlex.split(build)], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"oracle export control: build failed: {r.stdout[-300:]}{r.stderr[-300:]}")
        return compare(units, counts, site_units(out))


def run_controls(export, dist, units, counts, build, seed):
    rng = random.Random(seed)
    problems = sorted(i for k, i in units if k == "problem" and units[(k, i)]["text"])
    errata = sorted(i for k, i in units if k == "erratum")
    p1, p2, p3, p4 = rng.sample(problems, 4)
    e1, e2 = rng.sample(errata, 2)
    e3 = rng.choice(sorted(i for k, i in units if k == "erratum" and units[(k, i)]["evidence"]))
    book_of = lambda i: f"books/{i.split('/')[0]}/index.html"
    site_plants = [
        ("delete a problem", lambda c: plant_delete(c, "problem", p1), {("problem", p1, "missing")}),
        ("delete an erratum", lambda c: plant_delete(c, "erratum", e1), {("erratum", e1, "missing")}),
        ("duplicate an erratum", lambda c: plant_duplicate(c, "erratum", e2), {("erratum", e2, "duplicate")}),
        ("blank a problem's text", lambda c: plant_blank(c, "problem", p2), {("problem", p2, "content")}),
        ("drop an erratum's evidence", lambda c: plant_drop_evidence(c, e3), {("erratum", e3, "content")}),
        ("move a problem to its book page", lambda c: plant_move(c, "problem", p3, book_of(p3)), {("problem", p3, "page")}),
    ]
    for name, plant, want in site_plants:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dist"
            shutil.copytree(dist, copy)
            plant(copy)
            got = {(k, i, cat) for k, i, cat, _ in compare(units, counts, site_units(copy))}
        if got != want:
            print(f"control '{name}' (seed {seed}): FAILED, planted {sorted(want)}, oracle said {sorted(got)[:5]}")
            sys.exit(2)
        print(f"control '{name}' (seed {seed}): RED as planted, {next(iter(want))[1]}")
    got = {(k, i, cat) for k, i, cat, _ in control_export(export, units, counts, build, p4)}
    if got != {("problem", p4, "missing")}:
        print(f"control 'drop a problem from the export' (seed {seed}): FAILED, planted {p4}, oracle said {sorted(got)[:5]}")
        sys.exit(2)
    print(f"control 'drop a problem from the export' (seed {seed}): RED as planted, {p4}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--build", default="python3 build/site.py --export {export} --out {out} --no-checks")
    a = ap.parse_args()
    units, counts = export_units(a.export)
    if a.control:
        seed = a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 30)
        run_controls(a.export, a.dist, units, counts, a.build, seed)
    site = site_units(a.dist)
    diff = compare(units, counts, site)
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
