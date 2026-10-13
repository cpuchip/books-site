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
give readers; the build withholds them and the oracle, reading the same file, requires exactly that reason.
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
