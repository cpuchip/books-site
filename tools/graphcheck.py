"""graphcheck.py: the site's graph file holds every node and link of the export's graph.json, no more.

    python3 tools/graphcheck.py EXPORT DIST [--control]

Compares node ids (with type) and links (source, target, type) as multisets, after decoding the site's
compact form, and checks that the counts the file states equal what it holds. The browser half (the 3D view
renders those counts) runs in the Linux rehearsal once the graph library is approved.
--control removes one link and one node from a copy of the site file and requires both named red.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def export_graph(export):
    g = json.loads((Path(export) / "graph.json").read_text(encoding="utf-8"))
    return Counter((n["id"], n["type"]) for n in g["nodes"]), Counter((l["source"], l["target"], l["type"]) for l in g["links"])


def site_graph(s):
    nt, et = s["node_types"], s["edge_types"]
    ids = [n[0] for n in s["nodes"]]
    nodes = Counter((n[0], nt[n[1]]) for n in s["nodes"])
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
    s = json.loads((Path(a.dist) / "graph" / "graph.json").read_text(encoding="utf-8"))
    if a.control:
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
        print(f"graph control: RED as planted ({len(errs)} differences, the removed node and link named)")
    errs = compare(exp, site_graph(s))
    print(f"graph: export {sum(exp[0].values())} nodes / {sum(exp[1].values())} links; "
          f"site file {len(s['nodes'])} / {len(s['links'])}")
    if errs:
        print("GRAPH RED:", *errs[:20], sep="\n  ")
        sys.exit(1)
    print("GRAPH GREEN (data file; the browser render check is not built yet)")


if __name__ == "__main__":
    main()
