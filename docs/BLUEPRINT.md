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

## The oracle (each check has a planted fault seen red)

1. **Counts, both sides.** `tools/oracle.py EXPORT DIST` reads the export (its own JSON walk, no
   code shared with the build) and the built HTML (html.parser over every page, collecting
   `data-kind`/`data-id`), and compares id sets per kind: book, chapter, problem, erratum. Missing,
   extra and duplicated ids are all failures, each listed by id. The control (`--control`) copies the
   fresh dist to a temp directory, deletes one problem element chosen by seed, and must come back red
   naming exactly that id; a second control drops a problem from a copy of the export and builds it,
   and the oracle against the true export must name it. The match is reported only after both reds.
2. **Links.** `tools/linkcheck.py DIST` resolves every internal href and src to a file in dist, and
   every external URL (sources, scans, learn.cpuchip.net) by a request, with `--offline` for
   development only. Control: a planted broken internal link goes red.
3. **Graph.** The graph data file's node and link counts equal graph.json's (in the build). In the Linux
   rehearsal, a headless browser loads `/graph/` and reads the counts the library holds after load;
   they must equal the export's. Control: a graph file with one link removed goes red.
4. **Outward.** `tools/outward.py DIST` flags any roster seat name, em-dash or session URL in rendered
   text. A roster name passes only where the same string is book text from the export (Thompson writes
   "tutor"). Control: a planted seat name goes red.

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
