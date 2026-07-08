"""Métricas primárias de desempenho energético (seção 4.1 do Plano de Testes).

Este módulo é a **definição operacional única** das métricas do TCC — o
requisito P3 do plano ("definir formalmente as métricas") vira código aqui, de
modo que `evaluation`, `benchmark` e os testes de T3 consumam as MESMAS fórmulas
em vez de recalcularem cada um à sua maneira.

Todas as métricas são derivadas do histórico horário produzido pelo ambiente
(``FazendaEnergyEnv.historico``), sem estado adicional. Cada dia = 24 passos.

Escolhas de definição (P3 — explícitas para evitar confusão de construto):

  - **Autossuficiência** = demanda atendida por geração local (direta OU via
    bateria) ÷ demanda total. Usa as fontes já separadas pelo ambiente
    (`fonte_geracao_kwh`, `fonte_bateria_kwh`), então é uma razão exata.

  - **Autoconsumo** = geração local que ficou em casa ÷ geração local total =
    (atendimento direto da carga + energia que carregou a bateria) ÷ geração.
    A parcela que carregou a bateria é medida no lado da geração
    (`bat_carga / η_carga`), pois é essa energia que foi "retirada" da geração.
    NÃO confundir com "energia cortada": esta é CORTE DE CARGA (demanda não
    atendida, ver `energia_cortada`), não corte de geração. Autoconsumo também
    NÃO é autossuficiência: um dia nublado pode ter autoconsumo ~100 % (tudo que
    gerou foi usado) e autossuficiência baixa (gerou pouco perto da demanda).

  - **Ciclos equivalentes de bateria** = energia processada (carga + descarga)
    ÷ capacidade nominal, conforme a definição literal do plano (4.2).

  - **Gap de otimalidade** = (custo − custo_referência) ÷ custo_referência,
    com a referência sendo tipicamente o Heurístico (C1), conforme 4.1.

Ressalva de construto — ``energia_cortada`` (chave homônima): é a *produção
nominal não consumida* registrada pelo ambiente (`kwh_cortado`), que soma tanto
o corte por decisão do agente quanto a máquina fora do seu cronograma
(pivô/bomba desligados fora da janela). Portanto NÃO é apenas "demanda cortada
pelo controlador" — interpretar com cuidado ao comparar políticas. Separar as
duas causas exigiria instrumentar o ambiente (fora do escopo de T1–T3).
"""

from __future__ import annotations

from .config import CONFIG


def _safe_div(num: float, den: float) -> float:
    """Divisão protegida: retorna 0.0 quando o denominador é ~nulo."""
    return num / den if abs(den) > 1e-9 else 0.0


def metricas_dia(historico: list[dict], cfg: dict = CONFIG) -> dict:
    """Calcula as métricas primárias (4.1) e operacionais (4.2) de UM dia.

    Args:
        historico : lista de 24 dicts horários (``env.historico``).
        cfg       : config para constantes físicas (capacidade da bateria).

    Returns:
        dict com as métricas do dia. Percentuais em fração [0,1]; energia em
        kWh; potência em kW; custo em R$.
    """
    if not historico:
        return {}

    # ── Somatórios base (uma passada) ──────────────────────────────
    custo        = sum(h["custo_r"] for h in historico)
    geracao      = sum(h["geracao_kw"] for h in historico)
    consumo      = sum(h["consumo_kw"] for h in historico)
    importada    = sum(h["importacao"] for h in historico)
    exportada    = sum(h["exportacao"] for h in historico)
    cortada      = sum(h["kwh_cortado"] for h in historico)
    de_geracao   = sum(h["fonte_geracao_kwh"] for h in historico)
    de_bateria   = sum(h["fonte_bateria_kwh"] for h in historico)
    carga        = sum(h["bat_carga"] for h in historico)
    descarga     = sum(h["bat_descarga"] for h in historico)
    reward       = sum(h["reward"] for h in historico)
    viol_soc     = sum(1 for h in historico if h["soc"] < cfg["soc_min_pct"])

    cap   = cfg["bateria_cap_kwh"]
    eta_c = cfg["eficiencia_carga"]
    # Geração que carregou a bateria, medida no lado da geração (antes das perdas
    # de carga). É a parcela da geração "consumida" para armazenar.
    carga_da_geracao = carga / eta_c if eta_c > 0 else 0.0

    return {
        # Primárias (4.1)
        "custo_total_r"     : custo,
        "autossuficiencia"  : _safe_div(de_geracao + de_bateria, consumo),
        "autoconsumo"       : _safe_div(de_geracao + carga_da_geracao, geracao),
        "pico_demanda_kw"   : max((h["importacao"] for h in historico), default=0.0),
        "energia_importada" : importada,
        "energia_exportada" : exportada,
        "energia_cortada"   : cortada,
        # Operacionais (4.2)
        "ciclos_bateria"    : _safe_div(carga + descarga, cap),
        "violacoes_soc"     : viol_soc,
        # Auxiliares p/ auditoria
        "geracao_total_kwh" : geracao,
        "consumo_total_kwh" : consumo,
        "reward_total"      : reward,
    }


def resumo_metricas(historicos: list[list[dict]], cfg: dict = CONFIG) -> dict:
    """Média diária de cada métrica sobre um mês de simulações.

    Args:
        historicos : lista de históricos diários (cada um = 24 passos).

    Returns:
        dict {metrica: media_diaria}. Mesmas chaves de ``metricas_dia``.
    """
    if not historicos:
        return {}
    por_dia = [metricas_dia(h, cfg) for h in historicos]
    chaves = por_dia[0].keys()
    return {k: sum(d[k] for d in por_dia) / len(por_dia) for k in chaves}


def serie_por_dia(historicos: list[list[dict]], metrica: str,
                  cfg: dict = CONFIG) -> list[float]:
    """Vetor de uma métrica com um valor por dia — insumo do teste pareado (T3).

    Ex.: ``serie_por_dia(res_rl, "custo_total_r")`` devolve os 31 custos diários
    do braço RL, pareáveis contra o mesmo vetor de outro braço no Wilcoxon.
    """
    return [metricas_dia(h, cfg)[metrica] for h in historicos]


def gap_otimalidade(custo: float, custo_referencia: float) -> float:
    """Gap de otimalidade (4.1): (custo − ref) ÷ ref.

    Positivo = pior que a referência; negativo = melhor. A referência padrão do
    plano é o Heurístico (C1). Retorna 0.0 se a referência for ~nula.
    """
    return _safe_div(custo - custo_referencia, custo_referencia)
