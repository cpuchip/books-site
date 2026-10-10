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
4. Any check below fails on the built site.

## Output (static files, no server code)

- `/` the shelf: every book with title, author, year and counts.
- `/books/<slug>/` provenance and licence (the transcription's source, URL, release date and its
  licence sentence quoted from the export), the chapter list, every erratum with its evidence.
- `/books/<slug>/ch/<n>/` one chapter: its excerpts, equations, exercise sets and every problem in
  them with the printed answer, the check verdict, and STU-32 keys where the export has them.
- Anything in a book file that no chapter lists goes in an "elsewhere in the book" section on the
  book page, so nothing drops silently.
- `/graph/` the concept graph in 3D (library pending Michael's yes; see below).
- Every rendered unit carries `data-kind` and `data-id` (the export's id), which is what the oracle reads.

## Outward rules the build enforces

- No seat names. `found_by` is never rendered; the credit line comes from `kind` and `status`
  ("confirmed against the scan", with the scan linked). Seat clauses inside `evidence` are rewritten
  by one table in `build/neutral.py`. The verbatim fields stay in pd-books where they are CC0.
- No em-dashes, no session URLs.
- Nothing hosted without the right to host it: scans are linked to their archive, never copied
  (pd-books' evidence crops stay in pd-books, linked). No Project Gutenberg text beyond the excerpts
  the export already carries, unless Michael rules otherwise.

## The oracle (each check plants its own faults on every run and must see them red first)

1. **Every unit, once, on its page, with its text.** `tools/oracle.py EXPORT DIST` reads the export with its
   own walk (nothing imported from the build) and every `data-kind`/`data-id` element of the built HTML with the
   text inside it. Kinds: book, chapter, exercise_set, excerpt, equation, problem, erratum. Per unit:
   presence (exactly as many times as the export holds it), placement (the URL contract below), content (the
   problem's text, each printed answer and each key's steps; the excerpt's text; the equation's LaTeX; the
   erratum's printed and corrected text and context, and at least one evidence sentence verbatim, since the
   rest may be rewritten for readers; the titles). Seven controls: delete a problem, delete an erratum,
   duplicate an erratum, blank a problem's text, drop an erratum's evidence, move a problem to the wrong page,
   and drop a problem from a copy of the export and rebuild. Each must come back with exactly its planted
   finding.
2. **Links.** `tools/linkcheck.py DIST`: every internal href and src names a file (and fragment) in dist; an
   empty href or a bare `#` fails; every page is reachable from the shelf; every external URL answers 2xx/3xx
   (`--offline` for development only, and the build's last line says so). Controls: a missing file, a missing
   fragment, an empty link, an orphan page.
3. **Graph.** `tools/graphcheck.py`: the site's graph file holds every node (id, type, name) and link (source,
   target, type) of graph.json and states the same counts. Controls: a renamed node; a removed node and link.
   The browser half (the 3D view holds those counts after load) waits on the library ruling.
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
not in the book goes on the book page.

**Known limits** (reviewed 2026-10-10 by a fresh-eyes pass, which found five false greens in the first
version, all now red under the checks above):
- Fields the site does not render are not checked: equation `name`/`symbols`, `answer_latex`, `judge_why`,
  `relations`, key provenance beyond the firmware pin. Rendering one of them means adding it to the oracle.
- An element hidden by markup (`hidden`, `<template>`) would count as present; the build emits neither.
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

## Libraries (MUST ASK, sent to Michael through basecamp 2026-10-10)

three.js + 3d-force-graph (MIT) for the graph, KaTeX (MIT) for LaTeX. Vendored with their LICENSE
files, no CDN. Until he answers, problems render from the export's `markdown` field as text.

## Deploy

Static files from this repo through Dokploy on nocix (the nocix seat deploys). Rehearsed on a Linux
clone before any deploy request. The repo stays PRIVATE and the site unpublished until Michael says so.
