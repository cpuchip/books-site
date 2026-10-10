"""linkcheck.py: every link on the built site resolves.

    python3 tools/linkcheck.py DIST [--offline] [--control]

Internal: every href/src that is not absolute must name a file in DIST (a directory link needs its
index.html), a #fragment must be an id on that page, an empty href or a bare "#" fails, and every page
must be reachable from index.html. External: every http(s) URL is requested once
(HEAD, then GET when a server refuses HEAD) and must answer 2xx or 3xx. --offline skips the external half
and says so; the build that deploys never passes it.
--control plants a missing file, a missing fragment, an empty link and an orphan page in a copy of DIST and
requires all four red.
"""
import argparse
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlsplit


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids.add(v)
            if k in ("href", "src") and v is not None:
                self.links.append(v)


def scan(dist):
    pages = {}
    for p in sorted(Path(dist).rglob("*.html")):
        h = _Links()
        h.feed(p.read_text(encoding="utf-8"))
        pages[p.resolve()] = h
    return pages


CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")


def stylesheets(dist):
    """Every url() in every served stylesheet must name a file (KaTeX's fonts); data: URIs are inline."""
    bad = []
    for css in sorted(Path(dist).resolve().rglob("*.css")):
        for u in CSS_URL.findall(css.read_text(encoding="utf-8")):
            if u.startswith("data:"):
                continue
            if urlsplit(u).scheme or u.startswith("//"):
                bad.append((css, u, "a stylesheet loads from outside the site"))
            elif not (css.parent / unquote(urldefrag(u)[0].split("?")[0])).resolve().is_file():
                bad.append((css, u, "no such file"))
    return bad


def internal(dist, pages):
    dist = Path(dist).resolve()
    bad, external, reached = stylesheets(dist), set(), {}
    for page, h in pages.items():
        for link in h.links:
            if urlsplit(link).scheme in ("http", "https"):
                external.add(link)
                continue
            if urlsplit(link).scheme or link.startswith("//"):
                bad.append((page, link, "scheme not allowed"))
                continue
            if link.strip() in ("", "#"):
                bad.append((page, link, "empty link"))
                continue
            path, frag = urldefrag(link)
            target = page if not path else (page.parent / unquote(path)).resolve()
            if target.is_dir():
                target = target / "index.html"
            if dist not in target.parents and target != dist:
                bad.append((page, link, "leaves the site"))
            elif not target.exists():
                bad.append((page, link, "no such file"))
            elif frag and target.suffix == ".html" and frag not in pages[target].ids:
                bad.append((page, link, f"no id {frag!r} on the page"))
            elif target.suffix == ".html":
                reached.setdefault(page, set()).add(target)
    # every page must be reachable from the shelf by internal links (an orphan page is content nobody finds)
    start = dist / "index.html"
    seen, todo = {start}, [start]
    while todo:
        for t in reached.get(todo.pop(), ()):
            if t not in seen:
                seen.add(t)
                todo.append(t)
    for page in pages:
        if page not in seen:
            bad.append((page, "(no link reaches this page)", "orphan page"))
    return bad, external


def fetch(url):
    headers = {"User-Agent": "books-site linkcheck (static site build)"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return url, r.status
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            return url, e.code
        except Exception as e:  # noqa: BLE001 - any failure to reach a source is a broken link
            return url, f"{type(e).__name__}: {e}"
    return url, "no answer"


def run(dist, offline):
    pages = scan(dist)
    bad, external = internal(dist, pages)
    ext_bad = []
    if not offline:
        with ThreadPoolExecutor(8) as ex:
            for url, status in ex.map(fetch, sorted(external)):
                if not (isinstance(status, int) and 200 <= status < 400):
                    ext_bad.append((url, status))
    return pages, bad, external, ext_bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dist"
            shutil.copytree(a.dist, copy)
            idx = copy / "index.html"
            idx.write_text(idx.read_text(encoding="utf-8").replace(
                "</main>", '<a href="books/no-such-book/index.html">x</a>'
                           '<a href="about/index.html#no-such-id">y</a><a href="">z</a></main>', 1), encoding="utf-8")
            (copy / "site.css").write_text((copy / "site.css").read_text(encoding="utf-8")
                                           + "\n.x { background: url(no-such-font.woff2); }\n", encoding="utf-8")
            (copy / "orphan").mkdir()
            (copy / "orphan" / "index.html").write_text("<p>nobody links here</p>", encoding="utf-8")
            _, bad, _, _ = run(copy, offline=True)
            got = sorted(link for _, link, _ in bad)
            if got != ["", "(no link reaches this page)", "about/index.html#no-such-id", "books/no-such-book/index.html",
                       "no-such-font.woff2"]:
                print(f"LINK CONTROL FAILED: planted two broken links, checker said {got[:5]}")
                sys.exit(2)
            print("link control: RED as planted (a missing file, a missing fragment, an empty link, an orphan page, "
                  "a missing stylesheet url)")
    pages, bad, external, ext_bad = run(a.dist, a.offline)
    n = sum(len(h.links) for h in pages.values())
    print(f"links: {n} on {len(pages)} pages; {len(external)} distinct external"
          + (" (NOT requested: --offline)" if a.offline else ""))
    for page, link, why in bad[:20]:
        print(f"  BROKEN {Path(page).relative_to(Path(a.dist).resolve())}: {link} ({why})")
    for url, status in ext_bad[:20]:
        print(f"  BROKEN external {url}: {status}")
    if bad or ext_bad:
        print(f"LINKS RED: {len(bad)} internal, {len(ext_bad)} external")
        sys.exit(1)
    print("LINKS GREEN" + (" (internal only)" if a.offline else ""))


if __name__ == "__main__":
    main()
