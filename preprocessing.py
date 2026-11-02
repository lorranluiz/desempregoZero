"""Cálculo dos indicadores derivados (Passos 3 e 4 da metodologia).

Produz, a partir dos dados brutos carregados em `data.py`:
  * rho_bar          -- média dos 12 parâmetros setoriais (≈ 1.375);
  * w[i][r]          -- peso setorial (share do estado no VAB nacional do setor);
  * I[i][r]          -- intensidade bruta da seta;
  * tilde_I[i][r]    -- intensidade normalizada por máximo (por setor);
  * T[i][r]          -- intensidade normalizada globalmente (espessura);
  * direction[i]     -- +1 (atração) / -1 (repulsão);
  * subutilizacao[r], informais[r], potencial_bruto[r], potencial[r].

Todas as estruturas usam a UF canônica (nome com acentos, ex. "São Paulo")
e o id de setor como string "01".."12".
"""

from __future__ import annotations

import logging
import math

import numpy as np

from data import RHO, SECTOR_NAMES, UF_NAMES, load_informais, load_subutilizacao, load_vab

log = logging.getLogger(__name__)


def compute_all():
    """Calcula todos os indicadores e executa as validações do Passo 6."""
    vab = load_vab()
    subutilizacao = load_subutilizacao()
    informais = load_informais()

    sector_ids = sorted(SECTOR_NAMES.keys())

    # --- Passo 4: rho_bar -------------------------------------------------
    rho_bar = float(np.mean(list(RHO.values())))

    # --- Passo 1/4: pesos setoriais w[i][r] ------------------------------
    w: dict[str, dict[str, float]] = {}
    for sid in sector_ids:
        total = sum(vab[sid].get(uf, 0.0) for uf in UF_NAMES)
        if total == 0.0:
            w[sid] = {uf: 0.0 for uf in UF_NAMES}
        else:
            w[sid] = {uf: vab[sid].get(uf, 0.0) / total for uf in UF_NAMES}

    # --- Passo 4: intensidade bruta I, direção, normalizações ------------
    I: dict[str, dict[str, float]] = {}
    tilde_I: dict[str, dict[str, float]] = {}
    T: dict[str, dict[str, float]] = {}
    direction: dict[str, int] = {}

    global_max_I = 0.0
    for sid in sector_ids:
        direction[sid] = 1 if RHO[sid] > rho_bar else -1
        I[sid] = {
            uf: abs(RHO[sid] - rho_bar) * w[sid][uf] for uf in UF_NAMES
        }
        global_max_I = max(global_max_I, max(I[sid].values()))

    if global_max_I == 0.0:
        global_max_I = 1.0

    for sid in sector_ids:
        sector_max = max(I[sid].values()) if I[sid] else 0.0
        if sector_max == 0.0:
            sector_max = 1.0
        tilde_I[sid] = {uf: I[sid][uf] / sector_max for uf in UF_NAMES}
        T[sid] = {uf: I[sid][uf] / global_max_I for uf in UF_NAMES}

    # --- Passo 3: potencial de mobilidade (soma direta, sem fator) -------
    potencial_bruto = {
        uf: subutilizacao.get(uf, 0.0) + informais.get(uf, 0.0) for uf in UF_NAMES
    }
    soma_bruto = sum(potencial_bruto.values())
    potencial = {uf: potencial_bruto[uf] / soma_bruto for uf in UF_NAMES}

    result = {
        "vab": vab,
        "subutilizacao": subutilizacao,
        "informais": informais,
        "potencial_bruto": potencial_bruto,
        "potencial": potencial,
        "rho_bar": rho_bar,
        "w": w,
        "I": I,
        "tilde_I": tilde_I,
        "T": T,
        "direction": direction,
    }

    validate(result)
    return result


def validate(res: dict) -> None:
    """Executa as validações do Passo 6 e registra os resultados."""
    sector_ids = sorted(SECTOR_NAMES.keys())
    rho_bar = res["rho_bar"]
    w = res["w"]
    sub = res["subutilizacao"]
    inf_ = res["informais"]
    potencial_bruto = res["potencial_bruto"]
    potencial = res["potencial"]

    checks = []

    checks.append(("abs(rho_bar - 1.375) < 0.01", abs(rho_bar - 1.375) < 0.01))
    checks.append(("6 setores com rho > rho_bar", sum(1 for s in sector_ids if RHO[s] > rho_bar) == 6))
    checks.append(("6 setores com rho < rho_bar", sum(1 for s in sector_ids if RHO[s] < rho_bar) == 6))
    checks.append(("sum(subutilizacao) ~ 18.653.000", abs(sum(sub.values()) - 18_653_000) <= 0.01 * 18_653_000))
    checks.append(("sum(informais) ~ 39.306.000", abs(sum(inf_.values()) - 39_306_000) <= 0.01 * 39_306_000))
    checks.append(("sum(potencial_bruto) ~ 57.959.000", abs(sum(potencial_bruto.values()) - 57_959_000) <= 0.01 * 57_959_000))
    checks.append(("sum(potencial) == 1.0", abs(sum(potencial.values()) - 1.0) <= 0.001))

    all_ok = True
    for label, ok in checks:
        log.info("Validação %-38s %s", label, "OK" if ok else "FALHOU")
        if not ok:
            all_ok = False

    # w soma ~1 por setor
    for sid in sector_ids:
        s = sum(w[sid].values())
        ok = abs(s - 1.0) <= 0.01
        if not ok:
            all_ok = False
        log.info("Validação sum(w[%s]) ~ 1.0 (=%.4f) %s", sid, s, "OK" if ok else "FALHOU")

    if not all_ok:
        raise RuntimeError("Falha em uma ou mais validações (ver logs acima).")

    log.info("rho_bar = %.5f", rho_bar)
    log.info("Total subutilização  = %s", f"{sum(sub.values()):,.0f}")
    log.info("Total informais      = %s", f"{sum(inf_.values()):,.0f}")
    log.info("Total potencial bruto = %s", f"{sum(potencial_bruto.values()):,.0f}")
