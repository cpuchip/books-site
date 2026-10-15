// theme.js: light or dark, as the reader chose (remembered in this browser), else as their system prefers.
// books-site, MIT. Loaded in each page's <head>, so the choice is on <html data-theme> before the page is drawn.
// The button is made here, not in the page: without scripts the site follows the system setting and shows no
// button. A change is announced as a "themechange" event on document (the graph redraws its colours on it).
(function () {
  "use strict";
  var KEY = "books-theme";
  var root = document.documentElement;
  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) { stored = null; }  // storage blocked: follow the system
  if (stored === "light" || stored === "dark") root.setAttribute("data-theme", stored);
  var system = function () {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  };
  var current = function () { return root.getAttribute("data-theme") || system(); };
  var button = null;
  var label = function () {
    if (!button) return;
    var next = current() === "dark" ? "light" : "dark";
    button.textContent = next === "dark" ? "Dark" : "Light";
    button.setAttribute("aria-label", "Switch to the " + next + " theme");
    button.setAttribute("data-next", next);
  };
  var set = function (theme) {
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem(KEY, theme); } catch (e) { /* not remembered; the page still switches */ }
    label();
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
  };
  var place = function () {
    var nav = document.querySelector("header.top nav");
    if (!nav || button) return;
    button = document.createElement("button");
    button.type = "button";
    button.className = "theme-toggle";
    button.addEventListener("click", function () { set(current() === "dark" ? "light" : "dark"); });
    nav.appendChild(button);
    label();
  };
  // a reader who has not chosen follows the system as it changes
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var follow = function () {
      if (!root.getAttribute("data-theme")) {
        label();
        document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: system() } }));
      }
    };
    if (mq.addEventListener) mq.addEventListener("change", follow);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", place);
  else place();
})();
