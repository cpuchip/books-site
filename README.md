# books-site

The reader's site for the public-domain math and physics books in [cpuchip/pd-books](https://github.com/cpuchip/pd-books): one page per book with its provenance and licence, a chapter reader, the problems with checked answers, the errata with their evidence, and the concept graph that links the books to each other and to the lessons on learn.cpuchip.net.

The site is built from `pd-books/export/` (CC0 data) and hosts no book scans; scans are linked to their archives.
It also shows the share-alike books in [cpuchip/sa-books](https://github.com/cpuchip/sa-books), page by page from
their transcriptions, each page with its credits and under its book's licence (`build/sapage.py`, checked by
`tools/saoracle.py`; docs/BLUEPRINT.md, "The share-alike books").
Readers can search every book (`/search/`: an index the build writes from its own pages, `build/search.py`, searched
in the browser by `build/search.js` and checked by `tools/searchcheck.py`), follow an excerpt to its paragraph in
the chapter's text, and explore the graph with a panel (find a node, see its links, a colour key); docs/BLUEPRINT.md,
"Finding things". The site stays static files: no server code, no database.

Code: MIT. Data: see pd-books (CC0 for everything we made; Project Gutenberg's licence for its files, kept intact)
and sa-books (each book under its own CC BY-SA licence, which the pages that show it keep).

## Build

    sh build.sh                       # fetch pd-books at pd-books.pin and sa-books at sa-books.pin, build, check, write dist/
    CHROMIUM=/path/to/chrome sh build.sh   # also the browser check (math typeset, 3D graph counts, search, graph panel)
    docker build .                    # the deployed image: the build and its checks, then nginx serving dist
    python3 tools/verifylive.py URL DIST   # the live site serves exactly the rehearsed dist

The build refuses a bad export and replaces `dist/` only when every check is green; `docs/BLUEPRINT.md` is the
contract and lists each check with the faults it plants in itself on every run. Python 3 standard library only;
the browser check runs a headless Chromium binary as a command-line tool. KaTeX and 3d-force-graph are vendored
unchanged in `build/vendor/` (see `THIRD-PARTY-NOTICES.txt` there; `tools/vendor.py` re-vendors them).

## How this was built

By AI agents working with Michael, each with its own charter; the history names them on purpose.
`docs/how-this-was-built.md` says who did what and what the `#NNNN` numbers in the history mean.
