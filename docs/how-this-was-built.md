# How this was built

Michael Stufflebeam owns this site and rules on it. The code was written by AI agents, each a Claude Code session
with its own charter, working with him. The commit messages and docs name these agents (the "seats") and the
messages between them. They stay in the history on purpose, so anyone can see how the work was done and try it
themselves.

## The seats

- **books** wrote this repository: the build, the checks that judge it, the vendoring of the two libraries, and the
  deploy files. Its fresh-eyes reviews were done by short-lived helper agents that read the code cold and tried to
  make a check pass on a broken site; what they found is in `docs/BLUEPRINT.md`.
- **qwenniverse-fermion** produces the book data this site is built from: the export in
  [pd-books](https://github.com/cpuchip/pd-books) (CC0). Every count, link and erratum here comes from that export
  at the commit in `pd-books.pin`; this repository holds no book data of its own.
- **nocix** runs the hosting server and deploys the site by hand when asked, after a rehearsal at that commit.
- **primer** builds the lessons at learn.cpuchip.net, which link into these books.
- **abacus** keeps the board where Michael answers the questions the seats put to him.
- **basecamp** coordinates the seats and relays Michael's rulings.

## The numbers

A `#NNNN` in a commit or a doc (for example "#6483") is a message in our internal message log: the question,
ruling or report that a change answers. The log itself is not public. The number shows which conversation a line
came from and in what order.

Decisions are numbered too ("decision 84"): those are Michael's rulings.

## The rules the work kept

- **Oracle first:** the check that judges a feature was written before the feature, and every check plants its own
  faults on every run and must find exactly those. A check that has never been seen to fail is not evidence.
- **Counted both ways:** every book, chapter, problem, erratum and term in the export is on the site once, on its
  page, with its text; and the site holds nothing the export doesn't.
- **Provenance on every book page:** where the text came from, under what licence, quoted as it states it.
- **Nothing hosted we have no right to host; when in doubt, link.** The two libraries (KaTeX, 3d-force-graph) are
  vendored byte for byte from their npm releases, with every licence in `build/vendor/THIRD-PARTY-NOTICES.txt`.
- **The live site is the rehearsed build:** each deploy is checked by fetching every file from the live site and
  comparing its bytes with the build that passed every check, the browser check included.

## The history

One commit message was reworded on 2026-10-11, before the repository opened, to remove a local folder path. Every
commit's files are unchanged; only that message and the hashes after it changed.
