"""Aplicação Dash: mapas de potencial de realocação de trabalhadores por setor.

Executar com:
    python app.py
e acessar http://localhost:8050
"""

from __future__ import annotations

import json
import logging

import dash
from dash import Input, Output, dcc, html

import figures
import mapping
import preprocessing
from data import RHO, SECTOR_NAMES, UF_SIGLAS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Carregamento único dos dados (executado uma vez na inicialização).
# ---------------------------------------------------------------------------
log.info("=== Inicializando aplicação ===")
log.info("Carregando dados econômicos (VAB, subutilização, informais)...")
RES = preprocessing.compute_all()
log.info("Carregando shapefile do Brasil...")
MAPDATA = mapping.load_map()

MEDIAN = figures._median_potencial(RES["potencial"])

log.info("Calculando fluxos líquidos entre estados...")
FLOW = figures.compute_flows(RES, MAPDATA)

SECTOR_IDS = sorted(SECTOR_NAMES.keys())
SECTOR_OPTIONS = [
    {"label": f"{sid} — {SECTOR_NAMES[sid]}", "value": sid} for sid in SECTOR_IDS
]

# Figuras pré-computadas (dados são estáticos -> troca instantânea).
log.info("Construindo figuras (12 setores)...")
SINGLE_FIGURES = {
    sid: figures.build_sector_figure(sid, RES, MAPDATA, FLOW, show_colorbar=True, show_title=False)
    for sid in SECTOR_IDS
}
GRID_FIGURES = {
    sid: figures.build_sector_figure(sid, RES, MAPDATA, FLOW, show_colorbar=False, show_title=True)
    for sid in SECTOR_IDS
}

CODE_TO_NAME = {code: name for name, code in MAPDATA["name_to_code"].items()}
CODE_TO_SIGLA = {code: UF_SIGLAS[name] for name, code in MAPDATA["name_to_code"].items()}


# ---------------------------------------------------------------------------
# Helpers do painel lateral
# ---------------------------------------------------------------------------
def _is_dark(uf: str) -> bool:
    return RES["potencial"][uf] >= MEDIAN


def _diagnosis_counts(sid: str) -> dict:
    """Contagem 2x2: (excedente/déficit de trabalhadores) x (fundo escuro/claro)."""
    saldo = FLOW["saldo"][sid]
    counts = {
        "surplus_dark": 0,
        "surplus_light": 0,
        "deficit_dark": 0,
        "deficit_light": 0,
    }
    for uf in sorted(MAPDATA["name_to_code"]):
        dark = _is_dark(uf)
        if saldo[uf] >= 0:
            key = "surplus_dark" if dark else "surplus_light"
        else:
            key = "deficit_dark" if dark else "deficit_light"
        counts[key] += 1
    return counts


def _build_panel(sid: str) -> list:
    """Constrói o conteúdo do painel lateral para um setor."""
    direction = RES["direction"][sid]
    rho = RHO[sid]
    rho_bar = RES["rho_bar"]
    classification = "Atração (ρᵢ > ρ̄)" if direction > 0 else "Repulsão (ρᵢ < ρ̄)"
    color = figures.ATTRACTION_COLOR if direction > 0 else figures.REPULSION_COLOR

    counts = _diagnosis_counts(sid)

    top_w = sorted(MAPDATA["name_to_code"], key=lambda u: -RES["w"][sid][u])[:5]
    top_pot = sorted(MAPDATA["name_to_code"], key=lambda u: -RES["potencial"][u])[:5]
    top_borders = sorted(FLOW["flows"][sid], key=lambda b: -b["mag"])[:5]

    def _w_label(uf: str) -> str:
        return f"{RES['w'][sid][uf]:.2%} do VAB nacional"

    def _pot_label(uf: str) -> str:
        return f"{RES['potencial'][uf]:.2%} do potencial nacional"

    def _border_label(b: dict) -> str:
        if b["flux"] >= 0:
            src, dst = b["cd_a"], b["cd_b"]
        else:
            src, dst = b["cd_b"], b["cd_a"]
        return f"{CODE_TO_SIGLA[src]} → {CODE_TO_SIGLA[dst]} — {b['mag']:.2%}"

    panel = [
        html.H3(f"{sid} — {SECTOR_NAMES[sid]}"),
        html.Div(
            [
                html.Span(f"ρᵢ = {rho:.3f}", style={"font-weight": "bold", "margin-right": "10px"}),
                html.Span(f"ρ̄ = {rho_bar:.3f}", style={"margin-right": "10px"}),
                html.Span(classification, style={"color": color, "font-weight": "bold"}),
            ],
            className="rho-line",
        ),
        html.Hr(),

        html.H4("Diagnóstico 2×2"),
        html.Table(
            [
                html.Tr([html.Th(""), html.Th("Fundo escuro"), html.Th("Fundo claro")]),
                html.Tr([
                    html.Td("Excedente de trabalhadores (superávit)", style={"font-weight": "bold"}),
                    html.Td(f"{counts['surplus_dark']} estados", title="forte exportador"),
                    html.Td(f"{counts['surplus_light']} estados", title="exportador limitado"),
                ]),
                html.Tr([
                    html.Td("Déficit de trabalhadores", style={"font-weight": "bold"}),
                    html.Td(f"{counts['deficit_dark']} estados", title="absorve localmente"),
                    html.Td(f"{counts['deficit_light']} estados", title="importador"),
                ]),
            ]
        ),
        html.Ul(
            [
                html.Li(f"Excedente + escuro (forte exportador): {counts['surplus_dark']}"),
                html.Li(f"Excedente + claro (exportador limitado): {counts['surplus_light']}"),
                html.Li(f"Déficit + escuro (absorve localmente): {counts['deficit_dark']}"),
                html.Li(f"Déficit + claro (importador): {counts['deficit_light']}"),
            ]
        ),

        html.H4("Top 5 — concentração setorial (w)"),
        html.Ol([html.Li(f"{UF_SIGLAS[uf]} — {_w_label(uf)}") for uf in top_w]),

        html.H4("Top 5 — potencial de realocação de trabalhadores"),
        html.Ol([html.Li(f"{UF_SIGLAS[uf]} — {_pot_label(uf)}") for uf in top_pot]),

        html.H4("Top 5 — fluxo líquido (fronteiras)"),
        html.Ol([html.Li(_border_label(b)) for b in top_borders]),
    ]
    return panel


# ---------------------------------------------------------------------------
# Popup por clique (conteúdo HTML pré-gerado; JS só posiciona/exibe)
# ---------------------------------------------------------------------------
def _build_popup_html(sid: str, cd: str) -> str:
    name = CODE_TO_NAME[cd]
    sigla = CODE_TO_SIGLA[cd]
    rho = RHO[sid]
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
        f'<div class="pp-sector">{SECTOR_NAMES[sid]}</div>'
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


POPUP_HTML = {
    sid: {cd: _build_popup_html(sid, cd) for cd in CODE_TO_NAME}
    for sid in SECTOR_IDS
}
# Os dados do popup são servidos como texto num elemento oculto e lidos pelo
# `assets/custom.js` (scripts injetados via React não executam).
POPUP_JSON = json.dumps(POPUP_HTML, ensure_ascii=False)


# ---------------------------------------------------------------------------
# App e layout
# ---------------------------------------------------------------------------
app = dash.Dash(__name__, title="Potencial de Realocação de Trabalhadores")

app.layout = html.Div(
    className="app-shell",
    children=[
        html.H1(
            "Potencial de Realocação de Trabalhadores por Setor — Brasil (2022/2024)",
            className="neon-title",
        ),
        html.P(
            "Setas: fluxo líquido de trabalhadores entre estados vizinhos (uma seta por fronteira), "
            "do superávit (potencial > w) ao déficit (w > potencial). Cor da seta: do azul (menor fluxo) "
            "ao vermelho (maior fluxo), normalizada por mapa. Fundo: potencial de realocação de "
            "trabalhadores por UF. Clique num estado para detalhes.",
            className="subtitle",
        ),
        html.Div(
            className="controls",
            children=[
                html.Label("Setor:", className="field-label"),
                dcc.Dropdown(
                    id="sector-dropdown",
                    options=SECTOR_OPTIONS,
                    value=SECTOR_IDS[0],
                    clearable=False,
                    className="dash-dropdown",
                    style={"width": "440px"},
                ),
                dcc.RadioItems(
                    id="view-toggle",
                    options=[
                        {"label": "Mapa único", "value": "single"},
                        {"label": "Grade 12 mapas", "value": "grid"},
                    ],
                    value="single",
                    inline=True,
                    inputStyle={"accentColor": figures.BACKGROUND_HIGH},
                    labelStyle={"color": "#8fd9ae", "marginRight": "14px", "fontSize": "12.5px"},
                ),
            ],
        ),
        html.Div(id="main-area", children=[], style={"position": "relative"}),
        # Legenda geral (fixa, no rodapé do gráfico)
        html.Div(
            className="legend",
            children=[
                html.Strong("Legenda geral"),
                html.Div(
                    [
                        html.Div(
                            style={
                                "display": "inline-block",
                                "width": "160px",
                                "height": "12px",
                                "background": (
                                    f"linear-gradient(to right, {figures.ATTRACTION_COLOR}, "
                                    f"{figures.REPULSION_COLOR})"
                                ),
                                "verticalAlign": "middle",
                                "marginRight": "8px",
                            }
                        ),
                        html.Span(
                            " Cor da seta = magnitude do fluxo (azul = menor, vermelho = maior), "
                            "normalizada por mapa."
                        ),
                    ]
                ),
                html.Div(
                    "Seta = fluxo líquido entre estados vizinhos; direção do superávit "
                    "(potencial > w) ao déficit (w > potencial). Sinais opostos somam; sinais iguais subtraem."
                ),
                html.Div("Comprimento e espessura da seta = magnitude do fluxo (normalizada por setor)."),
                html.Div("Fundo = potencial de realocação de trabalhadores (subutilização + informais) normalizado: escuro = pouco, verde neon = muito."),
                html.Div(
                    "Estados escuros com saldo positivo = forte exportador; escuros com déficit = absorvem localmente; "
                    "claros com saldo positivo = exportador limitado; claros com déficit = importador (precisa de trabalhadores)."
                ),
            ],
        ),
        # Rodapé com fontes
        html.Div(
            className="footer",
            children=[
                "Fontes: IBGE (Contas Regionais 2022, tab06; PNAD Contínua 2024 — subutilização, Tabela 4666; "
                "informais, Tabela 8517); ILAESE (Anuário 2025/26, Tabela II-quinquies, ρᵢ 2024). "
                "Nota: potencial de realocação de trabalhadores = subutilização + informais, sem fator de desconto; "
                "as setas representam o fluxo líquido entre estados vizinhos (saldo = potencial − w); ver README."
            ],
        ),
        # Popup por clique
        html.Div(id="popup-overlay", className="popup-overlay", style={"display": "none"}),
        html.Div(id="state-popup", className="state-popup", style={"display": "none"}),
        html.Div(id="popup-data", style={"display": "none"}, children=POPUP_JSON),
    ],
)


@app.callback(
    Output("main-area", "children"),
    Input("sector-dropdown", "value"),
    Input("view-toggle", "value"),
)
def render_main(sector_id: str, view_mode: str):
    if view_mode == "grid":
        cells = []
        for sid in SECTOR_IDS:
            cells.append(
                html.Div(
                    dcc.Graph(
                        figure=GRID_FIGURES[sid],
                        config={"displayModeBar": False, "responsive": True},
                        style={"width": "100%", "height": "340px"},
                    ),
                    className="map-cell",
                    **{"data-sector": sid},
                )
            )
        grid = html.Div(cells, className="grid")
        return [grid]

    graph = html.Div(
        dcc.Graph(
            figure=SINGLE_FIGURES[sector_id],
            config={"displayModeBar": True, "scrollZoom": True, "responsive": True},
            style={"width": "100%", "height": "720px"},
        ),
        className="map-cell map-single",
        **{"data-sector": sector_id},
    )
    panel = html.Div(_build_panel(sector_id), className="panel")
    return [html.Div([graph, panel], className="single-layout")]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
