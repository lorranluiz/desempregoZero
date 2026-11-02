"""Carregamento e normalização dos dados de entrada.

Este módulo concentra:
  * RHO (parâmetros setoriais, ILAESE 2024) e o mapeamento aba->setor do tab06;
  * a localização dos arquivos .xls/.xlsx (raiz do projeto ou pasta `tabelas/`);
  * a extração do VAB setorial (coluna 2022) por UF;
  * a extração da subutilização da força de trabalho e dos informais por UF.

Toda a normalização de nomes de UF é feita via `unidecode` + strip, de modo
que "Mato Grosso " (com espaço extra no tab06) e "Mato Grosso" casem
corretamente, assim como os acentos ("Rondônia" -> "Rondonia").
"""

from __future__ import annotations

import glob
import logging
import os
import re

import pandas as pd
from unidecode import unidecode

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parâmetros setoriais (ILAESE, Anuário 2025/26, Tabela II-quinquies, ρᵢ 2024)
# ---------------------------------------------------------------------------
RHO = {
    "01": 1.616, "02": 1.768, "03": 1.603, "04": 1.415,
    "05": 1.017, "06": 1.440, "07": 1.340, "08": 1.231,
    "09": 1.194, "10": 1.211, "11": 1.203, "12": 1.460,
}

# Nome curto de cada setor (usado no dropdown e no painel lateral).
SECTOR_NAMES = {
    "01": "Agropecuária",
    "02": "Indústrias extrativas",
    "03": "Indústrias de transformação",
    "04": "Eletricidade e gás, água, esgoto, resíduos",
    "05": "Construção",
    "06": "Comércio e reparação",
    "07": "Transporte, armazenagem e correio",
    "08": "Informação e comunicação",
    "09": "Atividades financeiras e seguros",
    "10": "Atividades imobiliárias",
    "11": "Outros serviços",
    "12": "Administração, defesa, educação e saúde públicas",
}

# ---------------------------------------------------------------------------
# Mapeamento aba (tab06) -> setor MIP.
#
# Atenção: as duas últimas abas estão "trocadas" em relação ao número da aba:
#   * aba Tabela6.12  -> setor 12 (Administração, defesa, educação e saúde)
#   * aba Tabela6.13  -> setor 11 (Outros serviços)
# Isso segue a ordem padrão MIP (Administração pública é o setor 12) e é
# consistente com o dicionário RHO acima (setor 12 = 1.460 > rho_bar).
# ---------------------------------------------------------------------------
ABA_NUM_TO_SECTOR = {
    2: "01", 3: "02", 4: "03", 5: "04", 6: "05", 7: "06",
    8: "07", 9: "08", 10: "09", 11: "10", 12: "12", 13: "11",
}

# 27 Unidades da Federação (nome canônico, com acentos).
UF_NAMES = [
    "Rondônia", "Acre", "Amazonas", "Roraima", "Pará", "Amapá", "Tocantins",
    "Maranhão", "Piauí", "Ceará", "Rio Grande do Norte", "Paraíba",
    "Pernambuco", "Alagoas", "Sergipe", "Bahia",
    "Minas Gerais", "Espírito Santo", "Rio de Janeiro", "São Paulo",
    "Paraná", "Santa Catarina", "Rio Grande do Sul",
    "Mato Grosso do Sul", "Mato Grosso", "Goiás", "Distrito Federal",
]

# Código IBGE (CD_UF) de cada UF, usado como chave canônica no shapefile.
UF_CODES = {
    "Rondônia": "11", "Acre": "12", "Amazonas": "13", "Roraima": "14",
    "Pará": "15", "Amapá": "16", "Tocantins": "17",
    "Maranhão": "21", "Piauí": "22", "Ceará": "23",
    "Rio Grande do Norte": "24", "Paraíba": "25", "Pernambuco": "26",
    "Alagoas": "27", "Sergipe": "28", "Bahia": "29",
    "Minas Gerais": "31", "Espírito Santo": "32", "Rio de Janeiro": "33",
    "São Paulo": "35",
    "Paraná": "41", "Santa Catarina": "42", "Rio Grande do Sul": "43",
    "Mato Grosso do Sul": "50", "Mato Grosso": "51", "Goiás": "52",
    "Distrito Federal": "53",
}

# Sigla de cada UF (apenas para exibição/tooltip).
UF_SIGLAS = {
    "Rondônia": "RO", "Acre": "AC", "Amazonas": "AM", "Roraima": "RR",
    "Pará": "PA", "Amapá": "AP", "Tocantins": "TO",
    "Maranhão": "MA", "Piauí": "PI", "Ceará": "CE",
    "Rio Grande do Norte": "RN", "Paraíba": "PB", "Pernambuco": "PE",
    "Alagoas": "AL", "Sergipe": "SE", "Bahia": "BA",
    "Minas Gerais": "MG", "Espírito Santo": "ES", "Rio de Janeiro": "RJ",
    "São Paulo": "SP",
    "Paraná": "PR", "Santa Catarina": "SC", "Rio Grande do Sul": "RS",
    "Mato Grosso do Sul": "MS", "Mato Grosso": "MT", "Goiás": "GO",
    "Distrito Federal": "DF",
}

# URL corrigida do shapefile (a URL original do enunciado aponta para um
# caminho que não existe mais; ver README).
SHAPEFILE_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_municipais/municipio_2022/"
    "Brasil/BR/BR_UF_2022.zip"
)


def normalize_name(name: object) -> str:
    """Normaliza um nome de UF: unidecode + strip (mantém maiúsculas/minúsculas).

    "Rondônia" -> "Rondonia"; "Mato Grosso " -> "Mato Grosso".
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    return unidecode(str(name)).strip()


def _year_of(value: object) -> int | None:
    """Converte uma célula de cabeçalho de ano ("2010", 2011.0) em int.

    Retorna None se a célula não representar um ano válido.
    """
    s = str(value).strip()
    s = s.split(".")[0]  # remove sufixo ".0" de floats
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _canonical(uf_name: str) -> str:
    """Retorna o nome canônico (com acentos) de uma UF a partir de um nome
    normalizado, ou None se não for uma das 27 UFs."""
    normalized = normalize_name(uf_name)
    for canon in UF_NAMES:
        if normalize_name(canon) == normalized:
            return canon
    return None


def _find_input(pattern: str, label: str) -> str:
    """Procura um arquivo de entrada (por glob) na raiz e na pasta `tabelas/`."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, pattern), os.path.join(here, "tabelas", pattern)]
    for cand in candidates:
        matches = sorted(glob.glob(cand))
        if matches:
            log.info("Encontrado %s: %s", label, matches[0])
            return matches[0]
    raise FileNotFoundError(
        f"Arquivo de dados '{label}' não encontrado (padrão '{pattern}'). "
        "Procurei na raiz do projeto e em 'tabelas/'."
    )


# ---------------------------------------------------------------------------
# Extração do VAB setorial (tab06)
# ---------------------------------------------------------------------------
def load_vab() -> dict[str, dict[str, float]]:
    """Extrai o VAB setorial (coluna 2022) por UF.

    Retorna um dicionário da forma:
        { setor_id: { uf_canonica: share } }
    onde `share` já está dividido por 100 (participação no VAB nacional do
    setor, em fração de 1). Valores vazios/NaN são tratados como 0.
    """
    path = _find_input("*tab06*.xls", "tab06 (VAB setorial)")

    # xlrd lê o formato .xls (openpyxl não suporta .xls).
    sheets = pd.read_excel(path, sheet_name=None, engine="xlrd")

    vab: dict[str, dict[str, float]] = {sid: {} for sid in SECTOR_NAMES}

    for sheet_name, df in sheets.items():
        # Determina o número da aba ("Tabela6.2" -> 2).
        m = re.search(r"6\.(\d+)", normalize_name(sheet_name))
        if not m:
            continue
        aba_num = int(m.group(1))
        sector_id = ABA_NUM_TO_SECTOR.get(aba_num)
        if sector_id is None:
            # Aba "6.1" (Total) e "Sumário" são ignoradas.
            continue

        # Localiza a linha de cabeçalho dos anos (a que contém "2010").
        header_row = None
        for idx, row in df.iterrows():
            if any(_year_of(row[col]) == 2010 for col in df.columns):
                header_row = idx
                break

        if header_row is None:
            log.warning("Aba %s: cabeçalho de anos não encontrado.", sheet_name)
            continue

        # Localiza a coluna "2022" na linha de cabeçalho.
        year_col = None
        for col in df.columns:
            if _year_of(df.loc[header_row, col]) == 2022:
                year_col = col
                break

        if year_col is None:
            log.warning("Aba %s: coluna 2022 não encontrada.", sheet_name)
            continue

        # Linhas de dados: coluna 0 = UF, coluna `year_col` = valor 2022.
        for _, row in df.iloc[header_row + 1:].iterrows():
            uf = _canonical(row.iloc[0])
            if uf is None:
                continue
            raw = row[year_col]
            value = 0.0
            if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                try:
                    value = float(raw) / 100.0
                except (TypeError, ValueError):
                    value = 0.0
            vab[sector_id][uf] = value

    log.info("VAB carregado: %d setores x %d UFs.", len(vab), len(UF_NAMES))
    return vab


# ---------------------------------------------------------------------------
# Extração da subutilização e dos informais (tabela4666 / tabela8517)
# ---------------------------------------------------------------------------
def _load_uf_value_xlsx(pattern: str, label: str) -> dict[str, float]:
    """Lê um xlsx de duas colunas (col A = UF, col B = valor em mil pessoas).

    Retorna { uf_canonica: valor_em_pessoas } (milhares * 1000).
    """
    path = _find_input(pattern, label)
    df = pd.read_excel(path, header=None, engine="openpyxl")

    out: dict[str, float] = {}
    for _, row in df.iterrows():
        uf = _canonical(row.iloc[0])
        if uf is None:
            continue
        raw = row.iloc[1]
        try:
            value = float(str(raw).strip().replace(",", "."))
        except (TypeError, ValueError):
            value = 0.0
        out[uf] = value * 1000.0  # mil pessoas -> pessoas

    log.info("%s carregado: %d UFs.", label, len(out))
    return out


def load_subutilizacao() -> dict[str, float]:
    """Subutilização da força de trabalho por UF (milhares -> pessoas)."""
    return _load_uf_value_xlsx("*4666*.xlsx", "tabela4666 (subutilização)")


def load_informais() -> dict[str, float]:
    """Trabalhadores informais por UF (milhares -> pessoas)."""
    return _load_uf_value_xlsx("*8517*.xlsx", "tabela8517 (informais)")
