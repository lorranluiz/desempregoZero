"""Exporta os 12 mapas (versão clara para impressão) como PNG.

Reutiliza a matemática de `preprocessing`/`mapping`/`figures`, apenas
substituindo a paleta neon por uma paleta clara adequada a papel.
"""

from __future__ import annotations

import os

import figures
import mapping
import preprocessing

# Paleta clara (impressão) — mesmos dados/setas, fundo branco.
figures.ATTRACTION_COLOR = "#1f5fb8"   # azul = menor fluxo
figures.REPULSION_COLOR = "#c81e1e"    # vermelho = maior fluxo
figures.BACKGROUND_LOW = "#f3f4ef"     # potencial baixo
figures.BACKGROUND_HIGH = "#0b6b3a"    # potencial alto (verde escuro)
figures.MAP_BG = "#ffffff"
figures.LAND_COLOR = "#f3f4ef"
figures.OCEAN_COLOR = "#ffffff"
figures.LAKE_COLOR = "#ffffff"
figures.STATE_BORDER = "#8f948f"
figures.COLORBAR_TEXT = "#222222"


def main() -> None:
    res = preprocessing.compute_all()
    mapdata = mapping.load_map()
    flow = figures.compute_flows(res, mapdata)

    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artigo", "figs")
    os.makedirs(outdir, exist_ok=True)

    for sid in figures.SECTOR_NAMES:
        fig = figures.build_sector_figure(
            sid, res, mapdata, flow, show_colorbar=True, show_title=True
        )
        path = os.path.join(outdir, f"setor_{sid}.png")
        fig.write_image(path, width=1400, height=1000, scale=2)
        print("exportado", sid, "->", path)


if __name__ == "__main__":
    main()
