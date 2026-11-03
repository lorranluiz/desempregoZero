"""Construção das figuras Plotly (choropleth de fundo + setas de fluxo).

A camada de fundo (potencial de realocação de trabalhadores) é a mesma para os 12 setores. O
que muda entre setores são as **setas de fluxo líquido entre estados
vizinhos**, desenhadas nas fronteiras.

Modelo (fluxo entre estados):
  * saldo[r] = potencial[r] - w[i][r]  (superávit > 0 = "excedente de
    trabalhadores"; déficit < 0 = "déficit de trabalhadores");
  * para cada fronteira A-B: fluxo(A->B) = saldo[A] - saldo[B]. Sinais
    opostos somam; sinais iguais subtraem. A seta aponta do superávit ao
    déficit, com comprimento/espessura proporcionais a |fluxo|.

Tema retro-futurista "verde neon" (modo escuro):
  * cor da seta codifica a magnitude do fluxo líquido, do azul (menor) ao
    vermelho (maior), normalizada pelo mínimo/máximo de cada mapa;
  * fundo escuro (#07120b) -> verde neon (#00ff9d).
"""

from __future__ import annotations

import colorsys
import math

import numpy as np
import plotly.graph_objects as go

from data import RHO, SECTOR_NAMES, UF_NAMES

# Paleta neon (modo escuro). `ATTRACTION_COLOR` e `REPULSION_COLOR` são os
# extremos da escala de magnitude das setas: azul = menor fluxo, vermelho =
# maior fluxo (lidos em tempo de execução, para permitir a sobrescrita por
# `export_maps.py`).
ATTRACTION_COLOR = "#00e5ff"
REPULSION_COLOR = "#ff2d55"
BACKGROUND_LOW = "#07120b"
BACKGROUND_HIGH = "#00ff9d"

MAP_BG = "#050a06"
LAND_COLOR = "#07120b"
OCEAN_COLOR = "#040805"
LAKE_COLOR = "#040805"
STATE_BORDER = "#123a24"
COLORBAR_TEXT = "#9fffc7"

# ---------------------------------------------------------------------------
# Desenho das setas de fluxo (traces `Scattergeo`, posicionados por lon/lat).
# ---------------------------------------------------------------------------
ARROW_LEN_MIN = 0.22    # graus — comprimento mínimo da seta
ARROW_LEN_MAX = 0.75    # graus — comprimento máximo da seta
ARROW_WIDTH_BASE = 1.0  # espessura mínima do eixo (px)
ARROW_WIDTH_SCALE = 4.0  # espessura = base + scale * mag_norm
ARROW_HEAD_ANGLE = 30.0  # meia-abertura da ponta (graus)
ARROW_HEAD_FRAC = 0.45   # ponta = fração do comprimento da seta
ARROW_HEAD_MIN = 0.10    # comprimento mínimo da ponta (graus)
ARROW_HEAD_MAX = 0.26    # comprimento máximo da ponta (graus)

# Limiar de visibilidade: omite fronteiras cujo fluxo (após compressão por
# raiz quadrada e normalização por setor) fique abaixo deste valor.
FLOW_LIMIAR = 0.30

# Margem (em graus) aplicada ao enquadramento do mapa.
GEO_MARGIN = 1.2


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    """Converte "#rrggbb" em tupla RGB (0..1)."""
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    """Converte tupla RGB (0..1) em "#rrggbb"."""
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def _lerp_color(c_low: str, c_high: str, t: float) -> str:
    """Interpola entre duas cores no espaço HSL, mantendo o tom vibrante.

    O matiz (hue) cresce de `c_low` (azul) até `c_high` (vermelho) pelo caminho
    curto (azul -> roxo -> magenta -> vermelho), sem passar por cinza. `t` em
    [0, 1]: 0 -> `c_low`, 1 -> `c_high`.
    """
    r1, g1, b1 = _hex_to_rgb(c_low)
    r2, g2, b2 = _hex_to_rgb(c_high)
    h1, l1, s1 = colorsys.rgb_to_hls(r1, g1, b1)
    h2, l2, s2 = colorsys.rgb_to_hls(r2, g2, b2)
    if h2 < h1:
        h2 += 1.0
    h = h1 + (h2 - h1) * t
    l = l1 + (l2 - l1) * t
    s = s1 + (s2 - s1) * t
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return _rgb_to_hex((r, g, b))


def _median_potencial(potencial: dict[str, float]) -> float:
    """Limiar 'escuro/claro' (mediana do potencial). Documentado no README."""
    vals = np.array([potencial.get(uf, 0.0) for uf in UF_NAMES])
    return float(np.median(vals))


def compute_flows(res: dict, mapdata: dict) -> dict:
    """Calcula o saldo por estado e o fluxo líquido por fronteira, por setor.

    Retorna:
      { "saldo": {sid: {nome_canonico: float}},
        "flows": {sid: [ {cd_a, cd_b, mid, dir, flux, mag}, ... ]},
        "sector_max": {sid: float} }   # maior |fluxo| do setor (normalização)

    A magnitude é depois comprimida por raiz quadrada e normalizada pelo
    máximo do setor (ver `build_sector_figure`), para que setores com forte
    concentração (ex.: extrativas no RJ) não "esmaguem" as demais setas.
    """
    borders = mapdata["borders"]
    name_to_code = mapdata["name_to_code"]
    code_to_name = {v: k for k, v in name_to_code.items()}

    saldo: dict[str, dict[str, float]] = {}
    flows: dict[str, list[dict]] = {}
    sector_max: dict[str, float] = {}

    for sid in SECTOR_NAMES:
        s = {
            uf: res["potencial"][uf] - res["w"][sid][uf] for uf in UF_NAMES
        }
        saldo[sid] = s

        sector_flows: list[dict] = []
        smax = 0.0
        for b in borders:
            name_a = code_to_name[b["cd_a"]]
            name_b = code_to_name[b["cd_b"]]
            flux = s[name_a] - s[name_b]
            mag = abs(flux)
            smax = max(smax, mag)
            sector_flows.append({**b, "flux": flux, "mag": mag})
        flows[sid] = sector_flows
        sector_max[sid] = smax if smax > 0 else 1.0

    return {
        "saldo": saldo,
        "flows": flows,
        "sector_max": sector_max,
    }


def _state_interpretation(saldo: float, is_dark: bool) -> str:
    """Interpretação por estado no novo modelo (superávit/déficit x fundo)."""
    if saldo >= 0:  # superávit -> "excedente de trabalhadores"
        return "forte exportador" if is_dark else "exportador limitado"
    # déficit -> "déficit de trabalhadores"
    return "absorve localmente" if is_dark else "importador (precisa de trabalhadores)"


def _add_flow_arrow(
    fig: go.Figure,
    mid: tuple[float, float],
    dir_unit: tuple[float, float],
    mag_norm: float,
    color: str,
) -> None:
    """Adiciona uma seta de fluxo centrada no ponto médio da fronteira.

    `dir_unit` aponta do superávit ao déficit; a seta atravessa a fronteira.
    Comprimento e espessura são proporcionais a `mag_norm` (0..1). A ponta é
    desenhada como um "V" (chevron) de linha na extremidade de chegada, de modo
    que a seta tenha a ponta exatamente na direção do fluxo.
    """
    length_deg = ARROW_LEN_MIN + (ARROW_LEN_MAX - ARROW_LEN_MIN) * mag_norm
    width_px = ARROW_WIDTH_BASE + ARROW_WIDTH_SCALE * mag_norm

    dx, dy = dir_unit
    half = length_deg / 2.0
    tail = (mid[0] - dx * half, mid[1] - dy * half)
    tip = (mid[0] + dx * half, mid[1] + dy * half)

    fig.add_trace(
        go.Scattergeo(
            lon=[tail[0], tip[0]],
            lat=[tail[1], tip[1]],
            mode="lines",
            line=dict(color=color, width=width_px),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Ponta (chevron): dois segmentos saindo da ponta para trás, simétricos.
    head_len = min(ARROW_HEAD_MAX, max(ARROW_HEAD_MIN, length_deg * ARROW_HEAD_FRAC))
    alpha = math.radians(ARROW_HEAD_ANGLE)
    cos_a = math.cos(alpha)
    sin_a = math.sin(alpha)

    bx, by = -dx, -dy  # vetor unitário "para trás" (da ponta para a cauda)
    b1 = (
        tip[0] + (bx * cos_a - by * sin_a) * head_len,
        tip[1] + (bx * sin_a + by * cos_a) * head_len,
    )
    b2 = (
        tip[0] + (bx * cos_a + by * sin_a) * head_len,
        tip[1] + (-bx * sin_a + by * cos_a) * head_len,
    )

    fig.add_trace(
        go.Scattergeo(
            lon=[b1[0], tip[0], b2[0]],
            lat=[b1[1], tip[1], b2[1]],
            mode="lines",
            line=dict(color=color, width=width_px),
            hoverinfo="skip",
            showlegend=False,
        )
    )


def _ordered_codes(geojson: dict) -> list[str]:
    """Ordem dos CD_UF na FeatureCollection (para alinhar z/customdata)."""
    return [feat["properties"]["CD_UF"] for feat in geojson["features"]]


def build_sector_figure(
    sector_id: str,
    res: dict,
    mapdata: dict,
    flow_data: dict,
    *,
    show_colorbar: bool = True,
    show_title: bool = True,
) -> go.Figure:
    """Constrói a figura (choropleth + setas de fluxo) de um único setor."""
    geojson = mapdata["geojson"]

    rho_bar = res["rho_bar"]
    sector_name = SECTOR_NAMES[sector_id]

    codes = _ordered_codes(geojson)
    code_to_name = {
        feat["properties"]["CD_UF"]: feat["properties"]["NM_UF"]
        for feat in geojson["features"]
    }

    median = _median_potencial(res["potencial"])
    saldo = flow_data["saldo"][sector_id]

    z: list[float] = []
    customdata: list[list] = []
    for code in codes:
        name = code_to_name[code]
        pot = res["potencial"].get(name, 0.0)
        sal = saldo.get(name, 0.0)
        is_dark = pot >= median

        z.append(pot)
        customdata.append([
            name,
            sector_name,
            RHO[sector_id],
            rho_bar,
            sal,
            "excedente de trabalhadores" if sal >= 0 else "déficit de trabalhadores",
            res["subutilizacao"].get(name, 0.0),
            res["informais"].get(name, 0.0),
            res["potencial_bruto"].get(name, 0.0),
            pot,
            res["w"][sector_id].get(name, 0.0),
            _state_interpretation(sal, is_dark),
        ])

    choropleth = go.Choropleth(
        geojson=geojson,
        locations=codes,
        z=z,
        featureidkey="properties.CD_UF",
        colorscale=[[0.0, BACKGROUND_LOW], [1.0, BACKGROUND_HIGH]],
        zmin=0.0,
        zmax=1.0,
        marker_line_color=STATE_BORDER,
        marker_line_width=0.5,
        customdata=customdata,
        hoverinfo="none",
        hovertemplate=None,
        colorbar=(
            dict(
                title=(
                    "Potencial de realocação de<br>trabalhadores (subutilização<br>+ informais, share nacional)"
                ),
                tickformat=".1%",
                thickness=16,
                len=0.7,
                title_font=dict(color=COLORBAR_TEXT),
                tickfont=dict(color=COLORBAR_TEXT),
                outlinecolor=STATE_BORDER,
                outlinewidth=1,
            )
            if show_colorbar
            else None
        ),
        showscale=show_colorbar,
    )

    fig = go.Figure(choropleth)

    # Setas de fluxo nas fronteiras.
    sector_flows = flow_data["flows"][sector_id]
    sector_max = flow_data["sector_max"][sector_id]

    # Coleta as setas exibidas (acima do limiar) para normalizar a cor pelo
    # mínimo/máximo de magnitude do próprio mapa.
    shown: list[tuple[dict, float]] = []
    for b in sector_flows:
        # Compressão por raiz quadrada + normalização pelo máximo do setor,
        # para atenuar a cauda pesada (ex.: concentração extrativa no RJ).
        mag_norm = math.sqrt(b["mag"] / sector_max)
        if mag_norm < FLOW_LIMIAR:
            continue
        shown.append((b, mag_norm))

    mags = [m for _, m in shown]
    mag_min = min(mags) if mags else 0.0
    mag_max = max(mags) if mags else 1.0

    for b, mag_norm in shown:
        if mag_max > mag_min:
            t = (mag_norm - mag_min) / (mag_max - mag_min)
        else:
            t = 1.0  # sem contraste (ex.: uma única seta): tom máximo
        color = _lerp_color(ATTRACTION_COLOR, REPULSION_COLOR, t)

        # Direção: do superávit ao déficit. `dir` aponta de cd_a -> cd_b.
        sign = 1.0 if b["flux"] >= 0 else -1.0
        dir_unit = (b["dir"][0] * sign, b["dir"][1] * sign)

        _add_flow_arrow(fig, b["mid"], dir_unit, mag_norm, color)

    minx, miny, maxx, maxy = mapdata["gdf"].total_bounds

    fig.update_layout(
        margin=dict(l=0, r=0, t=40 if show_title else 0, b=0),
        geo=dict(
            lonaxis=dict(range=[minx - GEO_MARGIN, maxx + GEO_MARGIN]),
            lataxis=dict(range=[miny - GEO_MARGIN, maxy + GEO_MARGIN]),
            visible=True,
            bgcolor=MAP_BG,
            showland=True,
            landcolor=LAND_COLOR,
            showocean=True,
            oceancolor=OCEAN_COLOR,
            showlakes=True,
            lakecolor=LAKE_COLOR,
            showcountries=False,
            showcoastlines=False,
            showframe=False,
            projection=dict(type="equirectangular"),
        ),
        paper_bgcolor=MAP_BG,
        plot_bgcolor=MAP_BG,
        modebar=dict(
            bgcolor="rgba(5,10,6,0.55)",
            color=COLORBAR_TEXT,
            activecolor=BACKGROUND_HIGH,
        ),
    )

    if show_title:
        fig.update_layout(
            title=dict(
                text=f"{sector_id} — {sector_name}",
                x=0.01,
                xanchor="left",
                font=dict(size=16, color=COLORBAR_TEXT),
            )
        )

    return fig
