from typing import Any


def identificar_cenarios(historico_dias: list[dict]) -> dict[str, list[int]]:
    """
    Classifica cada dia do histórico e retorna índices agrupados por cenário.
    Cada entrada em historico_dias deve ter 'solar_media' e 'consumo_medio'.
    """
    grupos: dict[str, list[int]] = {
        "NUBLADO": [],
        "ENSOLARADO": [],
        "ALTO CONSUMO": [],
        "EQUILIBRADO": [],
    }
    for i, dia in enumerate(historico_dias):
        cenario = dia.get("cenario", "EQUILIBRADO")
        grupos.setdefault(cenario, []).append(i)
    return grupos


def stats_por_cenario(
    historico_dias: list[dict],
    metricas: list[str] = ("custo_medio", "rede_media", "reward_medio", "violacoes_soc"),
) -> dict[str, dict[str, float]]:
    """
    Retorna médias das métricas para cada cenário.
    historico_dias: lista de dicts com pelo menos 'cenario' e as métricas solicitadas.
    """
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
            resultado[cenario][m] = float(sum(lista) / len(lista)) if lista else 0.0
    return resultado
