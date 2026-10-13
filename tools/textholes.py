"""textholes.py: what the converter left behind or dropped in each chapter's text, counted per book. Review, not a gate.

    python3 tools/textholes.py EXPORT [--control]

Math spans are masked first; then each pattern below is counted in the text a reader would see. The patterns were
written from the holes found in pd-books 3ed7925 (a reference dropped from "( )", a section sign with no number, a
book index entry printed as text, alignment TeX outside math); a count is a pointer for the reviewer, not a verdict.
--control plants one of each into a copy of a chapter and requires every pattern to see its plant.
"""
import argparse
import collections
import html
import json
import re
import sys
from pathlib import Path

PATTERNS = [
    ("empty ( )", r"\(\s*\)"),
    ("section sign with no number", r"§\s*(?=[,.;:)\]]|\s+(?:and|or|to)\b)"),
    ("p. with no number", r"\bpp?\.\s*(?=[,.;:)])"),
    ("index entry as text", r"\w@\w|\|[()]"),
    ("alignment TeX outside math", r"&\s*&|\\\\"),
    ("heading begins with a dot", None),
]
MATH = re.compile(r'<span class="math[^"]*">.*?</span>', re.S)


def holes(text_html):
    h = MATH.sub("M", text_html)
    seen = html.unescape(re.sub(r"<[^>]+>", "", h))
    out = collections.Counter()
    for name, pat in PATTERNS:
        if pat is None:
            out[name] = len(re.findall(r"<h\d[^>]*>\s*\.\s", h))
        else:
            out[name] = len(re.findall(pat, seen))
    return out


def census(export):
    per = collections.defaultdict(collections.Counter)
    for f in sorted((Path(export) / "books").glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8"))["chapters"]:
            if c.get("text_html"):
                per[f.stem].update(holes(c["text_html"]))
    return per


def control():
    plants = {"empty ( )": "<p>as in ( ) above</p>", "section sign with no number": "<p>see § .</p>",
              "p. with no number": "<p>(p. ) here</p>", "index entry as text": "<p>Bachet@Bachet's</p>",
              "alignment TeX outside math": "<p>a & & b</p>", "heading begins with a dot": "<h4>. Limits.</h4>"}
    clean = '<p>Clean text, with <span class="math inline">\\(f(x) = (a)\\)</span> and § 4, p. 10.</p>'
    if any(holes(clean).values()):
        sys.exit(f"textholes control: FAILED, clean text counted {dict(+holes(clean))}")
    for name, plant in plants.items():
        got = holes(clean + plant)
        if got[name] != 1 or sum(got.values()) != 1:
            sys.exit(f"textholes control: FAILED, planted {name!r}, counted {dict(+got)}")
    print("textholes control: each pattern saw its plant and nothing else; clean text counted nothing")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        control()
    per = census(a.export)
    total = collections.Counter()
    for book, c in sorted(per.items()):
        total.update(c)
        found = ", ".join(f"{n} {k}" for k, n in sorted(c.items()) if n)
        print(f"{book}: {found or 'none'}")
    print("TEXT HOLES: " + (", ".join(f"{n} {k}" for k, n in sorted(total.items()) if n) or "none"))


if __name__ == "__main__":
    main()
