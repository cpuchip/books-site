// site.js: typeset a page's math in the reader's browser, and say on the page how it went. books-site, MIT.
// Equations (data-field="latex") are display math; $...$ and $$...$$ inside text fields are inline and display.
// Errata's "In the source:" lines are the source as printed, so they are never typeset.
// A formula KaTeX cannot typeset stays as its source. The HTML keeps the export's LaTeX either way.
(function () {
  "use strict";
  var report = document.getElementById("math-report");
  if (!report || typeof katex === "undefined" || typeof renderMathInElement === "undefined") return;
  var main = document.querySelector("main");
  var macros = {};
  try { macros = JSON.parse(main.getAttribute("data-macros") || "{}"); } catch (e) { macros = {}; }
  var options = function (display) {
    // a fresh copy each time: KaTeX writes \gdef into the macros object it is given
    return { displayMode: display, throwOnError: true, strict: "ignore", macros: Object.assign({}, macros) };
  };
  // a bare alignment row (an & outside any environment) is typeset inside aligned; display only
  var aligned = function (tex) {
    return (/(^|[^\\])&/.test(tex) && !/\\begin\{/.test(tex)) ? "\\begin{aligned}" + tex + "\\end{aligned}" : tex;
  };
  var source = 0;
  Array.prototype.forEach.call(document.querySelectorAll('[data-field="latex"]'), function (el) {
    var out = document.createElement("div");
    out.className = "math";
    try {
      katex.render(aligned(el.textContent), out, options(true));
      el.parentNode.replaceChild(out, el);
    } catch (e) {
      source += 1;
      el.classList.add("tex-source");
      el.title = "Shown as source: " + e.message;
    }
  });
  Array.prototype.forEach.call(document.querySelectorAll("main .tx"), function (el) {
    var o = options(false);
    renderMathInElement(el, {
      delimiters: [{ left: "$$", right: "$$", display: true }, { left: "$", right: "$", display: false }],
      throwOnError: true, strict: "ignore", macros: o.macros,
      errorCallback: function () { source += 1; }
    });
  });
  // a chapter's own text (pandoc's spans): \(...\) inline, \[...\] display; typeset into a new element, so a
  // formula KaTeX cannot typeset keeps its source on the page
  Array.prototype.forEach.call(document.querySelectorAll("main article.text span.math.inline, main article.text span.math.display"), function (el) {
    var display = el.classList.contains("display");
    var tex = el.textContent;
    var open = display ? "\\[" : "\\(", close = display ? "\\]" : "\\)";
    if (tex.slice(0, 2) === open && tex.slice(-2) === close) tex = tex.slice(2, -2);
    var out = document.createElement("span");
    out.className = display ? "math math-display" : "math";
    try {
      katex.render(tex, out, options(display));
      el.parentNode.replaceChild(out, el);
    } catch (e) {
      source += 1;
      el.classList.add("tex-source");
      el.title = "Shown as source: " + e.message;
    }
  });
  var typeset = document.querySelectorAll("main .katex").length;
  // an equation number drawn over its formula's glyphs: the browser check requires none
  var tagOverlap = 0;
  Array.prototype.forEach.call(document.querySelectorAll("main .katex-tag"), function (tag) {
    var tb = tag.getBoundingClientRect(), html = tag.closest(".katex-html");
    var glyphs = html ? html.querySelectorAll(".mord, .mrel, .mbin, .mpunct, .mopen, .mclose, .mop, .minner") : [];
    for (var i = 0; i < glyphs.length; i++) {
      var g = glyphs[i];
      if (tag.contains(g) || !g.textContent.trim()) continue;
      var r = g.getBoundingClientRect();
      if (r.width > 0 && r.right > tb.left + 1 && r.left < tb.right - 1 && r.bottom > tb.top + 1 && r.top < tb.bottom - 1) {
        tagOverlap += 1;
        break;
      }
    }
  });
  // how far the page is wider than its window (0 when nothing overflows): the browser check requires 0
  var root = document.documentElement;
  report.setAttribute("data-overflow", String(Math.max(0, root.scrollWidth - root.clientWidth)));
  report.setAttribute("data-typeset", String(typeset));
  report.setAttribute("data-tag-overlap", String(tagOverlap));
  report.setAttribute("data-macros-used", JSON.stringify(macros));
  report.setAttribute("data-source", String(source));
  report.textContent = typeset + (typeset === 1 ? " formula" : " formulas") + " typeset" +
    (source ? ", " + source + " shown as source" : "");
})();
