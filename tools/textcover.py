"""textcover.py: the words of each chapter's LaTeX source that its text_html (so its page) does not have, as runs.

    python3 tools/textcover.py EXPORT [--book ID] [--top N] [--control]

Review, not a gate. The oracle proves a page holds exactly its text_html; this asks what text_html lost from the
source. Both sides are reduced to lowercase words (math, comments and the arguments of labels, refs, index entries,
graphics and the like taken out; every other command name dropped, its arguments kept). A source word is missing
when the four words starting at it appear nowhere in the page; consecutive missing words make a run, and a run of
RUN words or more is reported (shorter ones are mostly macro arguments the page rightly does not print).
--control removes a paragraph from a copy of one chapter's text_html and requires 80% of its words back in runs.
"""
import argparse
import collections
import html
import json
import re
import sys
from pathlib import Path

RUN = 8
N = 4
# commands whose arguments are not prose: their whole argument goes
NOT_PROSE = r"(?:label|ref|eqref|pageref|index|includegraphics|Graphic|Input|input|cite|hyperref|url|href|" \
            r"phantomsection|pdfbookmark|BookMark|PageSep|DPPageSep|setlength|settowidth|addtolength|vspace|hspace|" \
            r"newcommand|renewcommand|providecommand|def|let|usepackage|documentclass|begin\{tabular\}|SetRunningHeads|" \
            r"SetCenterHeads|SetCornerHeads|SetPageNumbers|fancyhead|fancyfoot|thispagestyle|pagestyle|pagenumbering)"
# an escaped \$ is a dollar sign, not math (the data owner's find, 2026-10-13: "\$26" flipped every later $)
MATH = re.compile(r"(?<!\\)\$\$.*?\$\$|(?<!\\)\$(?:\\.|[^$\\])*\$|\\\[.*?\\\]|\\\(.*?\\\)|"
                  r"\\begin\{(equation|align|gather|multline|eqnarray|flalign|alignat|displaymath|math|array)\*?\}.*?"
                  r"\\end\{\1\*?\}", re.S)
# words (letters, accented ones too) and numbers: a lost section, equation or exercise number is a lost token
WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?|\d+")


def strip_braced(text, i):
    """Index after the braced group starting at text[i] ('{'), or i when there is none."""
    if i >= len(text) or text[i] != "{":
        return i
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "\\":
            continue
        if text[j] == "{" and (j == 0 or text[j - 1] != "\\"):
            depth += 1
        elif text[j] == "}" and text[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(text)


def latex_words(tex, math=False):
    """The source's words (math taken out; with math=True, kept, for counting numbers wherever they stand)."""
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    if not math:
        tex = MATH.sub(" ", tex)
    # environment markers, their options and a table's column spec: not words of the book
    tex = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?(?:\{(?:[^{}]|\{[^{}]*\})*\})?", " ", tex)
    out, i = [], 0
    for m in re.finditer(r"\\" + NOT_PROSE + r"\*?(?:\[[^\]]*\])?", tex):
        if m.start() < i:
            continue
        out.append(tex[i:m.start()])
        j = m.end()
        for _ in range(3):  # up to three braced arguments
            k = strip_braced(tex, j)
            if k == j:
                break
            j = k
        i = j
    out.append(tex[i:])
    tex = "".join(out)
    tex = re.sub(r"\\[A-Za-z@]+\*?|\\.", " ", tex)
    tex = tex.replace("``", " ").replace("''", " ").replace("~", " ")
    return WORD.findall(accents(tex).lower())


def accents(tex):
    r"""\'e, \`a, \"o and the like as the letter they make, so a source word is not split where the page's is whole."""
    return re.sub(r"\\[`'^\"~=.](?:\{([A-Za-z])\}|([A-Za-z]))", lambda m: m.group(1) or m.group(2), tex)


def html_words(text_html, math=False):
    h = text_html if math else re.sub(r'<span class="math[^"]*">.*?</span>', " ", text_html, flags=re.S)
    h = html.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\u2019", "'")
    return WORD.findall(h.lower())


def runs(src, page):
    grams = {tuple(page[i:i + N]) for i in range(len(page) - N + 1)}
    missing = [tuple(src[i:i + N]) not in grams for i in range(len(src) - N + 1)]
    out, i = [], 0
    while i < len(missing):
        if not missing[i]:
            i += 1
            continue
        j = i
        while j < len(missing) and missing[j]:
            j += 1
        length = j - i + N - 1  # the words of the missing windows
        if length >= RUN:
            out.append((length, " ".join(src[i:i + length])))
        i = j
    return out


def chapter(c):
    return runs(latex_words(c.get("text_latex") or ""), html_words(c.get("text_html") or ""))


def control(export):
    words = latex_words(r"A had $d$ dollars, but, after giving \$26 to B, he had one-third as many as B. How many has $x$?")
    if words != ["a", "had", "dollars", "but", "after", "giving", "26", "to", "b", "he", "had", "one", "third", "as",
                 "many", "as", "b", "how", "many", "has"]:
        sys.exit(f"textcover control: FAILED, an escaped dollar read as math: {words}")
    f = sorted((Path(export) / "books").glob("*.json"))[0]
    d = json.loads(f.read_text(encoding="utf-8"))
    c = next(c for c in d["chapters"] if c.get("text_html") and len(re.findall(r"<p>", c["text_html"])) > 5)
    base = chapter(c)
    paras = [m for m in re.finditer(r"<p>(.*?)</p>", c["text_html"], re.S)
             if len(html_words(m.group(1))) >= 30 and "math" not in m.group(1)]
    if not paras:
        sys.exit("textcover control: NOT RUN, no plain paragraph of 30 words")
    p = paras[len(paras) // 2]
    gone = html_words(p.group(1))
    planted = dict(c, text_html=c["text_html"][:p.start()] + c["text_html"][p.end():])
    new = [r for r in chapter(planted) if r not in base]
    # a phrase of the paragraph that recurs elsewhere on the page splits it, so: new runs holding 80% of its words
    found = sum(n for n, _ in new)
    back = collections.Counter(w for _, t in new for w in t.split())
    covered = sum((collections.Counter(gone) & back).values())
    if covered < 0.8 * len(gone):
        sys.exit(f"textcover control: FAILED, a removed paragraph of {len(gone)} words came back as {covered} of its words: {new[:2]}")
    print(f"textcover control: a paragraph of {len(gone)} words removed from {c['id']} came back as {found} words in "
          f"{len(new)} runs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--book")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        control(a.export)
    total_src = total_lost = 0
    for f in sorted((Path(a.export) / "books").glob("*.json")):
        if a.book and f.stem != a.book:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        book_src = book_lost = book_nums = book_nums_lost = 0
        lines = []
        for c in d["chapters"]:
            if not c.get("text_html"):
                continue
            src = latex_words(c.get("text_latex") or "")
            r = chapter(c)
            # numbers wherever they stand, math included on both sides: a number in math on one side and in prose
            # on the other is not lost
            page_nums = collections.Counter(w for w in html_words(c.get("text_html") or "", math=True) if w.isdigit())
            src_nums = collections.Counter(w for w in latex_words(c.get("text_latex") or "", math=True) if w.isdigit())
            book_nums, book_nums_lost = book_nums + sum(src_nums.values()), book_nums_lost + sum((src_nums - page_nums).values())
            lost = sum(n for n, _ in r)
            book_src, book_lost = book_src + len(src), book_lost + lost
            if r:
                biggest = sorted(r, reverse=True)[:a.top]
                lines.append(f"  {c['id'][len(d['book']['id']) + 1:]}: {lost} words in {len(r)} runs; "
                             + " | ".join(f"{n}: {t[:70]!r}" for n, t in biggest))
        total_src, total_lost = total_src + book_src, total_lost + book_lost
        print(f"{f.stem}: {book_lost} of {book_src} source words in runs of {RUN}+ not on the page "
              f"({100 * book_lost / max(book_src, 1):.1f}%); numbers: {book_nums_lost} of {book_nums} not on the page")
        print("\n".join(lines[:40]))
    print(f"TEXT COVER: {total_lost} of {total_src} source words missing in runs ({100 * total_lost / max(total_src, 1):.1f}%)")


if __name__ == "__main__":
    main()
