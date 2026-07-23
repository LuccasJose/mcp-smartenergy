"""
Identificação de cenários a partir do dataset real (não-sintético).

`identificar_cenarios(dias)` retorna os índices dos 3 dias extremos do
dataset: nublado (menor geração), ensolarado (maior geração) e
alto_consumo (maior razão consumo/geração).

`classificar_dia(idx, dias)` devolve a etiqueta categórica de um dia
específico (NUBLADO / ENSOLARADO / ALTO CONSUMO / EQUILIBRADO) usando
quartis da distribuição do mês.
"""

from typing import Any
import numpy as np
import pandas as pd


def identificar_cenarios(dias: list[pd.DataFrame]) -> dict[str, int]:
    """Índices dos três dias extremos do dataset."""
    ger_dia  = [d["solar_kw"].sum() + d["eolico_kw"].sum() for d in dias]
    cons_dia = [(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).sum()
                for d in dias]
    razao    = [cons_dia[i] / max(ger_dia[i], 0.1) for i in range(len(dias))]
    return {
        "nublado":      int(np.argmin(ger_dia)),
        "ensolarado":   int(np.argmax(ger_dia)),
        "alto_consumo": int(np.argmax(razao)),
    }


def classificar_dia(idx: int, dias: list[pd.DataFrame]) -> str:
    """Categoria do dia idx usando quartis da geração e do consumo do mês."""
    ger_dia  = np.array([d["solar_kw"].sum() + d["eolico_kw"].sum() for d in dias])
    cons_dia = np.array([(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).sum()
                         for d in dias])
    g = ger_dia[idx]
    c = cons_dia[idx]
    q25_g, q75_g = np.quantile(ger_dia, [0.25, 0.75])
    q75_c        = np.quantile(cons_dia, 0.75)
    if g <= q25_g:
        return "NUBLADO"
    if c >= q75_c and g >= q75_g:
        return "ALTO CONSUMO"
    if g >= q75_g:
        return "ENSOLARADO"
    return "EQUILIBRADO"


def stats_por_cenario(historico_dias: list[dict],
                      metricas: list[str] = ("custo_medio", "rede_media", "reward_medio")
                      ) -> dict[str, dict[str, float]]:
    """Retorna médias das métricas para cada cenário."""
    acumulador: dict[str, dict[str, list]] = {}
    for dia in historico_dias:
        cenario = dia.get("cenario", "EQUILIBRADO")
        if cenario not in acumulador:
            acumulador[cenario] = {m: [] for m in metricas}
        for m in metricas:
            if m in dia:
                acumulador[cenario][m].append(dia[m])

    resultado: dict[str, dict[str, float]] = {}
    for cenario, vals in acumulador.items():
        resultado[cenario] = {}
        for m, lista in vals.items():
            resultado[cenario][m] = float(np.mean(lista)) if lista else 0.0
    return resultado
