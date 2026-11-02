/* Popup de estado por clique (modo escuro neon).
 * O conteúdo HTML vem de `window.POPUP_HTML` (injetado por app.py).
 * Abre ao clicar num estado; fecha ao clicar fora (overlay) ou com Esc. */
(function () {
  "use strict";

  function popupEl() { return document.getElementById("state-popup"); }
  function overlayEl() { return document.getElementById("popup-overlay"); }

  window.__lastMouse = { x: 200, y: 200 };
  document.addEventListener("mousemove", function (e) {
    window.__lastMouse = { x: e.clientX, y: e.clientY };
  });

  function hidePopup() {
    var p = popupEl(), o = overlayEl();
    if (p) p.style.display = "none";
    if (o) o.style.display = "none";
  }

  function showPopup(sector, cd, ev) {
    ensureData();
    var data = window.POPUP_HTML[sector] && window.POPUP_HTML[sector][cd];
    var p = popupEl();
    if (!data || !p) return;

    p.innerHTML = data;
    p.style.display = "block";
    var o = overlayEl();
    if (o) o.style.display = "block";

    var x = ev ? ev.clientX : window.__lastMouse.x;
    var y = ev ? ev.clientY : window.__lastMouse.y;
    var w = p.offsetWidth || 280;
    var h = p.offsetHeight || 300;
    var gap = 16;
    var left = x + gap;
    var top = y + gap;
    if (left + w > window.innerWidth - 8) left = x - w - gap;
    if (top + h > window.innerHeight - 8) top = window.innerHeight - h - 8;
    if (left < 8) left = 8;
    if (top < 8) top = 8;
    p.style.left = left + "px";
    p.style.top = top + "px";
  }

  // (Re)liga o evento de clique nos gráficos Plotly (mapa único e grade).
  var bound = typeof WeakSet !== "undefined" ? new WeakSet() : null;

  function bindGraph(g) {
    if (bound) {
      if (bound.has(g)) return;
      bound.add(g);
    } else {
      if (g.__popupBound) return;
      g.__popupBound = true;
    }
    g.on("plotly_click", function (ev) {
      var cell = g.closest ? g.closest(".map-cell") : null;
      var sector = cell ? cell.getAttribute("data-sector") : null;
      var cd = ev && ev.points && ev.points[0] ? ev.points[0].location : null;
      if (!cd || !sector) {
        hidePopup();
        return;
      }
      showPopup(sector, cd, ev && ev.event ? ev.event : null);
    });
  }

  function bindAll() {
    var graphs = document.querySelectorAll("#main-area .js-plotly-plot");
    for (var i = 0; i < graphs.length; i++) bindGraph(graphs[i]);
  }

  function loadData() {
    var el = document.getElementById("popup-data");
    if (el && el.textContent) {
      try { window.POPUP_HTML = JSON.parse(el.textContent); } catch (e) { window.POPUP_HTML = {}; }
    }
    window.POPUP_HTML = window.POPUP_HTML || {};
  }

  function ensureData() {
    if (!window.POPUP_HTML || !Object.keys(window.POPUP_HTML).length) {
      loadData();
    }
  }

  function ready() {
    loadData();
    bindAll();
    var root = document.getElementById("main-area") || document.body;
    var mo = new MutationObserver(bindAll);
    mo.observe(root, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ready);
  } else {
    ready();
  }

  // Fecha ao clicar no overlay (fora do popup).
  document.addEventListener("click", function (e) {
    var o = overlayEl();
    if (o && e.target === o) hidePopup();
  });

  // Fecha com Esc.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") hidePopup();
  });

  window.__hidePopup = hidePopup;
})();
