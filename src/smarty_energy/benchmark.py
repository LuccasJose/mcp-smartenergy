"""
Benchmark: política de controle RL puro × LLM-via-MCP (análise de trade-offs).

Roda os mesmos 31 dias por vários "braços" (Sem Agente / Heurístico / RL /
LLM), no MESMO ambiente e com as MESMAS métricas (reusa ``evaluation``), e
caracteriza dois eixos:

  Eixo 1 — Qualidade da decisão : custo R$/dia, kWh da rede, violações, reward.
  Eixo 2 — Custo operacional MCP: latência, tokens, R$/mês de API, fallback.

Síntese: comparação pareada por dia (Wilcoxon signed-rank, sem dependência de
scipy) entre RL e LLM, e um ponto de trade-off (economia × custo de API) para o
gráfico de Pareto em visualization.py.

Uso típico (offline, sem custo de API — valida o harness):

    from smarty_energy.data_loader import carregar_dados
    from smarty_energy.benchmark import rodar_benchmark
    from smarty_energy.llm_policy import PoliticaLLM, decisor_heuristico_simulado
    dias, tarifa = carregar_dados()
    pol = PoliticaLLM(decisor_heuristico_simulado())
    res = rodar_benchmark(dias, tarifa, agentes_rl=AGENTES, politica_llm=pol)

Para o braço real, injete ``PoliticaLLM(criar_decisor_anthropic(...))``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime

from .config import CONFIG, OUTPUT_DIR
from .evaluation import (
    rodar_sem_agente, rodar_heuristico, rodar_rl, rodar_llm, resumo_mes,
)
from .metrics import serie_por_dia

BENCH_DIR = OUTPUT_DIR / "benchmarks"


# ──────────────────────────────────────────────────────────────
# Métricas por dia (para comparação pareada)
# ──────────────────────────────────────────────────────────────

def custos_por_dia(historicos: list[list[dict]]) -> list[float]:
    """Custo de energia (R$) de cada dia — vetor pareável entre braços."""
    return [sum(h["custo_r"] for h in hist) for hist in historicos]


def rede_por_dia(historicos: list[list[dict]]) -> list[float]:
    return [sum(h["rede_kwh"] for h in hist) for hist in historicos]


# ──────────────────────────────────────────────────────────────
# Wilcoxon signed-rank pareado (aprox. normal, sem scipy)
# ──────────────────────────────────────────────────────────────

def wilcoxon_pareado(a: list[float], b: list[float]) -> dict:
    """Teste de Wilcoxon signed-rank para amostras pareadas (a vs b).

    Implementa a aproximação normal com correção de continuidade e tratamento
    de empates por postos médios (método de Wilcoxon: descarta diferenças nulas).
    Adequado para n≈31 dias. Para n muito pequeno (<10) o p-valor normal é
    aproximado — reportar com ressalva.

    Returns:
        dict com W (estatística), z, p_valor (bicaudal), n_efetivo,
        e r (tamanho de efeito = |z|/sqrt(n)).
    """
    difs = [x - y for x, y in zip(a, b) if (x - y) != 0.0]
    n = len(difs)
    if n == 0:
        return {"W": 0.0, "z": 0.0, "p_valor": 1.0, "n_efetivo": 0, "r": 0.0}

    # Postos das magnitudes |dif| (postos médios em empates)
    ordenado = sorted(range(n), key=lambda i: abs(difs[i]))
    postos = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(difs[ordenado[j + 1]]) == abs(difs[ordenado[i]]):
            j += 1
        posto_medio = (i + 1 + j + 1) / 2.0  # postos 1-indexados
        for k in range(i, j + 1):
            postos[ordenado[k]] = posto_medio
        i = j + 1

    w_mais  = sum(p for p, d in zip(postos, difs) if d > 0)
    w_menos = sum(p for p, d in zip(postos, difs) if d < 0)
    W = min(w_mais, w_menos)

    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return {"W": W, "z": 0.0, "p_valor": 1.0, "n_efetivo": n, "r": 0.0}
    z = (W - mu + 0.5 * (1 if W < mu else -1)) / sigma  # correção de continuidade
    p = 2.0 * (1.0 - _phi(abs(z)))
    return {"W": W, "z": z, "p_valor": min(1.0, p), "n_efetivo": n,
            "r": abs(z) / math.sqrt(n)}


def _phi(x: float) -> float:
    """CDF da normal padrão via erf (stdlib)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def comparar_metrica_pareada(
    hist_a: list[list[dict]],
    hist_b: list[list[dict]],
    metrica: str = "custo_total_r",
    cfg: dict = CONFIG,
) -> dict:
    """Compara UMA métrica entre dois braços, pareada por dia (bloco T3).

    Aplica o Wilcoxon pareado sobre a série diária da métrica (ex.: RL vs C0 em
    ``custo_total_r``) e agrega médias e delta para reportar tamanho de efeito
    além do p-valor — como pede o plano ("não apenas p-valor").

    Args:
        hist_a, hist_b : históricos diários dos dois braços (mesmos dias, ordem).
        metrica        : chave de ``metrics.metricas_dia`` a comparar.

    Returns:
        dict com as chaves do Wilcoxon (W, z, p_valor, r, n_efetivo) mais
        ``media_a``, ``media_b`` e ``delta_medio`` (a − b). Delta < 0 significa
        que o braço A tem a métrica menor (melhor, para custo/rede).
    """
    a = serie_por_dia(hist_a, metrica, cfg)
    b = serie_por_dia(hist_b, metrica, cfg)
    res = wilcoxon_pareado(a, b)
    res["metrica"] = metrica
    res["media_a"] = sum(a) / len(a) if a else 0.0
    res["media_b"] = sum(b) / len(b) if b else 0.0
    res["delta_medio"] = res["media_a"] - res["media_b"]
    return res


# ──────────────────────────────────────────────────────────────
# Custo de API (Eixo 2) — preços parametrizados (NÃO hardcoded)
# ──────────────────────────────────────────────────────────────

@dataclass
class PrecoModelo:
    """Preço do modelo para estimar R$ de API.

    IMPORTANTE: preencher com a tabela de preços VIGENTE do modelo escolhido na
    data do experimento (ver claude-api / docs Anthropic). Os valores abaixo são
    PLACEHOLDERS e devem ser confirmados — registre a data do snapshot.
    """
    nome: str = "claude-haiku-4-5"
    usd_por_mtok_in: float = 0.0   # USD por 1M tokens de entrada — PREENCHER
    usd_por_mtok_out: float = 0.0  # USD por 1M tokens de saída   — PREENCHER
    usd_brl: float = 0.0           # câmbio USD→BRL                — PREENCHER
    snapshot: str = "PREENCHER (ex.: 2026-06-26)"


def custo_api_brl(resumo_op: dict, preco: PrecoModelo) -> dict:
    """Converte tokens consumidos em R$ (por mês simulado e por decisão)."""
    tin = resumo_op.get("tokens_in_total", 0)
    tout = resumo_op.get("tokens_out_total", 0)
    n = resumo_op.get("n_decisoes", 0) or 1
    usd = (tin / 1e6) * preco.usd_por_mtok_in + (tout / 1e6) * preco.usd_por_mtok_out
    brl = usd * preco.usd_brl
    return {
        "usd_total": usd, "brl_total": brl,
        "brl_por_decisao": brl / n,
        "brl_por_mes_31d": brl,  # n_decisoes ≈ 31×24 já é um mês
        "preco": preco.__dict__,
    }


# ──────────────────────────────────────────────────────────────
# Orquestração
# ──────────────────────────────────────────────────────────────

def rodar_benchmark(
    dias, tarifa, *,
    agentes_rl: dict,
    politica_llm,
    n_repeticoes: int = 1,
    preco: PrecoModelo | None = None,
    salvar: bool = True,
) -> dict:
    """Roda todos os braços nos 31 dias e monta o relatório de trade-off.

    Args:
        agentes_rl   : dict de AgenteQL já treinados (baseline principal).
        politica_llm : PoliticaLLM (decisor stub para validar offline, ou real).
        n_repeticoes : nº de execuções do braço LLM (estocástico → média ± dp).
        preco        : PrecoModelo para estimar R$ de API (placeholder se None).

    Returns:
        dict com métricas dos 4 braços, Wilcoxon RL×LLM e custo de API.
    """
    preco = preco or PrecoModelo()

    # -- Braços determinísticos (1 execução) --
    res_s = [rodar_sem_agente(d, tarifa) for d in dias]
    res_h = [rodar_heuristico(d, tarifa) for d in dias]
    res_r = [rodar_rl(d, tarifa, agentes_rl) for d in dias]

    # -- Braço LLM (n repetições, estocástico) --
    rep_resumos, rep_custos_dia, rep_op = [], [], []
    for _ in range(max(1, n_repeticoes)):
        politica_llm.reset_eventos()
        res_l = [rodar_llm(d, tarifa, politica_llm) for d in dias]
        rep_resumos.append(resumo_mes(res_l))
        rep_custos_dia.append(custos_por_dia(res_l))
        rep_op.append(politica_llm.resumo_operacional())

    # Média entre repetições (custo médio diário por dia, p/ Wilcoxon estável)
    custos_llm_dia = [
        sum(rep[i] for rep in rep_custos_dia) / len(rep_custos_dia)
        for i in range(len(dias))
    ]
    custos_rl_dia = custos_por_dia(res_r)

    resultado = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "n_dias": len(dias),
        "n_repeticoes": n_repeticoes,
        "eixo1_qualidade": {
            "sem_agente": _tupla_resumo(resumo_mes(res_s)),
            "heuristico": _tupla_resumo(resumo_mes(res_h)),
            "rl":         _tupla_resumo(resumo_mes(res_r)),
            "llm":        _media_resumos(rep_resumos),
        },
        "eixo2_operacional": _media_op(rep_op),
        "wilcoxon_custo_rl_vs_llm": wilcoxon_pareado(custos_rl_dia, custos_llm_dia),
        "custo_api": custo_api_brl(_media_op(rep_op), preco),
        "custos_por_dia": {"rl": custos_rl_dia, "llm": custos_llm_dia},
    }

    if salvar:
        resultado["run_dir"] = _salvar(resultado)
    return resultado


def _tupla_resumo(t: tuple[float, float, float, float]) -> dict:
    c, r, v, rw = t
    return {"custo_r": c, "rede_kwh": r, "violacoes_soc": v, "reward": rw}


def _media_resumos(resumos: list[tuple]) -> dict:
    """Média ± desvio das métricas do braço LLM entre repetições."""
    chaves = ["custo_r", "rede_kwh", "violacoes_soc", "reward"]
    cols = list(zip(*resumos))
    out = {}
    for k, col in zip(chaves, cols):
        m = sum(col) / len(col)
        dp = math.sqrt(sum((x - m) ** 2 for x in col) / len(col)) if len(col) > 1 else 0.0
        out[k] = m
        out[k + "_dp"] = dp
    return out


def _media_op(ops: list[dict]) -> dict:
    """Soma/média das métricas operacionais entre repetições."""
    if not ops or not ops[0]:
        return {}
    chaves = ops[0].keys()
    return {k: sum(o.get(k, 0) for o in ops) / len(ops) for k in chaves}


def _salvar(resultado: dict) -> str:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    rid = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destino = BENCH_DIR / rid
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "benchmark.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(destino)


def imprimir_relatorio(res: dict) -> None:
    """Imprime o relatório de trade-off em formato legível (terminal)."""
    q = res["eixo1_qualidade"]
    print(f"\n{'BENCHMARK — RL puro × LLM (média diária)':^72}")
    print("═" * 72)
    print(f"  {'Braço':<14} {'Custo R$':>10} {'Rede kWh':>10} {'Viol.':>7} {'Reward':>10}")
    print("  " + "─" * 66)
    for nome, k in [("Sem Agente", "sem_agente"), ("Heurístico", "heuristico"),
                    ("RL puro", "rl"), ("LLM", "llm")]:
        m = q[k]
        print(f"  {nome:<14} {m['custo_r']:>10.2f} {m['rede_kwh']:>10.2f} "
              f"{m['violacoes_soc']:>7.2f} {m['reward']:>10.2f}")
    print("═" * 72)
    w = res["wilcoxon_custo_rl_vs_llm"]
    print(f"  Wilcoxon custo RL×LLM: z={w['z']:.3f}  p={w['p_valor']:.4f}  "
          f"r={w['r']:.3f}  (n={w['n_efetivo']})")
    op = res["eixo2_operacional"]
    if op:
        print(f"  Latência mediana: {op.get('latencia_ms_mediana', 0):.0f} ms  "
              f"p95: {op.get('latencia_ms_p95', 0):.0f} ms  "
              f"fallback: {op.get('taxa_fallback', 0)*100:.1f}%")
        print(f"  Tokens in/out: {op.get('tokens_in_total', 0)}/"
              f"{op.get('tokens_out_total', 0)}")
    ca = res["custo_api"]
    print(f"  Custo API estimado: R${ca['brl_total']:.2f}/mês  "
          f"(R${ca['brl_por_decisao']:.4f}/decisão) — preço {ca['preco']['snapshot']}")
