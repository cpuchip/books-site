// search.js: search every book on the shelf, in the reader's browser. books-site, MIT.
// The index is the site's own files (search/, written by build/search.py from the finished pages); nothing about
// a query leaves the browser. A query is words, all required, the last also as a prefix while it is being typed;
// "quoted words" must be consecutive. What was found is written into #search-report for the browser check.
(function () {
  "use strict";
  var form = document.getElementById("search-form");
  var input = document.getElementById("q");
  var pick = document.getElementById("search-book");
  var list = document.getElementById("search-results");
  var report = document.getElementById("search-report");
  if (!form || !input || !list || !report) return;
  // made here, not in the page: the built pages carry no hidden element (the oracle refuses one)
  var more = document.createElement("button");
  more.type = "button";
  more.id = "search-more";
  more.textContent = "More results";
  var WORD = /[a-z0-9]+/g;
  // a dollar escaped as \$ (Boyden's money) is a dollar, never a delimiter (as build/search.py reads it)
  var FORMULA = /(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<!\\)\$(?:\\.|[^$\\])*\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/g;
  var KIND = { text: "Text", excerpt: "Excerpt", problem: "Problem", equation: "Equation", exercise_set: "Exercise",
               term: "Term", page: "Page" };
  var PAGE = 20, PHRASE_CANDIDATES = 3000, NEAR_CANDIDATES = 600, NEAR = 8;
  var cache = {};
  var get = function (path) {
    if (!cache[path]) {
      cache[path] = fetch(path).then(function (r) {
        if (!r.ok) throw new Error(path + " answered " + r.status);
        return r.json();
      });
    }
    return cache[path];
  };
  var words = function (s) { return (s.replace(FORMULA, " ").toLowerCase().match(WORD) || []); };
  var decode = function (delta) {
    var out = new Array(delta.length), at = 0;
    for (var i = 0; i < delta.length; i++) { at += delta[i]; out[i] = at; }
    return out;
  };
  var esc = function (s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  };

  // the query: required words (each with its own postings), the phrases, and the last word as a prefix
  var parse = function (q) {
    var phrases = [], rest = q.replace(/"([^"]*)"?/g, function (m, p) {
      var w = words(p);
      if (w.length) phrases.push(w);
      return " " + p + " ";
    });
    var all = words(rest);
    var open = /[a-z0-9]$/i.test(q);  // the query ends inside a word, not after a space or a closing quote
    var seen = {}, terms = [];
    all.forEach(function (w, i) {
      var prefix = open && i === all.length - 1;
      var key = w + (prefix ? "*" : "");
      if (!seen[key]) { seen[key] = true; terms.push({ word: w, prefix: prefix }); }
    });
    return { terms: terms, phrases: phrases };
  };

  var postings = function (term) {
    return get("p/" + term.word[0] + ".json").then(function (shard) {
      var hit = {}, exact = {};
      var add = function (w) {
        decode(shard[w]).forEach(function (d) {
          hit[d] = true;
          if (w === term.word) exact[d] = true;
        });
      };
      if (term.prefix) {
        Object.keys(shard).forEach(function (w) { if (w.lastIndexOf(term.word, 0) === 0) add(w); });
      } else if (Object.prototype.hasOwnProperty.call(shard, term.word)) {
        add(term.word);
      }
      return { ids: hit, exact: exact };
    }).catch(function () { return { ids: {}, exact: {} }; });
  };

  var text = function (docs, d) {
    var n = Math.floor(d / docs.chunk);
    return get("t/" + n + ".json").then(function (chunk) { return chunk[d - n * docs.chunk]; });
  };

  var pattern = function (t) { return t.word + (t.prefix ? "[a-z0-9]*" : "(?![a-z0-9])"); };
  // a window of the unit's text around the words standing together (else its first matched word), never cutting a
  // formula, with the words marked
  var snippet = function (s, terms, macros) {
    var lower = s.toLowerCase(), at = -1;
    if (terms.length > 1) {
      var all = new RegExp("(^|[^a-z0-9])" + terms.map(pattern).join("[^a-z0-9]+"), "g"), m0;
      while ((m0 = all.exec(lower))) {
        if (!inFormula(s, m0.index + m0[1].length)) { at = m0.index + m0[1].length; break; }
      }
    }
    if (at < 0) terms.forEach(function (t) {
      var re = new RegExp("(^|[^a-z0-9])" + t.word + (t.prefix ? "" : "(?![a-z0-9])"), "g"), m;
      while ((m = re.exec(lower))) {
        var i = m.index + m[1].length;
        if (!inFormula(s, i) && (at < 0 || i < at)) { at = i; }
        if (at >= 0) break;
      }
    });
    var start = Math.max(0, (at < 0 ? 0 : at) - 90), end = Math.min(s.length, start + 260);
    FORMULA.lastIndex = 0;
    var m;
    while ((m = FORMULA.exec(s))) {
      var a = m.index, b = m.index + m[0].length;
      if (a < start && b > start) start = a;
      if (a < end && b > end) end = b;
    }
    var piece = s.slice(start, end), out = "", last = 0;
    FORMULA.lastIndex = 0;
    // one pass over the plain text, the pieces between escaped: marking escaped text would let a word such as
    // "mark" or "amp" match the markup itself
    var any = new RegExp("(^|[^a-z0-9])(" + terms.map(function (t) {
      return t.word + (t.prefix ? "[a-z0-9]*" : "");
    }).join("|") + ")(?![a-z0-9])", "gi");
    var mark = function (plain) {
      plain = plain.replace(/\\\$/g, "$");
      var out = "", last = 0, m;
      any.lastIndex = 0;
      while ((m = any.exec(plain))) {
        var at = m.index + m[1].length;
        out += esc(plain.slice(last, at)) + "<mark>" + esc(m[2]) + "</mark>";
        last = at + m[2].length;
      }
      return out + esc(plain.slice(last));
    };
    while ((m = FORMULA.exec(piece))) {
      out += mark(piece.slice(last, m.index)) + formula(m[0], macros);
      last = m.index + m[0].length;
    }
    out += mark(piece.slice(last));
    return (start > 0 ? "…" : "") + out + (end < s.length ? "…" : "");
  };
  var inFormula = function (s, i) {
    FORMULA.lastIndex = 0;
    var m;
    while ((m = FORMULA.exec(s))) {
      if (m.index <= i && i < m.index + m[0].length) return true;
      if (m.index > i) return false;
    }
    return false;
  };
  // a formula typesets inline, with its book's macros; an environment (align*, gather*) or a \tag only in display
  var formula = function (src, macros) {
    var tex = src.replace(/^\$\$|\$\$$|^\$|\$$|^\\\(|\\\)$|^\\\[|\\\]$/g, "");
    var display = /\\begin\{|\\tag/.test(tex);
    if (typeof katex === "undefined") return '<code class="tex-source">' + esc(src) + "</code>";
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: true, strict: "ignore",
                                         macros: Object.assign({}, macros || {}) });
    } catch (e) {
      return '<code class="tex-source">' + esc(src) + "</code>";
    }
  };

  var shown = [], showing = 0, meta = null, seq = 0;
  var renderMore = function () {
    var mine = seq, slice = shown.slice(showing, showing + PAGE);
    showing += slice.length;
    return Promise.all(slice.map(function (r) { return text(meta.docs, r.d); })).then(function (texts) {
      if (mine !== seq) return;  // a later query has begun: these results are no longer the page's
      slice.forEach(function (r, i) {
        var doc = meta.docs.docs[r.d], page = meta.pages.pages[doc[0]];
        var kind = meta.docs.kinds[doc[2]];
        var href = "../" + page[0] + (doc[1] ? "#" + doc[1] : "");
        var li = document.createElement("li");
        li.className = "hit";
        li.innerHTML = '<p class="where"><span class="kind">' + esc(KIND[kind] || kind) + "</span> " +
          '<a href="' + esc(href) + '">' + esc(page[1]) + "</a></p>" +
          '<p class="snip">' + snippet(texts[i], r.terms, page[2] >= 0 ? meta.pages.books[page[2]][2] : {}) + "</p>";
        list.appendChild(li);
      });
      if (showing < shown.length) { list.parentNode.insertBefore(more, list.nextSibling); }
      else if (more.parentNode) { more.parentNode.removeChild(more); }
    });
  };

  var run = function (q, book) {
    var mine = ++seq;  // a later query wins: an earlier one still loading writes nothing
    list.innerHTML = "";
    shown = []; showing = 0;
    if (more.parentNode) more.parentNode.removeChild(more);
    var query = parse(q);
    report.setAttribute("data-query", q);
    if (!query.terms.length) {
      report.setAttribute("data-results", "0");
      report.textContent = "Type a word or two.";
      return Promise.resolve();
    }
    report.textContent = "Searching…";
    return Promise.all([get("pages.json"), get("docs.json")]).then(function (base) {
      meta = { pages: base[0], docs: base[1] };
      return Promise.all(query.terms.map(postings)).then(function (lists) {
        var order = lists.map(function (l, i) { return i; }).sort(function (a, b) {
          return Object.keys(lists[a].ids).length - Object.keys(lists[b].ids).length;
        });
        var cand = Object.keys(lists[order[0]].ids).map(Number).filter(function (d) {
          return order.every(function (i) { return lists[i].ids[d]; });
        });
        if (book !== "") {
          cand = cand.filter(function (d) {
            var b = meta.pages.pages[meta.docs.docs[d][0]][2];
            return b >= 0 && meta.pages.books[b][0] === book;
          });
        }
        // every candidate holds every word, so the order is: the word as typed before a longer word it begins
        // (sine before sines), a unit before the rest of a page, then the site's page order
        var exact = function (d) {
          var n = 0;
          lists.forEach(function (l) { if (l.exact[d]) n += 1; });
          return n;
        };
        var unit = function (d) { return meta.docs.kinds[meta.docs.docs[d][2]] === "page" ? 0 : 1; };
        cand.sort(function (a, b) { return exact(b) - exact(a) || unit(b) - unit(a) || a - b; });
        // with few enough candidates, those whose words stand together (2) or near (1) come first
        var near = {};
        var nearness = cand.length > 1 && cand.length <= NEAR_CANDIDATES && query.terms.length > 1 ?
          Promise.all(cand.map(function (d) { return text(meta.docs, d); })).then(function (texts) {
            var res = query.terms.map(function (t) { return new RegExp("^" + pattern(t)); });
            cand.forEach(function (d, i) {
              var w = words(texts[i]), best = 0;
              for (var k = 0; k < w.length && best < 2; k++) {
                if (!res[0].test(w[k])) continue;
                var ok = true;
                for (var j = 1; j < res.length; j++) { if (!res[j].test(w[k + j] || "")) { ok = false; break; } }
                if (ok) { best = 2; break; }
                var win = w.slice(k, k + NEAR);
                if (res.every(function (r) { return win.some(function (x) { return r.test(x); }); })) best = 1;
              }
              near[d] = best;
            });
            cand.sort(function (a, b) { return exact(b) - exact(a) || near[b] - near[a] || unit(b) - unit(a) || a - b; });
          }) : Promise.resolve();
        return nearness.then(function () { return cand; });
      }).then(function (cand) {
        var check = query.phrases.length ? cand.slice(0, PHRASE_CANDIDATES) : cand;
        var keep = query.phrases.length ? Promise.all(check.map(function (d) { return text(meta.docs, d); }))
          .then(function (texts) {
            return check.filter(function (d, i) {
              var w = " " + words(texts[i]).join(" ") + " ";
              return query.phrases.every(function (p) { return w.indexOf(" " + p.join(" ") + " ") >= 0; });
            });
          }) : Promise.resolve(cand);
        return keep.then(function (found) {
          if (mine !== seq) return;
          shown = found.map(function (d) { return { d: d, terms: query.terms }; });
          report.setAttribute("data-results", String(shown.length));
          var first = shown[0] && meta.docs.docs[shown[0].d];
          report.setAttribute("data-first", first ? meta.pages.pages[first[0]][0] + (first[1] ? "#" + first[1] : "") : "");
          report.textContent = shown.length ? shown.length.toLocaleString("en") + (shown.length === 1 ? " place" : " places") +
            (check.length < cand.length ? " (the phrase was checked in the first " + check.length.toLocaleString("en") + ")" : "") + "." :
            "Nothing found.";
          return renderMore();
        });
      });
    }).catch(function (e) { report.textContent = "The search could not load: " + e.message; });
  };

  var fromUrl = function () {
    var p = new URLSearchParams(location.search);
    input.value = p.get("q") || "";
    if (pick) pick.value = p.get("book") || "";
    if (input.value) run(input.value, pick ? pick.value : "");
  };
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var p = new URLSearchParams();
    if (input.value) p.set("q", input.value);
    if (pick && pick.value) p.set("book", pick.value);
    history.replaceState(null, "", "?" + p.toString());
    run(input.value, pick ? pick.value : "");
  });
  more.addEventListener("click", function () { renderMore(); });
  fromUrl();
})();
