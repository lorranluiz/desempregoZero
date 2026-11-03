"""Gera `docs/index.html`: versão estática e interativa do app, para GitHub Pages.

Reutiliza `data`/`preprocessing`/`mapping`/`figures` para pré-computar as 24
figuras Plotly (12 single + 12 grid), os 12 painéis laterais e os popups por
clique, e embute tudo (CSS, JS e dados) num único HTML autocontido, sem servidor.

O GeoJSON das 27 UFs é idêntico nas 24 figuras, por isso é embutido uma única
vez e reinjetado nos traces em tempo de execução (evita um HTML de ~10 MB).
"""

from __future__ import annotations

import json
import os

import data
import figures
import mapping
import preprocessing

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Dados e figuras (idênticos ao servidor)
# ---------------------------------------------------------------------------
RES = preprocessing.compute_all()
MAPDATA = mapping.load_map()
FLOW = figures.compute_flows(RES, MAPDATA)
MEDIAN = figures._median_potencial(RES["potencial"])
SECTOR_IDS = sorted(data.SECTOR_NAMES.keys())
CODE_TO_NAME = {code: name for name, code in MAPDATA["name_to_code"].items()}
CODE_TO_SIGLA = {code: data.UF_SIGLAS[name] for name, code in MAPDATA["name_to_code"].items()}


def _is_dark(uf: str) -> bool:
    return RES["potencial"][uf] >= MEDIAN


SINGLE_FIGURES = {
    sid: figures.build_sector_figure(sid, RES, MAPDATA, FLOW, show_colorbar=True, show_title=False)
    for sid in SECTOR_IDS
}
GRID_FIGURES = {
    sid: figures.build_sector_figure(sid, RES, MAPDATA, FLOW, show_colorbar=False, show_title=True)
    for sid in SECTOR_IDS
}


def _fig_dict(fig) -> dict:
    d = json.loads(fig.to_json())
    for t in d["data"]:
        if t.get("type") == "choropleth":
            t.pop("geojson", None)
    return d


SINGLE_JSON = {sid: _fig_dict(f) for sid, f in SINGLE_FIGURES.items()}
GRID_JSON = {sid: _fig_dict(f) for sid, f in GRID_FIGURES.items()}
GEOJSON = MAPDATA["geojson"]

# ---------------------------------------------------------------------------
# Painel lateral e popup (replicam app.py, mas como strings HTML)
# ---------------------------------------------------------------------------


def _diagnosis_counts(sid: str) -> dict:
    saldo = FLOW["saldo"][sid]
    counts = {"surplus_dark": 0, "surplus_light": 0, "deficit_dark": 0, "deficit_light": 0}
    for uf in sorted(MAPDATA["name_to_code"]):
        dark = _is_dark(uf)
        if saldo[uf] >= 0:
            key = "surplus_dark" if dark else "surplus_light"
        else:
            key = "deficit_dark" if dark else "deficit_light"
        counts[key] += 1
    return counts


def _border_label(b: dict) -> str:
    if b["flux"] >= 0:
        src, dst = b["cd_a"], b["cd_b"]
    else:
        src, dst = b["cd_b"], b["cd_a"]
    return f"{CODE_TO_SIGLA[src]} → {CODE_TO_SIGLA[dst]} — {b['mag']:.2%}"


def panel_html(sid: str) -> str:
    direction = RES["direction"][sid]
    rho = data.RHO[sid]
    rho_bar = RES["rho_bar"]
    classification = "Atração (ρᵢ > ρ̄)" if direction > 0 else "Repulsão (ρᵢ < ρ̄)"
    color = figures.ATTRACTION_COLOR if direction > 0 else figures.REPULSION_COLOR
    counts = _diagnosis_counts(sid)

    top_w = sorted(MAPDATA["name_to_code"], key=lambda u: -RES["w"][sid][u])[:5]
    top_pot = sorted(MAPDATA["name_to_code"], key=lambda u: -RES["potencial"][u])[:5]
    top_borders = sorted(FLOW["flows"][sid], key=lambda b: -b["mag"])[:5]

    w_items = "".join(
        f"<li>{data.UF_SIGLAS[uf]} — {RES['w'][sid][uf]:.2%} do VAB nacional</li>" for uf in top_w
    )
    pot_items = "".join(
        f"<li>{data.UF_SIGLAS[uf]} — {RES['potencial'][uf]:.2%} do potencial nacional</li>" for uf in top_pot
    )
    border_items = "".join(f"<li>{_border_label(b)}</li>" for b in top_borders)

    return (
        f"<h3>{sid} — {data.SECTOR_NAMES[sid]}</h3>"
        f'<div class="rho-line">'
        f'<span style="font-weight: bold; margin-right: 10px;">ρᵢ = {rho:.3f}</span>'
        f'<span style="margin-right: 10px;">ρ̄ = {rho_bar:.3f}</span>'
        f'<span style="color: {color}; font-weight: bold;">{classification}</span>'
        f"</div>"
        f"<hr>"
        f"<h4>Diagnóstico 2×2</h4>"
        f"<table>"
        f"<tr><th></th><th>Fundo escuro</th><th>Fundo claro</th></tr>"
        f'<tr><td style="font-weight: bold;">Excedente de trabalhadores (superávit)</td>'
        f'<td title="forte exportador">{counts["surplus_dark"]} estados</td>'
        f'<td title="exportador limitado">{counts["surplus_light"]} estados</td></tr>'
        f'<tr><td style="font-weight: bold;">Déficit de trabalhadores</td>'
        f'<td title="absorve localmente">{counts["deficit_dark"]} estados</td>'
        f'<td title="importador">{counts["deficit_light"]} estados</td></tr>'
        f"</table>"
        f"<ul>"
        f'<li>Excedente + escuro (forte exportador): {counts["surplus_dark"]}</li>'
        f'<li>Excedente + claro (exportador limitado): {counts["surplus_light"]}</li>'
        f'<li>Déficit + escuro (absorve localmente): {counts["deficit_dark"]}</li>'
        f'<li>Déficit + claro (importador): {counts["deficit_light"]}</li>'
        f"</ul>"
        f"<h4>Top 5 — concentração setorial (w)</h4>"
        f"<ol>{w_items}</ol>"
        f"<h4>Top 5 — potencial de realocação de trabalhadores</h4>"
        f"<ol>{pot_items}</ol>"
        f"<h4>Top 5 — fluxo líquido (fronteiras)</h4>"
        f"<ol>{border_items}</ol>"
    )


def popup_html(sid: str, cd: str) -> str:
    name = CODE_TO_NAME[cd]
    sigla = CODE_TO_SIGLA[cd]
    rho = data.RHO[sid]
    rho_bar = RES["rho_bar"]
    color = figures.ATTRACTION_COLOR if rho > rho_bar else figures.REPULSION_COLOR
    sal = FLOW["saldo"][sid].get(name, 0.0)
    saldo_label = "excedente de trabalhadores" if sal >= 0 else "déficit de trabalhadores"
    sub = RES["subutilizacao"].get(name, 0.0)
    inf = RES["informais"].get(name, 0.0)
    total = RES["potencial_bruto"].get(name, 0.0)
    share = RES["potencial"].get(name, 0.0)
    w = RES["w"][sid].get(name, 0.0)
    interp = figures._state_interpretation(sal, _is_dark(name))

    def row(k: str, v: str) -> str:
        return f'<div class="pp-row"><span class="pp-k">{k}</span><span class="pp-v">{v}</span></div>'

    return (
        f'<div class="pp-card" style="border-color:{color};box-shadow:0 0 18px {color}55,0 0 3px {color};">'
        f'<div class="pp-head" style="color:{color};">{sigla} · {name}</div>'
        f'<div class="pp-sector">{data.SECTOR_NAMES[sid]}</div>'
        f'<div class="pp-meta">ρᵢ {rho:.3f} &nbsp;·&nbsp; ρ̄ {rho_bar:.3f} &nbsp;·&nbsp; '
        f'<span style="color:{color};">{saldo_label} {sal:+.2%}</span></div>'
        f'<div class="pp-block">POTENCIAL DE REALOCAÇÃO DE TRABALHADORES</div>'
        + row("Subutilização", f"{sub:,.0f}")
        + row("Informais", f"{inf:,.0f}")
        + row("Total", f"{total:,.0f}")
        + row("Share nacional", f"{share:.2%}")
        + row("VAB setorial (w)", f"{w:.2%}")
        + f'<div class="pp-block">INTERPRETAÇÃO</div>'
        + f'<div class="pp-interp">{interp}</div>'
        + "</div>"
    )


PANELS = {sid: panel_html(sid) for sid in SECTOR_IDS}
POPUP = {sid: {cd: popup_html(sid, cd) for cd in CODE_TO_NAME} for sid in SECTOR_IDS}
POPUP_JSON = json.dumps(POPUP, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Leitura de assets
# ---------------------------------------------------------------------------
with open(os.path.join(HERE, "assets", "style.css"), encoding="utf-8") as f:
    CSS = f.read()

with open(os.path.join(HERE, "assets", "custom.js"), encoding="utf-8") as f:
    CUSTOM_JS = f.read()

# Expor a ligação de cliques para o controlador re-ligar após cada render.
CUSTOM_JS = CUSTOM_JS.replace(
    "  function ready() {",
    "  window.__bindGraphs = bindAll;\n\n  function ready() {",
)

SECTOR_OPTIONS = "".join(
    f'<option value="{sid}">{sid} — {data.SECTOR_NAMES[sid]}</option>' for sid in SECTOR_IDS
)

# ---------------------------------------------------------------------------
# Template HTML
# ---------------------------------------------------------------------------
TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
__CSS__

/* Dropdown estático (substitui o dcc.Dropdown do Dash) */
.sector-select {
  background: var(--bg2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  width: 440px;
  max-width: 90vw;
  box-shadow: 0 0 10px rgba(0, 255, 157, 0.10);
  outline: none;
  cursor: pointer;
}
.sector-select:hover, .sector-select:focus { border-color: var(--green); }
.sector-select option { background: var(--bg2); color: var(--text); }
</style>
</head>
<body>
<div class="app-shell">
  <h1 class="neon-title">Potencial de Realocação de Trabalhadores por Setor — Brasil (2022/2024)</h1>
  <p class="subtitle">Setas: fluxo líquido de trabalhadores entre estados vizinhos (uma seta por fronteira), do superávit (potencial &gt; w) ao déficit (w &gt; potencial). Cor da seta: do azul (menor fluxo) ao vermelho (maior fluxo), normalizada por mapa. Fundo: potencial de realocação de trabalhadores por UF. Clique num estado para detalhes.</p>

  <div class="controls">
    <label class="field-label">Setor:</label>
    <select id="sector-dropdown" class="sector-select">__SECTOR_OPTIONS__</select>
    <div class="view-toggle" id="view-toggle">
      <label><input type="radio" name="view" value="single" checked> Mapa único</label>
      <label><input type="radio" name="view" value="grid"> Grade 12 mapas</label>
    </div>
  </div>

  <div id="main-area" style="position: relative;"></div>

  <div class="legend">
    <strong>Legenda geral</strong>
    <div>
      <span style="display: inline-block; width: 160px; height: 12px; background: linear-gradient(to right, #00e5ff, #ff2d55); vertical-align: middle; margin-right: 8px;"></span>
      <span> Cor da seta = magnitude do fluxo (azul = menor, vermelho = maior), normalizada por mapa.</span>
    </div>
    <div>Seta = fluxo líquido entre estados vizinhos; direção do superávit (potencial &gt; w) ao déficit (w &gt; potencial). Sinais opostos somam; sinais iguais subtraem.</div>
    <div>Comprimento e espessura da seta = magnitude do fluxo (normalizada por setor).</div>
    <div>Fundo = potencial de realocação de trabalhadores (subutilização + informais) normalizado: escuro = pouco, verde neon = muito.</div>
    <div>Estados escuros com saldo positivo = forte exportador; escuros com déficit = absorvem localmente; claros com saldo positivo = exportador limitado; claros com déficit = importador (precisa de trabalhadores).</div>
  </div>

  <div class="footer">
    Fontes: IBGE (Contas Regionais 2022, tab06; PNAD Contínua 2024 — subutilização, Tabela 4666; informais, Tabela 8517); ILAESE (Anuário 2025/26, Tabela II-quinquies, ρᵢ 2024). Nota: potencial de realocação de trabalhadores = subutilização + informais, sem fator de desconto; as setas representam o fluxo líquido entre estados vizinhos (saldo = potencial − w); ver README.
  </div>

  <div id="popup-overlay" class="popup-overlay" style="display: none;"></div>
  <div id="state-popup" class="state-popup" style="display: none;"></div>
  <div id="popup-data" style="display: none;">__POPUP_JSON__</div>
</div>

<script>
__CUSTOM_JS__
</script>

<script>
(function () {
  "use strict";
  var SECTOR_IDS = __SECTOR_IDS__;
  var SINGLE_FIGS = __SINGLE_JSON__;
  var GRID_FIGS = __GRID_JSON__;
  var PANELS = __PANELS__;
  var GEOJSON = __GEOJSON__;

  var sectorSelect = document.getElementById("sector-dropdown");
  var viewToggle = document.getElementById("view-toggle");
  var mainArea = document.getElementById("main-area");
  var currentSector = SECTOR_IDS[0];
  var currentView = "single";

  function withGeo(fig) {
    fig.data.forEach(function (t) {
      if (t.type === "choropleth") { t.geojson = GEOJSON; }
    });
    return fig.data;
  }

  function renderSingle(sid) {
    var fig = SINGLE_FIGS[sid];
    mainArea.innerHTML =
      '<div class="single-layout">' +
        '<div class="map-cell map-single" data-sector="' + sid + '">' +
          '<div id="single-map" style="width:100%;height:720px;"></div>' +
        '</div>' +
        '<div class="panel">' + PANELS[sid] + '</div>' +
      '</div>';
    Plotly.newPlot("single-map", withGeo(fig), fig.layout,
      { responsive: true, displayModeBar: true, scrollZoom: true });
    if (window.__bindGraphs) { window.__bindGraphs(); }
  }

  function renderGrid() {
    var cells = "";
    SECTOR_IDS.forEach(function (sid) {
      cells += '<div class="map-cell" data-sector="' + sid + '">' +
               '<div id="grid-map-' + sid + '" style="width:100%;height:340px;"></div></div>';
    });
    mainArea.innerHTML = '<div class="grid">' + cells + '</div>';
    SECTOR_IDS.forEach(function (sid) {
      var fig = GRID_FIGS[sid];
      Plotly.newPlot("grid-map-" + sid, withGeo(fig), fig.layout,
        { responsive: true, displayModeBar: false });
    });
    if (window.__bindGraphs) { window.__bindGraphs(); }
  }

  function render() {
    if (currentView === "grid") { renderGrid(); } else { renderSingle(currentSector); }
  }

  sectorSelect.addEventListener("change", function (e) {
    currentSector = e.target.value;
    if (currentView === "single") { renderSingle(currentSector); }
  });

  var radios = viewToggle.querySelectorAll("input[name=view]");
  for (var i = 0; i < radios.length; i++) {
    radios[i].addEventListener("change", function (e) {
      if (e.target.checked) { currentView = e.target.value; render(); }
    });
  }

  render();
})();
</script>
</body>
</html>
"""


def main() -> None:
    html = TEMPLATE
    html = html.replace("__CSS__", CSS)
    html = html.replace("__CUSTOM_JS__", CUSTOM_JS)
    html = html.replace("__TITLE__", "Potencial de Realocação de Trabalhadores")
    html = html.replace("__SECTOR_OPTIONS__", SECTOR_OPTIONS)
    html = html.replace("__SECTOR_IDS__", json.dumps(SECTOR_IDS))
    html = html.replace("__SINGLE_JSON__", json.dumps(SINGLE_JSON, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__GRID_JSON__", json.dumps(GRID_JSON, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__GEOJSON__", json.dumps(GEOJSON, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__PANELS__", json.dumps(PANELS, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__POPUP_JSON__", POPUP_JSON)

    outdir = os.path.join(HERE, "docs")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "index.html")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    print("gerado", outpath, f"({os.path.getsize(outpath):,} bytes)")


if __name__ == "__main__":
    main()
