# books-site

The reader's site for the public-domain math and physics books in [cpuchip/pd-books](https://github.com/cpuchip/pd-books): one page per book with its provenance and licence, a chapter reader, the problems with checked answers, the errata with their evidence, and the concept graph that links the books to each other and to the lessons on learn.cpuchip.net.

The site is built from `pd-books/export/` (CC0 data) and hosts no book scans; scans are linked to their archives.

Code: MIT. Data: see pd-books (CC0 for everything we made; Project Gutenberg's licence for its files, kept intact).

## Build

    sh build.sh                       # fetch pd-books at pd-books.pin, build, check, write dist/
    CHROMIUM=/path/to/chrome sh build.sh   # also the browser check (math typeset, 3D graph counts)

The build refuses a bad export and replaces `dist/` only when every check is green; `docs/BLUEPRINT.md` is the
contract and lists each check with the faults it plants in itself on every run. Python 3 standard library only;
the browser check runs a headless Chromium binary as a command-line tool. KaTeX and 3d-force-graph are vendored
unchanged in `build/vendor/` (see `THIRD-PARTY-NOTICES.txt` there; `tools/vendor.py` re-vendors them).
