// graph.js: the concept graph in 3D, in the reader's browser. books-site, MIT.
// Views (from the page's query string): the concept layer (default), ?view=all, ?book=<id>. What is drawn is
// written into #graph-report, which the build's browser check compares with the export.
// The panel beside it: a search over the names in the view, the node under the pointer (or the one chosen) with its
// links and neighbours, and a colour key whose types can be hidden. What is chosen is written into #graph-pick's
// data attributes for the browser check (docs/BLUEPRINT.md, "Finding things").
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
  var find = document.getElementById("graph-find");
  var names = document.getElementById("graph-names");
  var keyBox = document.getElementById("graph-key");
  // one colour per node type, so the key means the same on every visit (the library would pick at random)
  var COLOURS = {
    book: "#1f4e79", chapter: "#8a8a8a", person: "#8c564b", concept: "#2ca02c", theorem: "#d62728",
    method: "#ff7f0e", law: "#9467bd", quantity: "#17becf", unit: "#bcbd22", instrument: "#e377c2",
    experiment: "#6b4c9a", problem: "#7fa7d6", equation: "#62b462", problem_form: "#f0a35e", excerpt: "#a990c9",
    problem_shape: "#b08478", exercise_set: "#e996c0", capability: "#c4c46a"
  };
  var colourOf = function (kind) { return COLOURS[kind] || "#999999"; };
  // dark text on a light colour, white on a dark one (relative luminance, WCAG's formula)
  var inkOn = function (hex) {
    var c = [1, 3, 5].map(function (i) {
      var v = parseInt(hex.slice(i, i + 2), 16) / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 0.18 ? "#111111" : "#ffffff";
  };
  var said = document.getElementById("graph-said");
  var words = function (s) { return String(s).replace(/_/g, " "); };
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
    var links = [], byId = {}, around = {};
    nodes.forEach(function (n) { byId[n.id] = n; around[n.id] = []; });
    g.links.forEach(function (l) {
      if (ids.has(l[0]) && ids.has(l[1])) {
        var s = g.nodes[l[0]][0], t = g.nodes[l[1]][0], type = g.edge_types[l[2]];
        links.push({ source: s, target: t, type: type });
        around[s].push({ other: t, type: type, out: true });
        if (t !== s) around[t].push({ other: s, type: type, out: false });
      }
    });
    var hidden = {}, picked = null, hovered = null, lit = null;
    var light = function (n) {
      lit = null;
      if (!n) return;
      lit = {};
      lit[n.id] = true;
      around[n.id].forEach(function (a) { lit[a.other] = true; });
    };
    var css = getComputedStyle(document.documentElement);
    var graph = ForceGraph3D()(box)
      .width(box.clientWidth).height(box.clientHeight)
      .backgroundColor(css.getPropertyValue("--code-bg").trim() || "#f4f1ea")
      .linkColor(function () { return css.getPropertyValue("--muted").trim() || "#888"; })
      .nodeLabel(function (n) { return n.kind + ": " + n.name; })
      .nodeColor(function (n) { return lit && !lit[n.id] ? "rgba(140,140,140,0.25)" : colourOf(n.kind); })
      .nodeVisibility(function (n) { return !hidden[n.kind]; })
      .linkVisibility(function (l) {
        var s = typeof l.source === "object" ? l.source : byId[l.source], t = typeof l.target === "object" ? l.target : byId[l.target];
        return !hidden[s.kind] && !hidden[t.kind];
      })
      .linkOpacity(0.25)
      .cooldownTime(15000)
      // a tap or click chooses a node: the panel names it and lists its neighbours (on touch there is no hover)
      .onNodeClick(function (n) { choose(n, false); })
      .onNodeHover(function (n) {
        hovered = n || null;
        box.style.cursor = n ? "pointer" : "";
        if (!picked) { light(hovered); show(hovered); refresh(); }
      })
      .onBackgroundClick(function () { picked = null; light(null); show(null); refresh(); })
      .graphData({ nodes: nodes, links: links });
    var refresh = function () { graph.nodeColor(graph.nodeColor()); };
    // the reader switched theme (theme.js): the canvas takes the new page colours
    document.addEventListener("themechange", function () {
      var now = getComputedStyle(document.documentElement);
      graph.backgroundColor(now.getPropertyValue("--code-bg").trim() || "#f4f1ea");
      graph.linkColor(function () { return now.getPropertyValue("--muted").trim() || "#888"; });
    });
    // the panel: the node's kind and name, its page, its links in this view, its neighbours by link type
    var show = function (n) {
      if (!chosen) return;
      chosen.textContent = "";
      chosen.removeAttribute("data-node");
      chosen.removeAttribute("data-links");
      if (!n) { chosen.textContent = "Point at a node, tap it, or find it by name."; return; }
      chosen.setAttribute("data-node", n.id);
      chosen.setAttribute("data-links", String(around[n.id].length));
      var head = document.createElement("p");
      head.className = "pick-head";
      var kind = document.createElement("span");
      kind.className = "pick-kind";
      kind.style.background = colourOf(n.kind);
      kind.style.color = inkOn(colourOf(n.kind));
      kind.textContent = words(n.kind);
      head.appendChild(kind);
      head.appendChild(document.createTextNode(" " + n.name));
      chosen.appendChild(head);
      var line = document.createElement("p");
      line.className = "n";
      line.textContent = around[n.id].length.toLocaleString("en") + (around[n.id].length === 1 ? " link" : " links") + " in this view. ";
      if (n.href) {
        var a = document.createElement("a");
        a.href = n.href;
        a.textContent = "Open its page";
        line.appendChild(a);
      }
      chosen.appendChild(line);
      var groups = {}, order = [];
      around[n.id].forEach(function (x) {
        var key = (x.out ? "" : "\u2190 ") + words(x.type);
        if (!groups[key]) { groups[key] = []; order.push(key); }
        groups[key].push(x.other);
      });
      order.sort();
      order.forEach(function (key) {
        var h = document.createElement("p");
        h.className = "pick-group";
        h.textContent = key + " (" + groups[key].length + ")";
        chosen.appendChild(h);
        var ul = document.createElement("ul");
        ul.className = "pick-list";
        groups[key].slice().sort(function (a, b) { return byId[a].name.localeCompare(byId[b].name); }).slice(0, 60)
          .forEach(function (id) {
            var li = document.createElement("li"), b = document.createElement("button");
            b.type = "button";
            b.className = "pick-node";
            b.style.borderLeftColor = colourOf(byId[id].kind);
            b.textContent = byId[id].name || id;
            b.title = words(byId[id].kind);
            b.addEventListener("click", function () { choose(byId[id], true); });
            li.appendChild(b);
            ul.appendChild(li);
          });
        if (groups[key].length > 60) {
          var li = document.createElement("li");
          li.className = "n";
          li.textContent = "and " + (groups[key].length - 60) + " more";
          ul.appendChild(li);
        }
        chosen.appendChild(ul);
      });
    };
    var choose = function (n, fly) {
      picked = n;
      if (n && hidden[n.kind]) {  // a node of a hidden type is shown again with its type, not flown to unseen
        hidden[n.kind] = false;
        key();
        graph.nodeVisibility(graph.nodeVisibility());
        graph.linkVisibility(graph.linkVisibility());
      }
      // the panel is rebuilt on every hover; only a choice is announced, in one short line
      if (said) said.textContent = n ? n.name + ", " + words(n.kind) + ", " + around[n.id].length + " links" : "";
      if (n && history.replaceState) {
        var u = new URLSearchParams(location.search);
        u.set("find", n.name + " (" + words(n.kind) + ")");
        history.replaceState(null, "", "?" + u.toString());
      }
      light(n);
      show(n);
      refresh();
      if (fly && n) {
        flyTo(n);
        if (!settled) pending = n;  // the layout is still moving: fly again once it stops
      }
    };
    var settled = false, pending = null;
    var flyTo = function (n) {
      if (typeof n.x !== "number") return;
      var d = 140, r = 1 + d / (Math.hypot(n.x, n.y, n.z) || 1);
      graph.cameraPosition({ x: n.x * r, y: n.y * r, z: n.z * r }, n, 1200);
    };
    graph.onEngineStop(function () {
      settled = true;
      if (pending && pending === picked) flyTo(pending);
      pending = null;
    });
    show(null);
    // the search: the names in this view, in a list the browser offers as the reader types
    if (find && names) {
      var byName = {};
      nodes.slice().sort(function (a, b) { return a.name.localeCompare(b.name); }).forEach(function (n) {
        var label = n.name + " (" + words(n.kind) + ")";
        if (byName[label]) return;
        byName[label] = n;
        var o = document.createElement("option");
        o.value = label;
        names.appendChild(o);
      });
      var go = function () {
        var v = find.value.trim(), n = byName[v];
        if (!n && v) {
          var low = v.toLowerCase();
          n = nodes.find(function (x) { return x.name.toLowerCase() === low; }) ||
              nodes.find(function (x) { return x.name.toLowerCase().indexOf(low) === 0; }) ||
              nodes.find(function (x) { return x.name.toLowerCase().indexOf(low) >= 0; });
        }
        if (n) { choose(n, true); }
        else if (chosen && v) { chosen.textContent = "No node in this view is named " + v + "."; }
      };
      find.addEventListener("change", go);
      find.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); go(); } });
    }
    // the key: each type in this view with its colour and count; a switch hides or shows it
    var key = function () {
      if (!keyBox) return;
      keyBox.textContent = "";
      var count = {};
      nodes.forEach(function (n) { count[n.kind] = (count[n.kind] || 0) + 1; });
      Object.keys(count).sort(function (a, b) { return count[b] - count[a] || (a < b ? -1 : 1); }).forEach(function (kind) {
        var li = document.createElement("li"), label = document.createElement("label"), box_ = document.createElement("input");
        box_.type = "checkbox";
        box_.checked = !hidden[kind];
        box_.addEventListener("change", function () {
          hidden[kind] = !box_.checked;
          graph.nodeVisibility(graph.nodeVisibility());
          graph.linkVisibility(graph.linkVisibility());
        });
        var sw = document.createElement("span");
        sw.className = "swatch";
        sw.style.background = colourOf(kind);
        label.appendChild(box_);
        label.appendChild(sw);
        label.appendChild(document.createTextNode(words(kind) + " (" + count[kind].toLocaleString("en") + ")"));
        li.appendChild(label);
        keyBox.appendChild(li);
      });
    };
    key();
    // ?find=<name> opens the view with that node chosen, so a node can be linked to (after the key is drawn,
    // which choosing a node of a hidden type redraws)
    if (find && names && q.get("find")) { find.value = q.get("find"); find.dispatchEvent(new Event("change")); }
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
