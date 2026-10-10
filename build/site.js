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
  var typeset = document.querySelectorAll("main .katex").length;
  // how far the page is wider than its window (0 when nothing overflows): the browser check requires 0
  var root = document.documentElement;
  report.setAttribute("data-overflow", String(Math.max(0, root.scrollWidth - root.clientWidth)));
  report.setAttribute("data-typeset", String(typeset));
  report.setAttribute("data-macros-used", JSON.stringify(macros));
  report.setAttribute("data-source", String(source));
  report.textContent = typeset + (typeset === 1 ? " formula" : " formulas") + " typeset" +
    (source ? ", " + source + " shown as source" : "");
})();
