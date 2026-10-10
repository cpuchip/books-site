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
   that its context holds. 34 in all.
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
   `tools/outward-allow.txt`. Fails on any roster name (`tools/roster.txt`), an em-dash, any claude.ai link.
   Controls: seat names in an erratum class, in evidence (hyphenated) and in a graph node; an em-dash in a
   correction; a claude.ai link.

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
- linkcheck reads href and src only; the build emits no srcset, poster, action or CSS url().
- A redirect counts as an answer (an archive.org item that is gone returns a real 404, checked).

## The 3D prototype (2026-10-10, thrown away; screenshots in docs/evidence/)

3d-force-graph 1.77.0 in headless Chromium (SwiftShader) on lepton:
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

## Full book text (ruled by Michael 2026-10-10)

"Lets not show full project Gutenberg text only the full book text, but link to project Gutenberg. So we
abide by their terms." Read against PG's licence page (gutenberg.org/policy/license.html, read 2026-10-10):
"If you strip the Project Gutenberg license and all references to Project Gutenberg from the text, you are
left with a text unrestricted by U.S. intellectual property law", and a distributor using the name "may only
distribute verbatim copies of the ebooks". So: chapter pages carry the book's own words with PG's header,
footer, licence and every PG reference stripped, changed in format only (math typeset, errata shown beside
the text, never edited into it); the book's provenance page links the PG ebook and quotes PG's 1.E.1
sentence, as it does now. The open question put to Michael: whether that link on the same site still
associates the stripped text with PG. The text has no source yet (pd-books carries excerpts only).

## Deploy

Static files from this repo through Dokploy on nocix (the nocix seat deploys). Rehearsed on a Linux
clone before any deploy request. The repo stays PRIVATE and the site unpublished until Michael says so.
