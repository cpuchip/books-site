"""searchcheck.py: the search index holds exactly the site's words, unit by unit. books-site, MIT.

    python3 tools/searchcheck.py DIST [--control]

From the built pages alone, and by its own reading (a tree of each page, each unit's subtree less the units inside
it; build/search.py streams a page with a stack instead), it derives every searchable unit and its words, and
requires of DIST/search/:
- every page of the site but the search page is in pages.json, and every unit in docs.json resolves: its page
  exists and its fragment is declared there exactly once;
- docs.json lists exactly the units derived, of the kinds derived;
- the postings hold, for every unit, exactly the words derived for it (so every word of every page is findable,
  and nothing is findable where it is not);
- each unit's text (what snippets show and phrases are checked against) holds all its words, in order.
--control first plants four faults in a copy of the index (a posting dropped, a stray posting added, a unit
pointing at a missing fragment, a word taken out of a text page's units) and requires each, alone, to be red.
docs/BLUEPRINT.md, "Finding things".
"""
import argparse
import copy
import json
import random
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

WORD = re.compile(r"[a-z0-9]+")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
QUIET = {"script", "style", "code", "output"}  # their text is not a reader's words
BREAKS = {"article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt", "figcaption", "figure",
          "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "img", "li", "main", "nav", "ol", "p",
          "section", "table", "tbody", "td", "th", "thead", "tr", "ul"}


class Node:
    __slots__ = ("tag", "attrs", "kids", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.kids, self.parent = tag, attrs, [], parent


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.at = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.at)
        self.at.kids.append(n)
        if tag not in VOID:
            self.at = n

    def handle_endtag(self, tag):
        x = self.at
        while x is not None and x.tag != tag:
            x = x.parent
        if x is not None and x.parent is not None:
            self.at = x.parent

    def handle_data(self, data):
        self.at.kids.append(data)


def walk(n):
    yield n
    for k in n.kids:
        if isinstance(k, Node):
            yield from walk(k)


def strip_formulas(s):
    """s with each formula written as source replaced by a space, by a scan of its own (build/search.py uses a
    regular expression): \\$ is a dollar; \\( \\) and \\[ \\] close at their first closer; $$ at the next unescaped $$;
    $ at the next unescaped $; an opener that never closes is text."""
    out, i, n = [], 0, len(s)
    while i < n:
        if s.startswith("\\$", i):
            out.append("\\$")
            i += 2
            continue
        for a, b in (("\\(", "\\)"), ("\\[", "\\]")):
            if s.startswith(a, i):
                j = s.find(b, i + 2)
                if j >= 0:
                    out.append(" ")
                    i = j + 2
                    break
        else:
            if s.startswith("$$", i):
                j = i + 2
                while j < n - 1 and not (s[j] == "$" and s[j + 1] == "$" and s[j - 1] != "\\"):
                    j += 1
                if j < n - 1:
                    out.append(" ")
                    i = j + 2
                    continue
            if s[i] == "$":
                k = i + 1
                while k < n and s[k] != "$":
                    k += 2 if s[k] == "\\" else 1
                if k < n:
                    out.append(" ")
                    i = k + 1
                    continue
            out.append(s[i])
            i += 1
            continue
    return "".join(out)


def is_math(n):
    return n.tag == "span" and "math" in (n.attrs.get("class") or "").split()


def words_of(n, units):
    """The words of n's subtree, less the subtrees of the other units, quiet elements and formulas."""
    out = []

    def go(x):
        for k in x.kids:
            if isinstance(k, str):
                out.append(k)
            elif k in units or k.tag in QUIET:
                out.append(" ")
            elif is_math(k):
                out.append(" ")
            else:
                if k.tag in BREAKS:
                    out.append(" ")
                go(k)
                if k.tag in BREAKS:
                    out.append(" ")
    go(n)
    return WORD.findall(strip_formulas("".join(out)).lower())


def derive(dist):
    """{page rel: [(kind, fragment, set of words, [words in order])]}; the page itself is the unit with fragment ""."""
    out = {}
    for f in sorted(Path(dist).rglob("index.html")):
        rel = f.relative_to(dist).as_posix()
        if rel.startswith("search/"):
            continue
        t = _Tree()
        t.feed(f.read_text(encoding="utf-8"))
        t.close()
        mains = [n for n in walk(t.root) if n.tag == "main"]
        units = {}
        for m in mains:
            for n in walk(m):
                if n is m or any(a.tag in QUIET for a in ancestors(n, m)) or n.tag in QUIET:
                    continue
                parent = n.parent
                if parent.tag == "article" and parent.attrs.get("data-kind") == "text" and n.attrs.get("id"):
                    units[n] = ("text", n.attrs["id"])
                elif n.attrs.get("data-kind") and n.attrs.get("id"):
                    units[n] = (n.attrs["data-kind"], n.attrs["id"])
        found = []
        page_words = []
        for m in mains:
            page_words += words_of(m, units)
        if page_words:
            found.append(("page", "", set(page_words), page_words))
        for n, (kind, frag) in units.items():
            w = words_of(n, units)
            if w:
                found.append((kind, frag, set(w), w))
        ids = {}
        for n in walk(t.root):
            if n.attrs.get("id"):
                ids[n.attrs["id"]] = ids.get(n.attrs["id"], 0) + 1
        out[rel] = (found, ids)
    return out


def ancestors(n, stop):
    x = n.parent
    while x is not None and x is not stop:
        yield x
        x = x.parent


def load(dist):
    s = Path(dist) / "search"
    idx = {"pages": json.loads((s / "pages.json").read_text(encoding="utf-8")),
           "docs": json.loads((s / "docs.json").read_text(encoding="utf-8")), "post": {}, "text": []}
    for f in sorted((s / "p").glob("*.json")):
        idx["post"].update(json.loads(f.read_text(encoding="utf-8")))
    n = 0
    while (s / "t" / f"{n}.json").is_file():
        idx["text"].extend(json.loads((s / "t" / f"{n}.json").read_text(encoding="utf-8")))
        n += 1
    return idx


def check(derived, idx):
    """[(category, detail)]"""
    bad = []
    pages, docs = idx["pages"]["pages"], idx["docs"]["docs"]
    kinds = idx["docs"]["kinds"]
    listed = [p[0] for p in pages]
    for rel in sorted(set(derived) - set(listed)):
        bad.append(("page", f"{rel} is not in pages.json"))
    for rel in sorted(set(listed) - set(derived)):
        bad.append(("page", f"pages.json lists {rel}, which the site does not have"))
    have = {}
    for d, (pi, frag, k) in enumerate(docs):
        rel = pages[pi][0]
        if rel not in derived:
            continue
        found, ids = derived[rel]
        if frag and ids.get(frag, 0) != 1:
            bad.append(("fragment", f"unit {d} points at {rel}#{frag}, declared {ids.get(frag, 0)} times there"))
        have[(rel, frag)] = (d, kinds[k])
    want = {(rel, frag): (kind, ws, seq) for rel, (found, _) in derived.items() for kind, frag, ws, seq in found}
    for key in sorted(set(want) - set(have)):
        bad.append(("unit", f"{key[0]}#{key[1]} ({want[key][0]}) is not in docs.json"))
    for key in sorted(set(have) - set(want)):
        bad.append(("unit", f"docs.json has {key[0]}#{key[1]}, which holds no unit of words there"))
    for key in sorted(set(have) & set(want)):
        if have[key][1] != want[key][0]:
            bad.append(("unit", f"{key[0]}#{key[1]} is a {want[key][0]}, docs.json says {have[key][1]}"))
    of_doc = {}
    for w, delta in idx["post"].items():
        at = 0
        for x in delta:
            at += x
            of_doc.setdefault(at, set()).add(w)
    for key in sorted(set(have) & set(want)):
        d = have[key][0]
        got, need = of_doc.get(d, set()), want[key][1]
        if got != need:
            lost, extra = sorted(need - got), sorted(got - need)
            bad.append(("words", f"{key[0]}#{key[1]}: {len(lost)} words not findable (e.g. {lost[:3]}), "
                                 f"{len(extra)} findable that are not there (e.g. {extra[:3]})"))
        text = idx["text"][d] if d < len(idx["text"]) else ""
        if WORD.findall(strip_formulas(text).lower()) != want[key][2]:
            bad.append(("snippet", f"{key[0]}#{key[1]}: its text (for snippets and phrases) does not hold its words "
                                   f"in order"))
    return bad


def control(derived, idx, seed):
    rng = random.Random(seed)
    docs, pages = idx["docs"]["docs"], idx["pages"]["pages"]
    words = sorted(idx["post"])
    w1 = rng.choice([w for w in words if len(idx["post"][w]) > 1])
    w2 = rng.choice(words)
    text_units = [d for d, x in enumerate(docs) if idx["docs"]["kinds"][x[2]] == "text"]
    d3 = rng.choice([d for d, x in enumerate(docs) if x[1]])
    d4 = rng.choice(text_units)

    def drop_posting(i):
        i["post"][w1] = i["post"][w1][1:] if len(i["post"][w1]) == 1 else [i["post"][w1][0] + i["post"][w1][1]] + i["post"][w1][2:]

    def stray(i):
        ids = decode(i["post"][w2])
        free = [d for d in range(len(docs)) if d not in set(ids)]
        ids = sorted(ids + [rng.choice(free)])
        i["post"][w2] = encode(ids)

    def missing_fragment(i):
        i["docs"]["docs"][d3] = [docs[d3][0], docs[d3][1] + "-planted", docs[d3][2]]

    def drop_text_word(i):
        rel = pages[docs[d4][0]][0]
        mine = {d for d, x in enumerate(docs) if pages[x[0]][0] == rel}
        w = sorted(x for x, delta in i["post"].items() if d4 in decode(delta))[0]
        i["post"][w] = encode([d for d in decode(i["post"][w]) if d not in mine])

    plants = [("drop a posting", drop_posting, {"words"}), ("add a stray posting", stray, {"words"}),
              ("point a unit at a missing fragment", missing_fragment, {"fragment", "unit"}),
              ("take a word out of a text page's units", drop_text_word, {"words"})]
    for name, plant, want in plants:
        c = copy.deepcopy(idx)
        plant(c)
        got = {cat for cat, _ in check(derived, c)}
        if not got or not got <= want:
            print(f"SEARCHCHECK CONTROL FAILED: '{name}' (seed {seed}) planted {sorted(want)}, checker said {sorted(got)}")
            sys.exit(2)
        print(f"searchcheck control '{name}' (seed {seed}): RED as planted")


def decode(delta):
    out, at = [], 0
    for x in delta:
        at += x
        out.append(at)
    return out


def encode(ids):
    out, last = [], 0
    for i in ids:
        out.append(i - last)
        last = i
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    derived = derive(a.dist)
    idx = load(a.dist)
    if a.control:
        control(derived, idx, a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 30))
    bad = check(derived, idx)
    for cat, why in bad[:30]:
        print(f"  {cat}: {why}")
    if bad:
        print(f"SEARCHCHECK RED: {len(bad)} findings")
        sys.exit(1)
    n_units = sum(len(f) for f, _ in derived.values())
    print(f"SEARCHCHECK GREEN: {len(derived)} pages, {n_units} units, {len(idx['post'])} words, each unit's words "
          f"exactly its postings" + (", after every control went red" if a.control else " (controls not run)"))


if __name__ == "__main__":
    main()
