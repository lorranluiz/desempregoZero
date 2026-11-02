"""Shapefile do Brasil por UF: download, carga, geometria e adjacência.

Responsabilidades:
  * baixar/descompactar o shapefile na primeira execução (data/BR_UF_2022/);
  * carregar com geopandas (engine `pyogrio`, que tem wheel compatível com
    Python 3.11+ -- o `fiona` não tem wheel para Python 3.14);
  * normalizar a coluna NM_UF para o nome canônico usado em `data.py`;
  * calcular o centroide de cada UF;
  * calcular a **adjacência** entre UFs (fronteiras compartilhadas) e, para
    cada fronteira, o ponto médio e o vetor direção que atravessa a borda.

A adjacência é calculada sobre a geometria **completa** (antes da
simplificação), pois a simplificação independente de cada polígono destrói a
coincidência das bordas compartilhadas.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import urllib.request
import zipfile

import geopandas as gpd

from data import SHAPEFILE_URL, UF_CODES, UF_NAMES, normalize_name

log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SHP_DIR = os.path.join(DATA_DIR, "BR_UF_2022")
SHP_PATH = os.path.join(SHP_DIR, "BR_UF_2022.shp")

# Tolerância de simplificação da geometria (em graus, ~2,2 km). A malha
# original tem ~1,1 milhão de pontos; a simplificação reduz para ~11 mil
# (JSON de 40 MB -> 0,4 MB), acelerando a inicialização e a renderização sem
# perda perceptível de forma na escala nacional.
SIMPLIFY_TOLERANCE = 0.02

# Comprimento mínimo (em graus) da borda compartilhada para considerar dois
# estados como vizinhos. Descarta "toques por ponto" (ex.: quinas).
BORDER_MIN_LENGTH = 0.02


def _download_shapefile() -> None:
    """Baixa e descompacta o shapefile em data/BR_UF_2022/ (se necessário)."""
    if os.path.exists(SHP_PATH):
        log.info("Shapefile já presente em %s", SHP_DIR)
        return

    os.makedirs(SHP_DIR, exist_ok=True)
    zip_path = os.path.join(SHP_DIR, "BR_UF_2022.zip")

    log.info("Baixando shapefile de %s ...", SHAPEFILE_URL)
    try:
        with urllib.request.urlopen(SHAPEFILE_URL, timeout=120) as resp:
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(resp, f)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Falha ao baixar o shapefile do IBGE. Veja o README.md para "
            "instruções de download manual (fallback: "
            "https://github.com/kelvins/Municipios-Brasileiros). Erro: "
            f"{exc}"
        ) from exc

    log.info("Descompactando shapefile em %s ...", SHP_DIR)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(SHP_DIR)
    log.info("Shapefile pronto.")


def _shared_border(geom_a, geom_b):
    """Retorna (comprimento, ponto_médio) da fronteira compartilhada entre
    dois polígonos, ou (0.0, None) se não forem adjacentes.

    Usa `boundary_a.intersection(geom_b)` (linha ∩ polígono), que é mais
    robusto a pequenas divergências de vértices entre as malhas dos estados
    do que `boundary_a.intersection(boundary_b)`.
    """
    inter = geom_a.boundary.intersection(geom_b)
    if inter.is_empty:
        return 0.0, None
    if inter.geom_type == "MultiLineString":
        parts = list(inter.geoms)
    elif inter.geom_type == "LineString":
        parts = [inter]
    else:
        return 0.0, None

    length = sum(p.length for p in parts)
    longest = max(parts, key=lambda p: p.length)
    mid = longest.interpolate(0.5, normalized=True)
    return length, (mid.x, mid.y)


def _compute_borders(gdf, centroids: dict[str, tuple[float, float]]) -> list[dict]:
    """Calcula a lista de fronteiras entre UFs adjacentes.

    Usa um join espacial (sjoin) para gerar candidatos e, para cada par,
    calcula a fronteira compartilhada. Retorna uma lista de dicionários:
        { "cd_a": cd, "cd_b": cd, "mid": (lon, lat), "dir": (dlon, dlat) }
    onde `cd_a` < `cd_b` (ordem lexicográfica) e `dir` é o vetor unitário
    apontando do centroide de `cd_a` para o centroide de `cd_b`.
    """
    # Candidatos a vizinhos (intersecção de geometrias), via índice espacial.
    joined = gpd.sjoin(gdf, gdf, predicate="intersects")
    joined = joined[joined["CD_UF_left"] != joined["CD_UF_right"]]
    candidates = sorted(set(
        tuple(sorted((a, b)))
        for a, b in zip(joined["CD_UF_left"], joined["CD_UF_right"])
    ))

    geom_by_code = {row["CD_UF"]: row.geometry for _, row in gdf.iterrows()}

    borders: list[dict] = []
    for cd_a, cd_b in candidates:
        length, mid = _shared_border(geom_by_code[cd_a], geom_by_code[cd_b])
        if length < BORDER_MIN_LENGTH or mid is None:
            continue

        ca = centroids[cd_a]
        cb = centroids[cd_b]
        dx = cb[0] - ca[0]
        dy = cb[1] - ca[1]
        norm = math.hypot(dx, dy)
        if norm == 0.0:
            continue
        borders.append({
            "cd_a": cd_a,
            "cd_b": cd_b,
            "mid": mid,
            "dir": (dx / norm, dy / norm),
        })

    log.info("Fronteiras entre UFs detectadas: %d", len(borders))
    return borders


def load_map() -> dict:
    """Carrega o shapefile e retorna geometria, centroides e fronteiras.

    Retorna um dicionário com:
      * gdf          -- GeoDataFrame (simplificado) das 27 UFs;
      * geojson      -- dict GeoJSON (FeatureCollection) das 27 UFs;
      * centroids    -- { cd_uf: (lon, lat) };
      * name_to_code -- { nome_canonico: cd_uf };
      * borders      -- lista de fronteiras (ver `_compute_borders`).
    """
    _download_shapefile()

    # `pyogrio` evita a dependência de `fiona` (sem wheel para Python 3.14).
    gdf = gpd.read_file(SHP_PATH, engine="pyogrio")

    # Garante coordenadas em WGS84 (lon/lat) para o Plotly.
    if gdf.crs is not None:
        gdf = gdf.to_crs(epsg=4326)

    # CD_UF como string de 2 dígitos ("11", "12", ...).
    gdf["CD_UF"] = gdf["CD_UF"].astype(str).str.zfill(2)

    # Centroides calculados sobre a geometria COMPLETA (mais precisos).
    centroids: dict[str, tuple[float, float]] = {}
    for _, row in gdf.iterrows():
        c = row.geometry.centroid
        centroids[row["CD_UF"]] = (c.x, c.y)

    # Adjacência sobre a geometria completa (antes de simplificar).
    borders = _compute_borders(gdf, centroids)

    # Simplifica a geometria para renderização (acelera o choropleth).
    gdf["geometry"] = gdf.geometry.simplify(
        tolerance=SIMPLIFY_TOLERANCE, preserve_topology=True
    )

    # Normaliza NM_UF para o nome canônico de data.py (remove acentos/fora).
    gdf["NM_UF"] = gdf["NM_UF"].map(lambda n: _canonical_name(n))

    name_to_code = {name: UF_CODES[name] for name in UF_NAMES}

    geojson = gdf.__geo_interface__

    log.info("Shapefile carregado: %d UFs, %d fronteiras.", len(gdf), len(borders))
    return {
        "gdf": gdf,
        "geojson": geojson,
        "centroids": centroids,
        "name_to_code": name_to_code,
        "borders": borders,
    }


def _canonical_name(raw: object) -> str:
    """Converte NM_UF do shapefile para o nome canônico de data.py."""
    normalized = normalize_name(raw)
    for canon in UF_NAMES:
        if normalize_name(canon) == normalized:
            return canon
    return str(raw)
