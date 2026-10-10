"""graphcheck.py: the site's graph file holds every node and link of the export's graph.json, no more.

    python3 tools/graphcheck.py EXPORT DIST [--control]

Compares nodes (id, type and name, which the 3D view draws) and links (source, target, type) as multisets, after
decoding the site's compact form, and checks that the counts the file states equal what it holds. Node links (a
click in the 3D view): exactly the books, chapters and terms have one, each the page the blueprint names (a term
opens on the first book of the shelf that teaches it), and each names a file in DIST with its anchor. The browser
half (the 3D view draws those counts) is tools/browsercheck.py.
--control removes one link and one node, renames a node, and points a node at another book's page, each in a copy
of the site file, and requires each named red.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def export_graph(export):
    g = json.loads((Path(export) / "graph.json").read_text(encoding="utf-8"))
    return Counter((n["id"], n["type"], n.get("name") or "") for n in g["nodes"]), Counter((l["source"], l["target"], l["type"]) for l in g["links"])


TERM_TYPES = ("concept", "theorem", "method", "law", "quantity", "unit", "instrument", "experiment", "person")


def export_urls(export):
    """{node id: link from graph/index.html}, walked from the export alone (book files for chapters)."""
    export = Path(export)
    index = json.loads((export / "books.json").read_text(encoding="utf-8"))
    g = json.loads((export / "graph.json").read_text(encoding="utf-8"))
    kind = {n["id"]: n["type"] for n in g["nodes"]}
    urls, chapter_book = {}, {}
    for b in index["books"]:
        bid = b["id"]
        urls[bid] = f"../books/{bid}/index.html"
        d = json.loads((export / "books" / f"{bid}.json").read_text(encoding="utf-8"))
        for c in d["chapters"]:
            chapter_book[c["id"]] = bid
            urls[c["id"]] = f"../books/{bid}/ch/{c['id'][len(bid) + 1:]}/index.html"
    order = {b["id"]: k for k, b in enumerate(index["books"])}
    first = {}
    for l in g["links"]:
        if l["type"] == "taught_in" and kind.get(l["source"]) in TERM_TYPES and l["target"] in chapter_book:
            b = chapter_book[l["target"]]
            if l["source"] not in first or order[b] < order[first[l["source"]]]:
                first[l["source"]] = b
    for n, b in first.items():
        urls[n] = f"../books/{b}/terms/index.html#t-{n.replace('/', '-')}"
    return urls


def url_errors(want, s, dist):
    have = {n[0]: n[3] for n in s["nodes"] if len(n) > 3}
    errs = [f"url {k}: export says {want.get(k)!r}, site {have.get(k)!r}"
            for k in sorted(set(want) | set(have)) if want.get(k) != have.get(k)]
    ids = {}
    for k, u in sorted(have.items()):
        path, _, frag = u.partition("#")
        target = (Path(dist) / "graph" / path).resolve()
        if not target.is_file():
            errs.append(f"url {k}: no file {u}")
            continue
        if frag:
            if target not in ids:
                ids[target] = set(re.findall(r'\bid="([^"]+)"', target.read_text(encoding="utf-8")))
            if frag not in ids[target]:
                errs.append(f"url {k}: no id {frag!r} on {path}")
    return errs


def site_graph(s):
    nt, et = s["node_types"], s["edge_types"]
    ids = [n[0] for n in s["nodes"]]
    nodes = Counter((n[0], nt[n[1]], n[2]) for n in s["nodes"])
    links = Counter((ids[a], ids[b], et[t]) for a, b, t in s["links"])
    stated = s.get("counts") or {}
    errs = []
    if stated.get("nodes") != len(s["nodes"]) or stated.get("links") != len(s["links"]):
        errs.append(f"file states {stated}, holds {len(s['nodes'])} nodes / {len(s['links'])} links")
    return nodes, links, errs


def compare(exp, site):
    (en, el), (sn, sl, errs) = exp, site
    errs = list(errs)
    for what, e, s in (("node", en, sn), ("link", el, sl)):
        for k in sorted(set(e) | set(s)):
            if e[k] != s[k]:
                errs.append(f"{what} {k}: export {e[k]}, site {s[k]}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("dist")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    exp = export_graph(a.export)
    want_urls = export_urls(a.export)
    s = json.loads((Path(a.dist) / "graph" / "graph.json").read_text(encoding="utf-8"))
    if a.control:
        u = json.loads(json.dumps(s))
        moved = next(n for n in u["nodes"] if len(n) > 3 and "/terms/" in n[3])
        other = next(n[0] for n in u["nodes"] if len(n) > 3 and n[3].endswith("/index.html") and n[0] != moved[0]
                     and "/" not in n[0])
        moved[3] = f"../books/{other}/terms/index.html#t-{moved[0].replace('/', '-')}"
        errs = url_errors(want_urls, u, a.dist)
        if not any(e.startswith(f"url {moved[0]}:") for e in errs):
            print(f"GRAPH CONTROL FAILED: a node pointed at another book passed, checker said {errs[:3]}")
            sys.exit(2)
        r = json.loads(json.dumps(s))
        r["nodes"][1][2] = r["nodes"][1][2] + " (renamed)"
        if not any(e.startswith(f"node ('{r['nodes'][1][0]}'") for e in compare(exp, site_graph(r))):
            print("GRAPH CONTROL FAILED: a renamed node passed")
            sys.exit(2)
        t = json.loads(json.dumps(s))
        gone_link = t["links"].pop(len(t["links"]) // 2)
        gone_node = t["nodes"][-1][0]
        t["nodes"] = t["nodes"][:-1]
        t["links"] = [l for l in t["links"] if len(t["nodes"]) not in (l[0], l[1])]
        errs = compare(exp, site_graph(t))
        named = any(e.startswith(f"node ('{gone_node}'") for e in errs) and any(
            e.startswith(f"link ('{s['nodes'][gone_link[0]][0]}', '{s['nodes'][gone_link[1]][0]}'") for e in errs)
        if not named:
            print(f"GRAPH CONTROL FAILED: removed node {gone_node} and a link, checker said {errs[:4]}")
            sys.exit(2)
        print(f"graph control: RED as planted (a node pointed at another book; a renamed node; a removed node and link, "
              f"{len(errs)} differences, named)")
    errs = compare(exp, site_graph(s)) + url_errors(want_urls, s, a.dist)
    print(f"graph: export {sum(exp[0].values())} nodes / {sum(exp[1].values())} links; "
          f"site file {len(s['nodes'])} / {len(s['links'])}")
    if errs:
        print("GRAPH RED:", *errs[:20], sep="\n  ")
        sys.exit(1)
    print(f"GRAPH GREEN (data file and {len(want_urls)} node links; the 3D view itself is tools/browsercheck.py)")


if __name__ == "__main__":
    main()
