// graph.js: the concept graph in 3D, in the reader's browser. books-site, MIT.
// Views (from the page's query string): the concept layer (default), ?view=all, ?book=<id>. What is drawn is
// written into #graph-report, which the build's browser check compares with the export.
(function () {
  "use strict";
  // two 32-bit FNV-1a hashes of the UTF-8 bytes, as 16 hex digits: synchronous, so the report is complete before
  // the first frame (the browser check gives the page only a few frames)
  var fnv64 = function (s) {
    var bytes = new TextEncoder().encode(s), a = 0x811c9dc5, b = 0x050c5d1f;
    for (var i = 0; i < bytes.length; i++) {
      a = Math.imul(a ^ bytes[i], 0x01000193) >>> 0;
      b = Math.imul(b ^ bytes[i], 0x01000193) >>> 0;
    }
    return ("0000000" + a.toString(16)).slice(-8) + ("0000000" + b.toString(16)).slice(-8);
  };
  var report = document.getElementById("graph-report");
  var box = document.getElementById("graph");
  var pick = document.getElementById("view");
  var chosen = document.getElementById("graph-pick");
  if (!report || !box || typeof ForceGraph3D === "undefined") return;
  var q = new URLSearchParams(location.search);
  var view = q.get("view") === "all" ? "all" : (q.get("book") ? "book:" + q.get("book") : "concepts");
  if (pick) {
    pick.value = view;
    pick.addEventListener("change", function () {
      var v = pick.value;
      location.search = v === "concepts" ? "" : (v === "all" ? "?view=all" : "?book=" + encodeURIComponent(v.slice(5)));
    });
  }
  fetch("graph.json").then(function (r) { return r.json(); }).then(function (g) {
    var type = function (i) { return g.node_types[g.nodes[i][1]]; };
    var keep, own = null;  // in a book's view, that book's terms open on its own index of terms
    if (view === "all") {
      keep = function () { return true; };
    } else if (view === "concepts") {
      var layer = new Set(g.concept_layer);
      keep = function (i) { return layer.has(type(i)); };
    } else {
      // a book, its chapters (part_of the book) and every node taught_in one of those chapters
      var book = view.slice(5), bi = g.nodes.findIndex(function (n) { return n[0] === book; });
      var partOf = g.edge_types.indexOf("part_of"), taughtIn = g.edge_types.indexOf("taught_in");
      var chapters = new Set(), inBook = new Set([bi]);
      g.links.forEach(function (l) { if (l[2] === partOf && l[1] === bi && type(l[0]) === "chapter") chapters.add(l[0]); });
      chapters.forEach(function (c) { inBook.add(c); });
      own = new Set();
      g.links.forEach(function (l) { if (l[2] === taughtIn && chapters.has(l[1])) { inBook.add(l[0]); own.add(l[0]); } });
      keep = function (i) { return inBook.has(i); };
    }
    var nodes = [], ids = new Set();
    g.nodes.forEach(function (n, i) {
      if (!keep(i)) return;
      ids.add(i);
      var href = own && own.has(i) ? "../books/" + view.slice(5) + "/terms/index.html#t-" + n[0].replace(/\//g, "-") : (n[3] || null);
      nodes.push({ id: n[0], name: n[2], kind: g.node_types[n[1]], href: href });
    });
    var links = [];
    g.links.forEach(function (l) {
      if (ids.has(l[0]) && ids.has(l[1])) links.push({ source: g.nodes[l[0]][0], target: g.nodes[l[1]][0] });
    });
    var css = getComputedStyle(document.documentElement);
    var graph = ForceGraph3D()(box)
      .width(box.clientWidth).height(box.clientHeight)
      .backgroundColor(css.getPropertyValue("--code-bg").trim() || "#f4f1ea")
      .linkColor(function () { return css.getPropertyValue("--muted").trim() || "#888"; })
      .nodeLabel(function (n) { return n.kind + ": " + n.name; })
      .nodeAutoColorBy("kind")
      .linkOpacity(0.25)
      .cooldownTime(15000)
      // a tap or click selects a node and names it, with a link to its page: on touch there is no hover label
      .onNodeClick(function (n) {
        if (!chosen) { if (n.href) location.href = n.href; return; }
        var name = graph.nodeLabel();
        chosen.textContent = (typeof name === "function" ? name(n) : n[name]) + " ";
        if (n.href) {
          var a = document.createElement("a");
          a.href = n.href;
          a.textContent = "Open its page";
          chosen.appendChild(a);
        }
      })
      .graphData({ nodes: nodes, links: links });
    var drawn = graph.graphData();
    report.setAttribute("data-view", view);
    report.setAttribute("data-nodes", String(drawn.nodes.length));
    report.setAttribute("data-links", String(drawn.links.length));
    report.textContent = "Showing " + drawn.nodes.length.toLocaleString("en") + " nodes and " +
      drawn.links.length.toLocaleString("en") + " links.";
    // a digest of exactly what the graph holds (each node's id, label and link target, each link's ends), so the
    // browser check can compare more than counts
    var label = graph.nodeLabel();
    var end = function (x) { return typeof x === "object" ? x.id : x; };
    var text = drawn.nodes.map(function (n) {
      return n.id + "\t" + (typeof label === "function" ? label(n) : n[label]) + "\t" + (n.href || "");
    }).sort().join("\n") + "\n--\n" + drawn.links.map(function (l) {
      return end(l.source) + "\t" + end(l.target);
    }).sort().join("\n");
    report.setAttribute("data-digest", fnv64(text));
  }).catch(function (e) { report.textContent = "The graph could not load: " + e; });
})();
