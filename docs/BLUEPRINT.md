# books-site blueprint

The contract for the site and the checks that judge it. Written 2026-10-10, before any page code.

## Input

`cpuchip/pd-books` (PUBLIC, CC0 data), pinned by commit in `pd-books.pin`. The build reads only
`export/` at that commit:

- `export/books.json`: the index (schema_version, generated_from, node_types, edge_types, books, relations).
- `export/books/<slug>.json`: one per book (chapters, excerpts, equations, exercise_sets, problems,
  errata_statuses, errata).
- `export/graph.json`: the concept graph (nodes, links).

Census at b3c614f (the export side of the oracle): 15 books, 235 chapters, 5,027 problems (341 with
keys), 135 errata, graph 19,904 nodes and 58,517 links.
Census at 3ed7925 (pinned 2026-10-13, the export regenerated on sound hardware after a memory fault on the box
that builds it): 236 chapters (Boyden's ALGEBRAIC NOTATION is its own chapter now), graph 19,912 nodes and
58,592 links; problems, keys and errata unchanged in number.

## Refusal (the build stops, writes nothing to dist/)

1. pd-books' own `tools/check_only.py export` fails (the same checks publish_shelf.py applies).
2. `schema_version` is not one this build knows (1).
3. The books listed in `books.json` and the files in `export/books/` differ.
4. graph.json places a chapter (`part_of`) in another book than the book file that lists it; a `taught_in` link
   starts at a node that is not a term type; a relation does not name two books of the shelf, or names a pair
   twice. (Each is a control: the oracle plants the first two and requires the refusal.)
5. Any check below fails on the built site.

## Output (static files, no server code)

- `/` the shelf: every book with title, author, year and counts.
- `/books/<slug>/` provenance and licence (the transcription's source, URL, release date and its
  licence sentence quoted from the export), the chapter list, every erratum with its evidence.
- `/books/<slug>/ch/<n>/` one chapter: its excerpts, equations, exercise sets and every problem in
  them with the printed answer, the check verdict, and STU-32 keys where the export has them.
- Anything in a book file that no chapter lists goes in an "elsewhere in the book" section on the
  book page, so nothing drops silently.
- `/books/<slug>/terms/` the book's index of terms: every concept-layer node (concept, theorem, method, law,
  quantity, unit, instrument, experiment, person) that the graph says is `taught_in` one of the book's chapters,
  with its type, the chapters (linked), and the other books whose chapters teach it (linked to their term).
- The book page also lists its related books: every `books.json` relation that names the book, with the other
  book linked and the relation's `shared_concepts` exactly as the export gives them (linked to this book's
  terms where the term is there, plain text where not).
- `/graph/` the concept graph in 3D (library pending Michael's yes; see below).
- Every rendered unit carries `data-kind` and `data-id` (the export's id), which is what the oracle reads.

## Outward rules the build enforces

- No seat names. `found_by` is never rendered; the credit line comes from `kind` and `status`
  ("confirmed against the scan", with the scan linked). Seat clauses inside `evidence` are rewritten
  by one table in `build/neutral.py`. The verbatim fields stay in pd-books where they are CC0.
- No em-dashes, no session URLs.
- Nothing hosted without the right to host it: scans are linked to their archive, never copied
  (pd-books' evidence crops stay in pd-books, linked). Full book text only as the ruling below allows.

## The oracle (each check plants its own faults on every run and must see them red first)

1. **Every unit, once, on its page, with its text.** `tools/oracle.py EXPORT DIST` reads the export with its
   own walk (nothing imported from the build) and every `data-kind`/`data-id` element of the built HTML with the
   text inside it. Kinds: book, chapter, exercise_set, excerpt, equation, problem, erratum. Per unit:
   presence (exactly as many times as the export holds it), placement (the URL contract below), content: each
   rendered field (`data-field`) equal, in order, to the export's (the problem's text, each printed answer and
   each key step; the excerpt's text; the equation's LaTeX and statement; the erratum's printed text, correction
   and source context), at least one evidence sentence verbatim (the rest may be rewritten for readers), and the
   titles by containment. Exact fields, not containment, because 61 problems print an answer that repeats their
   text and 9 errata quote their printed text in their context: blanking either passed a containment check
   (found 2026-10-10 by a random control seed, Hardy ex-xl/1). Seven controls: delete a problem, delete an erratum,
   duplicate an erratum, blank a problem's text, drop an erratum's evidence, move a problem to the wrong page,
   and drop a problem from a copy of the export and rebuild. Each must come back with exactly its planted
   finding.
   Two kinds added 2026-10-10 (unit 2), read from graph.json and books.json with the oracle's own walk:
   - `term`, id `<book>|<node id>`: one per (book, node) pair where the node is a term type and has a `taught_in`
     link to a chapter that the book's FILE lists (the build reads the graph's `part_of`; two sources, so they
     must agree). Page `books/<book>/terms/index.html`. Name: the whole text of the element's first child.
     Links, exactly (every `<a>` inside it as (target resolved against its page, link text), nothing missing,
     nothing extra, nothing twice): each chapter that teaches it with the chapter's title, and its anchor on every
     other book's terms page with that book's title. Its own `id` is its anchor. It sits inside the `data-group`
     section of its type.
   - `relation`, id `<book>~<other>`: one per relation per book it names, so each relation is on both books'
     pages. Page `books/<book>/index.html`. Name (first child): the other book's title. Content: each shared
     concept's node name. Links, exactly: the other book's page with its title, and this book's term with its
     name for each shared concept the book teaches.
   - Stated numbers (`data-count`), each one element whose whole text is digits, equal to the export's and tied
     to what it describes: a relation's shared-term count inside the relation, each group's count inside its
     `data-group` section, a book's term count on its page.
   - Every kind: a unit is closed by its own end tag (a page cut off inside a unit is red) and is not inside
     another unit (a problem inside its exercise set is the one nesting allowed); a term's or relation's first
     child has no text before it.
   - Every page (the markup allowlist): the site hides nothing, so nothing on any page may hide. Red anywhere:
     `<base>`, `<template>`, `<noscript>`, `<style>`, `<iframe>`, `<object>`, `<embed>`, a `<script>` without
     `src` or with text inside, the attributes `hidden`, `style`, `aria-hidden`, `inert`, a stylesheet rule that
     can hide text (display:none, visibility, opacity 0, font-size 0, content, clip, negative text-indent), and
     a page with no `</html>`. On a terms page, each group's heading is its type's label and the jump links are
     exactly one per group, labelled the same.
   Controls for these (on top of the seven above): delete a term; drop a chapter link from a term; add a wrong
   chapter link to a term; blank a term's name; put text before a term's name; swap two terms' anchors; move a
   term to another group; leave a term unclosed; cut a page off inside its last term; nest an excerpt inside
   another; state a wrong term count; state a count as a decimal; delete a relation; blank a relation's other
   title; drop a shared concept from a relation (one whose name is in no other text of it, so content and link
   must both fire); swap two relations' counts; hide text inside a term; hide a group section; wrap a term in a
   template; style a term's name invisible; hide text with the stylesheet; point a jump link at the wrong group;
   drop one `taught_in` edge from a copy of graph.json (a term taught in two or more chapters) and rebuild, which
   must come back as exactly that term's link finding; and the two refusals under "Refusal" 4. Each is
   required to come back with exactly its planted findings. Removing the shared-name check, or narrowing the
   hiding rule to the `hidden` attribute, makes a control fail (checked 2026-10-10 on broken copies of the oracle).
   Two more for the fields: blank a problem whose printed answer repeats its text; blank an erratum's printed text
   that its context holds. One for the macros: change only the whitespace inside one macro's value, which must be
   red, because KaTeX receives those bytes (it runs when the export has macros, and the run says NOT RUN when it
   has none). 35 in all, plus the two refusals; each run prints every control by name.
2. **Links.** `tools/linkcheck.py DIST`: every internal href and src names a file (and fragment) in dist; an
   empty href or a bare `#` fails; every page is reachable from the shelf; every external URL answers 2xx/3xx
   (`--offline` for development only, and the build's last line says so). Controls: a missing file, a missing
   fragment, an empty link, an orphan page.
3. **Graph.** `tools/graphcheck.py`: the site's graph file holds every node (id, type, name) and link (source,
   target, type) of graph.json and states the same counts. Controls: a renamed node; a removed node and link.
   The browser half (the 3D view holds those counts after load) is unit 3.
4. **Outward.** `tools/outward.py`: every text node and attribute of every page, every served text file, and
   every graph node name. Exempt only: text quoted from the book (problem text and answers, excerpts, equation
   LaTeX, an erratum's printed text and source context, titles, the licence sentence) and the exact strings in
   `tools/outward-allow.txt`. Fails on any roster name (`tools/roster.txt`) or an em-dash in checked text, and
   anywhere (ids and links included) on a claude.ai link, a private or mesh IPv4 address, a hostname under an
   internal suffix, a home-directory path, or a token of a known shape. Controls: seat names in an erratum
   class, in evidence (hyphenated) and in a graph node; an em-dash in a correction; a claude.ai link; a private
   address in a link; a local path in evidence; an internal hostname in a graph node; a token in site.js.

**URL contract** (the oracle's placement check reads it from this list, not from the build):
`index.html` lists books; `books/<book>/index.html` holds the book's chapters list and errata;
`books/<book>/ch/<chapter id without the book prefix>/index.html` holds the exercise sets, excerpts and
equations whose `chapter` field names that chapter, and the problems of those sets. Anything whose chapter is
not in the book goes on the book page. `books/<book>/terms/index.html` holds the book's terms, each with the
anchor `t-<node id with / replaced by ->`; a book's relations are on `books/<book>/index.html`.

**Known limits** (reviewed 2026-10-10 by three fresh-eyes passes: five false greens in the first version,
fourteen in unit 2's first draft of the term and relation checks, and ten in its second draft, every one
reproduced on the real tools and red now under the checks above). The oracle guards against a build that loses,
misplaces or garbles the export; hostile markup is shut out by the allowlist above, not by modelling a browser:
- Fields the site does not render are not checked: equation `name`/`symbols`, `answer_latex`, `judge_why`,
  a relation's `shared_problem_forms` and `prerequisite_edges`, key provenance beyond the firmware pin.
  Rendering one of them means adding it to the oracle.
- Node types and edges outside `taught_in` (prerequisite_of, uses, related_to and the rest) are not on the
  term pages; they belong to the graph view (unit 3; the libraries are approved).
- A relation's `shared_concepts` and the intersection of its two books' terms agree for 99 of the 100 pairs at
  b3c614f; Ball and Hardy differ by concept/cissoid-of-diocles. The data owner confirmed the graph is right and
  the relation wrong (two case-variant entities merged into one export id, and the relations loop paired them
  apart; fixed for the next export). Until the repin the site shows each as its own field gives it, so Ball's
  and Hardy's pages list 48 shared terms while their term indexes share 49.
- A colour that matches the background, or a rule in a stylesheet the site does not serve, is not seen.
- A shared concept that the book does not teach is plain text, checked by containment only (none at b3c614f).
- The one relation with no shared terms (Blackburn and Boyden) says only "0 shared terms recorded"; the export
  relates them by one `prerequisite_edges` entry, which the site does not interpret.
- linkcheck reads href, src and the url() of served stylesheets; the build emits no srcset, poster or action.
- Text fields are shown as text with their math typeset: the export's Markdown emphasis (`*constants*`) shows
  as asterisks. Rendering Markdown needs either a library (Michael's to approve) or a renderer of our own, and
  then an oracle for what it may change.
- The browser check runs where a Chromium binary is (the Linux rehearsal), not in the Dokploy build; the
  build's last line says whether it ran.
- The annotation check proves each typeset formula came from its page's own TeX (display equations in page
  order), not that KaTeX drew it rightly; KaTeX is trusted as published (byte-identical, checked).
- The graph check proves the data handed to the renderer (counts and a digest of every node's id, label and
  link and every link's ends), not the pixels: a script that set nodeVisibility(false) would pass. Three ways to
  read what was drawn (three.js's render counters after two animation frames, a synchronous render, refresh()
  then render) were tried on 2026-10-10 and none is deterministic under headless virtual time: frames come at
  random and a synchronous render draws nothing before the library's deferred build. The rehearsal's
  screenshots are the check on pixels.
- Our own scripts are trusted not to lie about themselves: site.js reports the macros it handed to KaTeX
  (checked against the export) and the tap names a node through the digested label and link, but a site.js
  that hard-coded other macros, or a tap handler rewritten to name another node, would pass. They are small
  and reviewed; a check from outside cannot stop code under test from misreporting itself.
- The page measures its own overflow (site.js), in a 500 px window; the oracle forbids sideways clipping in our
  CSS (only the graph's canvas may), so "no overflow" cannot be had by cutting text off.
- At b3c614f the export writes a literal dollar bare, as math's `$` is written: 19 prose spans typeset as math
  (Boyden, Wentworth First Steps), 148 fields left with an unmatched `$`, and 142 LaTeX commands outside any
  delimiter. The data owner is fixing all three for the next export (asked 2026-10-10, with these counts as the
  before/after check); until then those scroll in their own box rather than widen the page.
- Inside one text field, a `\gdef` in one formula reaches the next (auto-render shares its options).
- The notices name the versions npm resolves today for 3d-force-graph 1.80.0's tree; the bundle carries its
  author's (three r183), under the same licences.
- A redirect counts as an answer (an archive.org item that is gone returns a real 404, checked).

## The 3D prototype (2026-10-10, thrown away; screenshots in docs/evidence/)

3d-force-graph 1.77.0 in headless Chromium (SwiftShader) on the build box:
- Full graph, 19,904 nodes / 58,517 links: loads, the library holds exactly those counts, 325 MB JS heap,
  10 simulation ticks in 17 s, and the picture is an unreadable ball.
- Concept layer only (book, person, chapter, concept, method, theorem, law, quantity, unit, instrument,
  experiment): 2,829 nodes / 7,910 links, 46 MB heap, 255 ticks in 60 s, structure visible.

So the default view is the concept layer, with a book filter, and problems, equations and excerpts
reached from the book pages rather than drawn as 15,000 more points. The full graph stays loadable
and the count check runs on it. A layout computed at build time (so the browser does not simulate)
is the likely next step and needs a decision on running node in the build.

## Libraries (approved by Michael 2026-10-10: "Those libs look good to me for the site.")

three.js + 3d-force-graph (MIT) for the graph, KaTeX (MIT) for LaTeX. Vendored with their LICENSE
files, no CDN.

## Unit 3: math and the 3D graph (written 2026-10-10, before its code)

**Vendored, never fetched by a reader.** `build/vendor/` holds exactly these published files, copied unchanged
from their npm tarballs: KaTeX 0.18.7 (`katex.min.js`, `katex.min.css`, its `fonts/`, `contrib/auto-render.min.js`,
`LICENSE`) and 3d-force-graph 1.80.0 (`3d-force-graph.min.js`, which bundles three r183
and its other dependencies, and `LICENSE`). Versions are at least two weeks old when pinned.
`build/vendor/SOURCES.json` records, per package, the tarball URL, npm's published integrity and the sha256 of
every vendored file. `build/vendor/THIRD-PARTY-NOTICES.txt` carries the licence text of every package in
3d-force-graph's dependency tree (MIT, ISC and BSD-3-Clause; BSD-3 requires the notice) and says that the versions
inside the bundle are the ones its author built with; each notice is the package's own licence file, its sha256
recorded with the package's tarball and integrity. `tools/vendor.py` makes all three (maintainer tool, run by hand,
never by the build). **mhchem:** KaTeX's `contrib/mhchem` (chemistry, `\ce` and `\pu`) is adapted from MathJax code
under Apache-2.0, not MIT. It was withheld on 2026-10-10 and approved by Michael with its notice on 2026-10-11.
Its minified file drops the copyright header, so its notice is the header of its source file in the same KaTeX
tarball plus the full Apache License 2.0 text (from apache.org); `SOURCES.json` records it as a part of katex,
with the sha256 of that notice, and `tools/vendorcheck.py` reads both again online. Only pages that hold a `\ce{`
or `\pu{` load it, after `katex.min.js`.

**Full texts and Project Gutenberg** (Michael, 2026-10-10 and 2026-10-11): chapter text pages, when they come,
show the book's own words with every Project Gutenberg header, footer, licence and reference removed, and carry
no Project Gutenberg name or link. The link to the PG ebook stays only in the book page's provenance section (the
"Where this came from" of his ruling), which already quotes the transcription's licence as it states it.
Amended by Michael on 2026-10-15 (B3, via basecamp #8318: "Yes I want the extra link back you suggest too pg as
well"): the About page's acknowledgement also links Project Gutenberg's home page. The basis is PG's own pages, read
that day: "references to Project Gutenberg (with links, please!) in acknowledgements sections, reference sections or
colophons" are not use of the trademark (gutenberg.org/policy/license.html), and "No permission is needed to link to
www.gutenberg.org" (gutenberg.org/policy/permission.html). Text pages still carry neither the name nor a link.

**Math.** `build/site.js` (ours) typesets in the reader's browser: every `data-field="latex"` element as display
math, and `$...$` inside every text field, with the book's own macros (`book.macros` in the export, carried on the
page as `data-macros`; absent until the export has them). An erratum's "In the source:" line is the source as
printed and is never typeset. A bare alignment row (an `&` outside any
environment) is wrapped in `aligned` for display only; the HTML keeps the export's LaTeX, so the oracle is
unchanged. KaTeX runs with errors on: a formula it cannot typeset stays visible as its source, and the page footer
says so ("N formulas typeset, M shown as source"), written into an `<output id="math-report">`. A formula or
title too wide for a phone scrolls inside itself; the page never does.

**Graph.** `graph/index.html` with `build/graph.js` (ours): the concept layer by default, a book filter (a
`<select>`; the view is read from the page's query string), the whole graph on request. A node click opens its
page (a book, a chapter, or a term: in a book's view on that book's index of terms, elsewhere on the first book of
the shelf that teaches it). `<output id="graph-report">` states what
is drawn, with a digest of exactly what the graph holds. A tap names a node and offers its page (no hover on
touch). The canvas takes the page's colours. The terms pages are the accessible way into the same data, linked
from the graph page.

**Checks added (each with planted controls, red first):**
1. `tools/vendorcheck.py`: SOURCES.json holds exactly the pins in `tools/vendor.py`, from the npm registry; every
   file under `dist/vendor/` is listed with its sha256, nothing unlisted; exactly one notice per package, its
   header stating the licence the package declares and its text byte-for-byte the package's licence file (by
   sha256), and the introduction the one `tools/vendor.py` writes; online, each tarball (the two libraries and all 34 bundled packages) is
   downloaded again and must match npm's integrity, hold the same bytes and carry the same licence. Controls: a
   flipped byte, an unlisted file, a dropped notice, a notice with other words, a changed licence header, a
   duplicate notice, a version off its pin.
2. `tools/browsercheck.py`: headless Chromium (a browser binary run as a command-line tool with `--dump-dom`; no
   browser-automation library) loads every page from a local server it runs and stops, with every host but
   127.0.0.1 resolved nowhere and WebRTC kept off the network, in a 500 px window, and reads the reports the pages
   wrote. Math, on every book and chapter page: typeset + source equals the formulas the checker finds in the
   HTML itself; every typeset formula's TeX (KaTeX's MathML annotation) is one of the page's own sources; the
   page is no wider than the window; each book shows no more as source than its ceiling. Graph, in every view
   (concept layer, everything, each book): the node and link counts and a digest of every node's id, label and
   link and every link's ends, against the same computed from the export. Controls: a bad formula (one more as
   source, over its ceiling), a page without its script, equations typeset from other text, a page too wide, a
   graph one node short, a graph with one label wrong, and a page that hands KaTeX macros the export does not have
   (one harmless extra, so it is the macros comparison that fires). The report's attributes are read back
   unescaped: the DOM dump writes a quote as `&quot;`, which no macro-free export had shown (found 2026-10-13 on
   pd-books 7c27037, the first export with macros). The browser check runs in the Linux rehearsal before any deploy (`CHROMIUM=path`); a build
   without it says so on its last line, as `OFFLINE` does.
3. linkcheck also reads `url()` in served CSS (KaTeX's fonts) and `<script src>`.
4. outward skips `vendor/` (third-party code, proven byte-identical to upstream by check 1) except the two files
   we write there. The oracle's hiding rule skips vendored CSS (KaTeX's rules style only what KaTeX makes at run
   time) and in exchange forbids any `katex` class in the built HTML; it also requires each book's math pages to
   carry exactly the export's `book.macros`, or none (control: a page given macros the export does not have).

**Measured 2026-10-10 at b3c614f** (Chromium 130 headless, SwiftShader; pages 8 at a time, graph views 2 at a time;
about 1m50 with controls): 250 pages, 23,967 formulas typeset and 1,070 shown as source (mhchem withheld), and on every page the two add up to the checker's own
count of the HTML (so the model of auto-render's delimiters holds on all of it). Graph views: concept layer 2,829 /
7,910, everything 19,904 / 58,517, and each of the 15 books (Thompson 236 / 793), all equal to the export. Node
links: 2,599 (15 books, 235 chapters, 2,349 terms), each the page the rule names and each resolving.
Two things the check met on this box: Chromium's sandbox cannot start here (AppArmor disables unprivileged user
namespaces on Ubuntu 26.04), so it runs with `--no-sandbox` and a resolver rule that sends every host but
127.0.0.1 nowhere, so it loads only this site; and 3d-force-graph hangs, rather than failing, on a link to a node
it was not given, so the graph control plants a consistent graph one node short.

**Reviewed 2026-10-10:** two fresh-eyes passes on unit 3 reproduced 15 holes (8, then 7). The ones a check from
outside the code under test can close are red now, by the checks above; the rest are under Known limits (the
pixels of the graph, our scripts reporting on themselves). (The commit that brought unit 3, 8d1a2eb, says "three
passes" and "22 holes"; that count was wrong, and this is the true one.)

**A ratchet, not yet a gate:** the number shown as source may not exceed each book's ceiling in
`build/math-ceiling.json` (1,070 in all at b3c614f; Planck raised by 4 for mhchem, with the reason in the file; 1,066 once mhchem was vendored on 2026-10-11). At b3c614f about 457 equations need the books' own macros, which
the next export carries; the gate becomes zero, or an explicit per-formula list, once it lands.
At 3ed7925 the macros and the producer-markup fix landed: 147 in all, every book at or below its old ceiling,
Maxwell and Macfarlane at zero. Not zero yet, so the ratchet stays a ratchet.

## Full book text (ruled by Michael 2026-10-10)

"Lets not show full project Gutenberg text only the full book text, but link to project Gutenberg. So we
abide by their terms." Read against PG's licence page (gutenberg.org/policy/license.html, read 2026-10-10):
"If you strip the Project Gutenberg license and all references to Project Gutenberg from the text, you are
left with a text unrestricted by U.S. intellectual property law", and a distributor using the name "may only
distribute verbatim copies of the ebooks". So: chapter pages carry the book's own words with PG's header,
footer, licence and every PG reference stripped, changed in format only (math typeset, errata shown beside
the text, never edited into it); the book's provenance page links the PG ebook and quotes PG's 1.E.1
sentence, as it does now. The open question put to Michael: whether that link on the same site still
associates the stripped text with PG. (Answered 2026-10-11, recorded under "Full texts and Project Gutenberg"
above: the text pages carry no PG name or link; the link stays only in the provenance section.) The text has no
source yet (pd-books carries excerpts only). (Superseded 2026-10-13: pd-books 3ed7925 carries each chapter's
`text_html`; the next section is how it becomes pages.)

## The chapter text pages (written 2026-10-13, before their code)

**What the export gives** (census at 3ed7925, `htmlcensus`): 226 of 236 chapters have `text_html`, which is
pandoc's HTML of the transcription. It has 29 tags and no script, style, form, iframe, comment or external
link; styles are only `text-align` and `width`; 244 images, all present under `export/images/<book>/`; no
"Gutenberg". Math is `<span class="math inline">\(..\)</span>` and `<span class="math display">\[..\]</span>`.
The link structure is broken in ways that matter: of 1,202 fragment links, 666 do not resolve in their own
chapter, because the books were converted whole and then split. So each footnote sits in the book's last
chapter, and cross-references point at other chapters or at nothing.

**Pages.** `books/<book>/ch/<chapter>/text/index.html`, one for each chapter that has `text_html` and passes the
sanitizer, linked from its chapter page ("Read the chapter"). A chapter without one has no link and no page.

**The sanitizer** (`build/textpage.py`): it parses the HTML and writes it again from three lists.
- KEEP: the census's tags; `class` tokens from a fixed list, the ones the site reads (`math inline display
  smallcaps center footnotes footnote-ref footnote-back`), any other token dropped; `id`, if a link points to it,
  it is unique on the page, and it has no backslash or space (an id nothing links to is dropped), written with a
  `c-` prefix, as are the fragments that point to it; `style` holding
  only `text-align: left|center|right|justify` (written as a class, `ta-center` and so on) or
  `width: <number><%|in|cm|mm|em|px|pt>` (dropped; site.css keeps every image inside the page), so no `style`
  attribute ships and the oracle's rule against any style attribute stands for these pages too; `colspan` and
  `rowspan` of 1 to 99; `img` `src`, if it is `images/<this book>/...` and the export holds the file (rewritten
  to the site's copy), and its `alt`; `a` `href`, if it is a fragment (see links).
- DROP, known and inert: `role`, `data-label`, `data-latex-placement`.
- REJECT anything else: an unknown tag or attribute, a comment, a declaration, an unbalanced end tag, "gutenberg"
  in any case. A rejected chapter gets no page; the build prints how many were withheld and why, chapter by
  chapter. It never strips something unknown and ships the rest.

**Worked illustrations as tables** (agreed with the data owner, #7968, for Boyden's sums, divisions and roots, which
need column spans and partial rules a KaTeX array cannot draw): `<table class="tex">` with `colspan`, a cell's
`text-align` (written as a ta-* class like any other), its math as math spans, and the classes `rule-t`, `rule-b`,
`rule-l`, `rule-r`, one border each; both the sanitizer's list and the oracle's own include exactly these.

**Links**, resolved in order: a target on the same page stays a fragment; a target that exists in exactly one
other chapter of the same book (one that has a page) becomes a link to that page; anything else loses its
`<a>` and keeps its words. So footnotes read as endnotes and no link is dead.

**Errata beside the text.** A book with errata gets text pages only once every erratum names its chapter, asked
of the data owner (#7833); each page then lists its chapter's errata beside the text. (Refined at 3372745: an
erratum with no chapter is allowed when `printed_in_text` is false, the 40 errata in the books' answers at the
back, which no chapter's text shows; it stays on the book page with the rest.) A book with no errata
says so on each page. 12 of the 15 books have none at 3ed7925.

**Math.** `site.js` typesets each `span.math` inside the text, into a new element; a formula KaTeX cannot
typeset stays as its source, as everywhere else. The browser check counts text pages with the rest, and each
book gets a second ceiling for its text pages (`"text"` in `build/math-ceiling.json`), measured, so that the
pages' as-source formulas cannot hide behind the book's. Wide display math and tables scroll inside their own
box; the page stays 0 px wider than the window.

**The oracle's "text" kind** (`tools/oracle.py`, its own parser, not the builder's):
1. Every chapter with `text_html` has a page, or is named in the build's withheld list with a reason.
2. A page's text, every text node in order with whitespace collapsed, equals the export's `text_html` text in
   the same form. The sanitizer may drop attributes and `<a>` tags, never a word.
3. Every image on a page is byte-identical to the export's file, and no image is copied that no page uses.
4. No text page holds "gutenberg" in any case.
5. A book with errata that do not name their chapter, or whose macros name the transcription's source (the page
   carries the macros), has its chapters withheld; the oracle decides both from the export alone, and requires
   the chapter page's line to give exactly that reason.
6. Planted, each of which must go red or be withheld: a `<script>`, an `onclick`, a `javascript:` href, an
   external href, an `<iframe>`, a `style` with `url(`, a duplicate linked id, "Gutenberg" in the text, a dropped
   paragraph (the oracle's text compare), a changed image byte, and one more as-source formula than a text
   ceiling allows.

**Built 2026-10-13 at 3ed7925:** 69 text pages and 157 withheld (56 for errata without chapters: Boyden,
Thompson, Wentworth's First Steps; 101 for macros that name the source: Blackburn, De Morgan, Hardy, Planck,
Whitehead). Every control above went red as planted; the builder's sanitizer and the oracle's own rules agree on
nine planted chapters (script, onclick, external link, style with url, the name, a comment, an unbalanced tag, an
image of another book, a duplicate linked id). On the 69 pages, 21k formulas typeset and 544 show as source.

**Fresh eyes, before the commit** (a reviewer who did not write it, 2026-10-13): no way found to run script, load
a remote resource, leave the site or escape the article. Fixed from its findings: a book class that is one of the
site's (`graph-canvas` clips, `tx` typesets `$...$`) and a book id that is one of the page's (`math-report`) are
now impossible (fixed class list, `c-` ids, each a control); an unlinked `<a>` keeps its id on a span so links
to it still land; link targets are read by the parser, not a regex; text that ends inside a tag is rejected
(the parser drops it without a word, in the builder and the oracle alike); an image path with `%`, `\`, `?` or
`#` is rejected; the oracle now checks the article's tags, classes and ids itself and reads the withheld line's
words against its reason; site.js typesets only the spans browsercheck counts.

**The source's name, site-wide** (`tools/outward.py`, from the 36d12bc miss): outside a book page's provenance
and the About page, "Gutenberg" may stand only inside the export's own text or its notes on equations, and in no
attribute anywhere. On the deployed 36d12bc this is red with 101 findings, the macros; at 3372745 it is green.

**At 3372745** (the data owner's export for these findings): 226 text pages, 0 withheld; holes 45 (from about
700); 720 of about 45k text formulas as source (ceilings measured; Ball's raised by 4, with the reason in the
file).

**The read, and the hold list** (2026-10-13, at 3372745): five readers who had not built the pages each took
three books, compared three chapters of each word by word with `text_latex`, followed every link and took phone
screenshots. Every book but one loses something the page would claim to show "in format only": a set of examples
(Hardy), figures (Planck, Thompson, Slaught, Wentworth's Plane Geometry, Dickson), theorem statements and proofs
(Plane Geometry), exercise numbers (Hardy, Thompson, Slaught, both Wentworths, Dickson), worked solutions (Boyden),
tables (Ball, De Morgan), footnotes inside math (Hardy, Maxwell, Macfarlane), doubled dates (Whitehead). The
pages match the export's `text_html` exactly, so the losses are the conversion's, sent to the data owner whole.
So `build/text-hold.json` lists the books whose text pages are held, each with the reason its chapter pages
give readers (and, since 2026-10-16, the books a read released: see "A book transcribed from a scan"); the build withholds them and the oracle, reading the same file, requires exactly that reason.
Todhunter alone is released (its one results table shows as source). Two findings were the site's and are
fixed: table cells broke inside numbers on a phone (3487 read as "348 / 7"), and the page's line promised links
between chapters that few books have.

**For deploy at 30d284c** (the export after #7854 and #7855): equations' unconfirmed suspicions are a separate
`flag` field the site does not show, so no page tells a reader the book is wrong on the pipeline's word alone;
book.macros hold math only, so no live page carries the source's name in its macros; 14 Todhunter text pages,
212 chapters withheld (14 books held for review).

**Coverage, the count the readers' findings asked for** (`tools/textcover.py EXPORT --control`): each chapter's
`text_latex` and `text_html` reduced to words and numbers (math, comments, labels, refs, index entries and graphics
arguments taken out); a source word is lost when the four words from it appear nowhere on the page, and runs of
8+ lost words are reported, with the source numbers the page does not have. The control removes a paragraph and
requires 80% of its words back. At 5aa3c05 Todhunter, the one book the readers passed, loses 0.9% of its words
and 2 of 599 numbers; every held book loses many numbers (Whitehead 47 of 205, Planck 561 of 1,110, Hardy 1,701
of 3,235, Wentworth's First Steps 3,093 of 3,455) and the worst lose whole passages (Plane Geometry 58.5% of its
words). It points a reader at where to look; it does not release a book.

**Not deployed yet, on review:** `tools/textholes.py EXPORT --control` counts what the converter left behind or
dropped (math masked). At 3ed7925: 214 empty "( )" where a reference was, 126 section signs with no number, 22
"p." with no number, 102 index entries printed as text, 52 runs of alignment TeX outside math, 195 headings that
begin with a dot. All went to the data owner (#7830, #7834, #7835, #7846, #7848), who is fixing them in one export.
The text pages go live after that export, this count, and a read of the pages.

## The share-alike books (written 2026-10-15, before their code)

Michael, on the books-sa card (2026-10-14, via basecamp #8250): "Show it, with the credits"; "that's fine to host cc
by-sa on books that was kind of the point of looking into that licensing so we can host newer content."

**Input.** [cpuchip/sa-books](https://github.com/cpuchip/sa-books) at `sa-books.pin`, fetched as pd-books is
(`SA_BOOKS=/path` for a local checkout, whose HEAD must equal the pin and whose `books/` must be clean). Each book is
`books/<slug>/book.json` and `books/<slug>/transcription/<doc>/pNNN.md` with its `fig/`. sa-books has no export, so
the site reads the transcription itself. The build refuses a book.json without an author, a licence URL and
statement, `attribution.title_as_modified` and `attribution.credit`. It also refuses a page without front matter
(`source`, `credit`) or whose `credit` differs from the book's. A page that will not render is a refusal too, not
a withheld page: a work under a share-alike licence goes up whole or not at all.

**The licence, as read on 2026-10-15.** CC BY-SA 2.5 section 4 asks, wherever the work is shown, for:
- the licence's URI with every copy;
- the work's copyright notices kept intact;
- the author's name, the work's title and its URI;
- for a derivative work, a credit naming the use.

It does not reach the rest of a collective work, so the site's code stays MIT and the public-domain books stay as
they are. The author's [manner of attribution](http://www.cbphysics.org/howtoAttribute.html) asks for "online
textbook Calculus-Based Physics by Jeffrey Schnick." on the same page as an excerpt, and the title "Calculus-Based
Physics by Jeffrey Schnick as modified by" the modifier for a modified release.

**The credit block, on every page that shows the work** (`<section class="credit">`):
1. the modified release's title (`attribution.title_as_modified`);
2. the excerpt line, verbatim from the author's page;
3. the copyright statement (`licence.statement`), as the book prints it;
4. `attribution.credit`, which names the source and the licence URIs, both as links.

The oracle compares each of these with book.json. The footer of those pages says the page is under CC BY-SA 2.5
(linked) and the site's code is MIT; it does not say CC0 there.

**Pages.**
- The shelf gets a second list, "Share-alike books (CC BY-SA)". The site's name in the header becomes "Math and
  physics books", since it is no longer only public domain.
- `books/<slug>/index.html`, the book page, holds:
  - the title as modified, with the author and his affiliation;
  - the credit block;
  - "What we changed": transcribed from the author's PDFs and .doc, figures cut from the page images, some pages
    proofread, and how each page was read, linked to the evidence README in sa-books at the pin;
  - each source file's URL on cbphysics.org;
  - each document, with its page count and a link to every page.
- `books/<slug>/<doc>/<pNNN>/index.html`, one per transcription page, holds:
  - a crumb back to the book;
  - "Page N of <document title>", with previous and next links;
  - the credit block;
  - the page itself (`<article class="text" data-kind="sa-page" data-id="<slug>/<doc>/<pNNN>">`);
  - its source page and how it was read (the front matter's `source` and `reading`).

**The Markdown** (census at sa-books d9cc208: 633 pages). It has headings, paragraphs, flat `-` lists, `N.` lists,
images, pipe tables, raw `<table>/<tr>/<td>/<br>/<img>`, `**bold**`, `*italic*`, `\*` escapes, entities, and math
as `$..$`, `$$..$$`, `\(..\)` and `\[..\]`. It has no links, code, nesting, blockquotes or footnotes.
`build/sapage.py` renders that subset and nothing else. Math becomes the chapter text pages' spans
(`<span class="math inline">\(..\)</span>`, `display` with `\[..\]`), so `site.js` typesets it unchanged. A
numbered line (`N.` or `N)`) is a paragraph of its own with its number kept as text, so the page's own numbering
reads as printed; `a)` lines stay text too. Then the HTML goes through
`textpage.sanitize`, the same allowlist as the chapter text, with images under `images/<slug>/<doc>/fig/`.

**The oracle for these pages** (`tools/saoracle.py`, its own Markdown reading, nothing imported from the build):
- every page file is on the site once, at its URL, and no sa-page is there that sa-books lacks;
- each page's words (everything outside math, with Markdown's own markers taken out) equal the article's words
  outside math, in order, as a sequence;
- each page's formulas equal the article's math spans, in order;
- each figure it references is an `<img>` in the article whose file is byte-identical to sa-books';
- the credit block on every sa page and on the book page equals book.json's strings, with the licence and source
  links;
- the book page links every page once.

It plants faults, each of which must come back red with exactly its own findings:
- drop a page;
- add a page sa-books lacks;
- blank one page's credit;
- point one page's licence link elsewhere;
- drop a word from a paragraph;
- change one formula;
- drop a figure;
- swap a figure's bytes.

**What it cannot see** (found by the fresh-eyes review, 2026-10-15): a star or underscore that Markdown reads as
emphasis but the page meant literally. For example, `*Footnote ... the factor* above` becomes italics, and both
stars are gone. The words still match, so no finding is raised, and any counting rule built on Markdown's pairing
shares that blindness. The same goes for a line that opens with `- ` and was meant as a minus sign. Neither occurs
at d9cc208: the reviewer counted every such character outside math, page by page (no mismatches), checked that
every bare footnote star survives (quiz answers p054, p072, p119, p124, p140), and found the only `+ `/`- ` lines
inside display math (p094). Re-run that census before a second book goes on.

`tools/oracle.py` hands the kinds `sa-book` and `sa-page` to it by name and still holds every sa page to the
markup allowlist.

**The other checks.**
- The browser check visits every sa page, against a measured ceiling for the book in `math-ceiling.json`.
- The outward check exempts an sa page's article text (the book's words), as it exempts quoted book fields, and
  checks the credits, provenance lines and our own text.
- Since 2026-10-15 ("Finding things") it also exempts, by position, the text inside an element with `data-field`:
  the export's own field, which the oracle compares exactly (an excerpt's with its stars set aside), and which
  rendered emphasis now splits into pieces that are no longer whole strings of the export (the printed dashes
  pd-books beb8a93 restored made this visible). Leaks are still looked for there. The search index (`search/*.json`)
  is checked for leaks only: searchcheck proves it holds exactly the pages' words, which are judged on the pages,
  and its words include the books' own spin, church and tutor.
- The link check requests cbphysics.org and the licence page like any external link.
- `version.json` carries the sa-books pin.

## Finding things: search, excerpts in place, the graph's panel (written 2026-10-15, before their code)

Michael, 2026-10-15, on the live site: the graph page "could be more interactive? like with a side panel? search?
and updating with what the mouse is over? maybe a color code key?"; "these excerpts page could actually link to the
page they were found on"; "could we provide a whole search over every book?"; "if we need to add a real backend
with postgres to improve a lot of that, I am fine with that."

**No backend.** Measured on the d2d75b0 dist: 1,007 pages, about 900,000 words, 12,821 distinct words; a
paragraph-level index is 1.5 MB of postings (0.5 MB gzipped) and 1.9 MB of snippet text (0.5 MB gzipped), loaded
only when a reader searches. A database would add a server to run, back up and secure, and would end the
byte-for-byte comparison of the served site with the rehearsal, for no gain at this size. The site stays static
files. Revisit if the shelf grows past roughly ten times this.

**Block anchors.** Every top-level block of a chapter's text (a child of the text article: a paragraph, list,
table, heading, figure, blockquote, div or section) carries an id: the book's own (`c-...`) where it has one,
else `b-N`, N its position in the article from 1. The ids are written after the allowlist, so the sanitizer's
rules are unchanged; the oracle's text check accepts `b-[1-9][0-9]*` beside `c-`.

**Excerpts in place.** On a chapter page each excerpt shows its page (`p. 183`, from the export) and, when the
chapter's text page is published, a link "In the text": to `text/index.html#<id>` of the block where the excerpt's
words begin, or to the text page's top when its words cannot be found there exactly once (all of them, else its
first 8). Measured at 51b8c3c (where the data owner wrote out the excerpts' cross-references as the chapter
text has them): 796 to their block, 15 to the top, most of them formulas; 1,630 excerpts are in chapters whose
text is not published, and show their page only. A page reads "p. 183"; the export's
"scan 29" (a leaf of the scan) reads "scan page 29". Words are compared as `[a-z0-9]+` runs, math left out. A
located excerpt's target block is highlighted when reached (`:target`). The excerpt's star runs render as
emphasis by CommonMark's rule (nesting and a star inside a word work; a formula is set aside first; a dollar
escaped as `\$` is a dollar); nothing else of its text changes. The oracle does not re-run that rule: it compares
the excerpt's words with every star outside a formula set aside, and counts the excerpts that still show a star
against a ceiling. On the page, site.js shows an escaped `\$` as `$` once the math is typeset (it had shown the
backslash).

**Search** (`/search/`). The build reads its own finished pages (so the index holds what a reader sees) and writes:
`search/docs.json` (every searchable unit: its url with fragment, a title, its book, its kind), `search/p/<c>.json`
(postings, sharded by a word's first character, each word's doc numbers delta-coded) and `search/t/<n>.json`
(each unit's display text, for snippets, in chunks of 1,000 units). Units: each anchored block of a text page;
each element with `data-kind` and an id elsewhere (an excerpt, equation, problem, term, erratum); each sa page;
and each page's remaining text as one unit. Math is not indexed. A query is lowercased `[a-z0-9]+` words, all
required, the last also as a prefix when the query ends inside it; "quoted words" must be consecutive; a book filter
narrows it. Every result holds every word, so the order is: the words as typed before longer words they begin,
then (when 600 or fewer units hold them) units where the words stand together, then near each other (within 8
words), then a unit before the rest of its page, then the site's page order. A snippet centres on the words standing
together where they do, never cuts a formula, and typesets its formulas with KaTeX. Nothing about a query leaves the reader's
browser: the shards are fetched whole, and the server keeps no access log.

**The graph's panel.** Beside the 3D view (below it on a phone): a search over the names in the current view
(choosing one turns the camera to it and selects it); what the pointer is over, or what was tapped, named with its
kind, its number of links in the view, its page, and its neighbours grouped by link type (each one selects that
node); and a colour key, one fixed colour per node type with its count in the view, each a switch that hides or
shows that type. The colours are written in graph.js, not chosen by the library at random, so the key is stable.
`?find=<name>` opens a view with that node chosen, and choosing a node writes it into the address, so a node can be
linked to.
The view's report and digest stay what the browser check compares.

**Gzip and the icon.** nginx compresses HTML, CSS, JavaScript, JSON and SVG for a client that asks; the live
check asks for identity (now said in its request, not left to the library's default), so the bytes it compares
are unchanged. Every page links a small SVG icon (`favicon.svg`), so a browser that reads the link no longer asks
for `/favicon.ico` (basecamp's DevTools pass, 2026-10-15: its 404 was the only console error).

**Oracle.**
- `tools/searchcheck.py` (independent of the build's parser: a tree of each page with each unit's subtree less the
  units inside it, where the build streams with a stack; formulas found by its own scan, where the build uses a
  regular expression): from the dist pages alone, every unit in docs.json resolves (page exists, fragment exists
  once); the postings equal the words it derives for each unit, exactly; every word of every text page's article
  is in the index for a unit of that page; each unit's text (whole: snippets and phrase checks read it) holds all
  its words in order. A fresh-eyes review on 2026-10-15 found the two had shared one regular expression, and with it
  one mistake (an escaped `\$` read as a formula's opening, which hid 113 units' words); the scan is the fix. Controls on every run, each must go red alone: a posting dropped, a stray posting added,
  a unit pointing at a missing fragment, a word missing from a text page's units.
- The oracle's excerpt check: where an excerpt's words stand exactly once in its chapter's text page, its link
  names the block they begin in; elsewhere it goes to the page's top; the excerpts linked to the top and those
  still showing a star are counted against ceilings measured at the first build (build/excerpt-ceiling.json).
  Controls: a link moved to the next block, a fragment removed from the page, an excerpt's emphasis written back
  as stars.
- The browser check: the search page, asked for four words that stand together in one unit of a text page and
  nowhere else (found by searchcheck's own reading of the pages), returns that unit first and only; the graph page,
  opened with `?find=` on the concept layer's best-linked concept whose name is its own, names that node and counts
  as many links as the export gives it in that view. Controls: a search script that drops its first result, a
  panel that counts one link short.

## Light and dark (2026-10-15; written after a small build, out of the usual order, and said so here)

Michael, 2026-10-15: "could we get light/dark modes working for this and primer's sites as easy toggles with memory
of what the use selected in browser storage?"

- The palettes were already there (site.css: light on `:root`, dark under `prefers-color-scheme` guarded by
  `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`). `build/theme.js`, loaded in each
  page's head so the choice is applied before the page is drawn, sets `<html data-theme>` from localStorage
  (`books-theme`, read and written inside try/catch: blocked storage means the site follows the system). It adds one
  button to the header ("Dark" or "Light", the theme it switches to); a click switches and remembers. A reader who
  never chose follows the system setting, also as it changes. Without scripts there is no button and the system
  setting rules. `color-scheme` follows the theme, so form controls and scrollbars do too; the graph's canvas
  takes the new colours on the "themechange" event theme.js sends.
- Primer's sites (learn.cpuchip.net, calc.cpuchip.net) are primer's to change: books sent primer the request and
  this design, with the script, in the message.
- The browser check: three pages that store dark, light, or nothing and go on to a real page; that page must carry
  the stored theme and offer the other one (nothing stored: no data-theme, headless Chromium's light, offering
  dark); and site.css's chosen-dark palette must equal its system-dark palette token for token. Control: a theme
  script that ignores storage. The search page now reports its overflow with its results and the check requires 0
  (a Planck formula in a snippet was 79px wider than a 390px phone; it now scrolls in its own box).
- From primer's same change on its sites (#8722): every colour token of the light palette must have a dark value,
  and each text token (fg, muted, accent, ok, warn) must reach 4.5:1 on the page and the code background in both
  themes (measured: lowest 4.87, light muted on code background). Controls: a pale muted colour, a token with no
  dark value. The graph panel's kind label now takes black or white ink, whichever contrasts more (law's purple
  had 4.44:1 under a fixed cut-off; now 4.93). primer's other finding, that `color-scheme` makes Chromium's default
  link colours pass in dark, does not reach books: every link here is set in --accent.

## A book transcribed from a scan: Granville (2026-10-16; written after the build, and said so here)

Granville's *Elements of the Differential and Integral Calculus* (1911) is the first pd-books book whose text is not
Project Gutenberg's: pd-books transcribed the Cornell scan `cu31924003686221` itself, and `books.json` carries
`transcription.page_scans`, each printed page's scan image (six pages, 3-4 and 33-36, from a second scan of the same
edition). It arrived at pd-books 43ada35 and showed three things the site had assumed.

- **Release, not hold, is what publishes text.** The site held a book's text only when `build/text-hold.json` named
  it, so Granville's 18 chapters with `text_html` went out unread on the first build. Now a book's text is published
  only when the file lists it under `released` (the five books a read released: Todhunter on three chapters, the other four on all of theirs); any other book is withheld
  with the `unread` reason until a read releases it. Build and oracle read the same rule.
- **Release is per chapter** (2026-10-17). `released` maps each released book to the chapters a read released.
  A released book that gains a chapter's text (Todhunter's two, converted at pd-books 3364b3c) holds it as unread
  until a read releases it, instead of publishing it because the book was released once. A chapter with source text
  and no `text_html` says on its chapter page that its text could not be converted, instead of staying silent.
- **A name on the hold file that is no book refuses the build** (a typo or a renamed id would otherwise withhold a
  released book as unread, and the oracle, reading the same file, would agree); the oracle reports it too.
- **Provenance without a licence to quote.** A Gutenberg book's page quotes its transcription's licence. A scan
  transcription has none, so `text_provenance()` says what the printed book is and that the transcription is
  pd-books' own (CC0), names any pages read from another scan (computed from `page_scans`), and refuses unless the
  book was published more than 95 years before the build (the United States public-domain line). It claims no more
  than the data holds: no place of publication, nothing about the other scan beyond its name and pages. The About
  page names the books transcribed this way.
- **Page labels link to the scan.** In a book with `page_scans`, every excerpt's and problem's page label is a link
  (`a.pg`) to that page's image in its archive, which is where its words were read; elsewhere it stays plain
  (`span.pg`, problems now carry it too). The scans are linked, never copied. The oracle's `scan_links_check`
  requires exactly `page_scans[page]` on every label of such a book and no link in any other, with three controls
  (a label pointed at another page, a linked label made plain, a link given to a plain label). Checked on the real
  path: printed pages 25, 33, 128, 301 and 463 open on the page they name.

**Page starts and figures in the text** (pd-books 1348b6d). The data owner marks, in a scan book's `text_html`
only, where each printed page starts (`<span class="pagenum" data-page="N">`, `data-continued="true"` where a
chapter opens partway down a page) and where each figure stands (`<figure class="scan-figure" data-page="N"
data-description="...">`, or a span inside a paragraph), as empty elements; the transcription has no figure images.
`textpage.scanmark()` writes each again as a `.scanmark`: a page start is a small "p. N" link to that page's scan,
a figure is "Figure on p. N of the scan" linked the same way, with the transcriber's description beside it, said
to be the transcriber's. A marker with any content, an unknown attribute, or a page with no scan is a reason to
withhold the chapter. A scanmark's words are the site's, not the book's: the build's `blocks()` and the oracle's
unit, field and block readers all leave them out, so the text comparison stays the book's words exactly, and
`scan_marks_check` proves the scanmarks themselves: one for each marker, in order, its tag, its words and exactly
`page_scans[N]`, with three controls (a page start pointed at another page, a figure dropped, a description word
changed). Measured at 1348b6d with Granville released in a scratch copy: 462 page starts and 278 figures, all
matched, each control red.

Found on the way: the emphasis parser counted a formula beside a star as a letter, where CommonMark counts its `$`
as punctuation, so "*...function.*$^{*}$" stayed as stars. It now follows CommonMark; on the 15 other books the
change alters no page. Three Granville excerpts still show a star that is the book's own footnote mark (asked of the
export); `build/excerpt-ceiling.json` allows those three and no more.

## Deploy

**Before this repo goes public** (Michael's call). Michael ruled on 2026-10-10 (decision 84) that his own
public repos and sites keep their history, seat names and message numbers, so `tools/roster.txt` and the
control's planted names may stay. What must not be public, in the site or in this repo's history: addresses,
hostnames with domains, local paths, session links, secrets, family names. The outward check guards the site
against the first five; the repo's history is searched for all six before the flip. The same ruling lets an
erratum's credit name the seat that settled it, verbatim from the export: the roster check will exempt that
field when the export carries it.

Static files from this repo through Dokploy on the hosting server, deployed by its operator. Michael said to make
the site public on 2026-10-11; the repo stays PRIVATE until he flips it. The deploy, in order:
1. **Rehearsal** at the commit to deploy: a fresh clone, `CHROMIUM=... sh build.sh`, every check green including
   the browser's. Its dist is the reference.
2. **The image** (`Dockerfile`): build.sh runs inside it with every check but the browser's (no Chromium there), so
   a red check fails the deploy. The served stage is nginx with `deploy/nginx.conf`: static files only, no access
   log, no directory listings, `nosniff` and `no-referrer`. Only the built site is copied into it.
3. **The live check**: `tools/verifylive.py https://books.cpuchip.net/ DIST --control` fetches every path of the
   rehearsed dist (609 at 3efd133, directory URLs included) and requires the same bytes, and requires 404 for the
   repo's source paths. Rehearsed against the image on the build box: green, and its control red as planted. The
   build is deterministic (version.json holds the pin and the export's own timestamp, never a build time), which
   is what lets the served bytes be compared with the rehearsal's.
