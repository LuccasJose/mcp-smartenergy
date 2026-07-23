import numpy as np
from collections import defaultdict
from typing import Any

# Limiar de SOC crítico — a nova base usa porcentagem (0-100), não fração (0-1).
_SOC_MIN_PCT = 15.0


class MetricsTracker:
    """
    Rastreia todas as métricas de passos e episódios para cada agente.

    Métricas por passo: armazena dicts de info completos do ambiente.
    Métricas por episódio: reward total, custo total, epsilon, cenário.
    """

    def __init__(self):
        # passos: agente -> lista de info dicts (um por hora)
        self.passos: dict[str, list[dict]] = defaultdict(list)
        # episódios: agente -> lista de resumos
        self.episodios: dict[str, list[dict]] = defaultdict(list)

    def registrar_passo(self, info: dict, agente: str):
        self.passos[agente].append(info)

    def fechar_episodio(
        self,
        agente: str,
        reward_total: float,
        custo_total: float,
        epsilon: float,
        cenario: str = "EQUILIBRADO",
    ):
        self.episodios[agente].append(
            {
                "reward": reward_total,
                "custo": custo_total,
                "epsilon": epsilon,
                "cenario": cenario,
            }
        )

    def limpar(self, agente: str | None = None):
        if agente:
            self.passos[agente].clear()
            self.episodios[agente].clear()
        else:
            self.passos.clear()
            self.episodios.clear()

    # ------------------------------------------------------------------ #
    # Métricas de treino                                                   #
    # ------------------------------------------------------------------ #

    def get_training_metrics(self, agente: str = "ql_treino") -> dict:
        eps = self.episodios.get(agente, [])
        if not eps:
            return {"aviso": f"Nenhum episódio registrado para '{agente}'"}

        rewards = [e["reward"] for e in eps]
        custos = [e["custo"] for e in eps]
        epsilons = [e["epsilon"] for e in eps]

        janela = min(50, len(rewards))
        return {
            "n_episodios": len(rewards),
            "rewards_hist": rewards,
            "custos_hist": custos,
            "epsilons": epsilons,
            "reward_media_total": float(np.mean(rewards)),
            "reward_media_ultimos_50": float(np.mean(rewards[-janela:])),
            "custo_medio_total_rs": float(np.mean(custos)),
            "custo_medio_ultimos_50_rs": float(np.mean(custos[-janela:])),
            "epsilon_final": float(epsilons[-1]) if epsilons else 0.0,
        }

    # ------------------------------------------------------------------ #
    # Métricas de avaliação mensal                                         #
    # ------------------------------------------------------------------ #

    def get_eval_metrics(self, agente: str = "ql_eval") -> dict:
        eps = self.episodios.get(agente, [])
        if not eps:
            return {"aviso": f"Nenhum episódio registrado para '{agente}'"}

        passos_agente = self.passos.get(agente, [])

        # Estatísticas de episódio
        custos = [e["custo"] for e in eps]
        rewards = [e["reward"] for e in eps]

        # Estatísticas de passo
        rede_vals = [p["rede_kwh"] for p in passos_agente]
        soc_vals = [p["soc"] for p in passos_agente]
        viols_soc = sum(1 for s in soc_vals if s < _SOC_MIN_PCT)
        pcc_viols = sum(1 for p in passos_agente if p["pcc_violado"])
        kwh_cortado_total = sum(p["kwh_cortado"] for p in passos_agente)

        n_dias = len(eps)
        horas_total = len(passos_agente)
        horas_por_dia = horas_total / n_dias if n_dias > 0 else 24

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std_rs": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(rede_vals) * horas_por_dia) if rede_vals else 0.0,
            "violacoes_soc_total_h": viols_soc,
            "violacoes_soc_media_h_dia": float(viols_soc / n_dias) if n_dias > 0 else 0.0,
            "violacoes_pcc_total": pcc_viols,
            "kwh_cortado_total": float(kwh_cortado_total),
            "reward_medio_dia": float(np.mean(rewards)),
        }

    # ------------------------------------------------------------------ #
    # Métricas por cenário                                                 #
    # ------------------------------------------------------------------ #

    def get_stats_por_cenario(self, agente: str = "ql_eval") -> dict:
        eps = self.episodios.get(agente, [])
        cenarios: dict[str, dict[str, list]] = defaultdict(lambda: {"recompensas": [], "custos": []})

        for ep in eps:
            c = ep.get("cenario", "EQUILIBRADO")
            cenarios[c]["recompensas"].append(ep["reward"])
            cenarios[c]["custos"].append(ep["custo"])

        resultado = {}
        for cenario, vals in cenarios.items():
            resultado[cenario] = {
                "n_dias": len(vals["recompensas"]),
                "reward_medio": float(np.mean(vals["recompensas"])) if vals["recompensas"] else 0.0,
                "custo_medio_rs": float(np.mean(vals["custos"])) if vals["custos"] else 0.0,
            }
        return resultado

    # ------------------------------------------------------------------ #
    # Dashboard: dados para curva de aprendizado                          #
    # ------------------------------------------------------------------ #

    def get_learning_curve(self, agente: str = "ql_treino", janela: int = 20) -> dict:
        eps = self.episodios.get(agente, [])
        if not eps:
            return {}

        rewards = [e["reward"] for e in eps]
        custos = [e["custo"] for e in eps]
        epsilons = [e["epsilon"] for e in eps]

        def media_movel(serie, k):
            if len(serie) < k:
                return serie
            return [float(np.mean(serie[max(0, i - k):i + 1])) for i in range(len(serie))]

        return {
            "episodios": list(range(len(rewards))),
            "rewards": rewards,
            "rewards_ma": media_movel(rewards, janela),
            "custos": custos,
            "custos_ma": media_movel(custos, janela),
            "epsilons": epsilons,
        }

    # ------------------------------------------------------------------ #
    # Pico vs fora de pico por carga                                      #
    # ------------------------------------------------------------------ #

    def get_peak_offpeak_stats(self, agente: str = "ql_eval") -> dict:
        passos = self.passos.get(agente, [])
        pico = [p for p in passos if p.get("em_pico_tarifa", False)]
        fora = [p for p in passos if not p.get("em_pico_tarifa", False)]

        def soma(lista, campo):
            return float(sum(p.get(campo, 0.0) for p in lista))

        return {
            "pico": {
                "pivo_kwh": soma(pico, "pivo_kw_consumido"),
                "captacao_kwh": soma(pico, "captacao_kw_consumido"),
                "secador_kwh": soma(pico, "secador_kw_consumido"),
                "rede_kwh": soma(pico, "rede_kwh"),
                "custo_rs": soma(pico, "custo_r"),
                "n_horas": len(pico),
            },
            "fora_pico": {
                "pivo_kwh": soma(fora, "pivo_kw_consumido"),
                "captacao_kwh": soma(fora, "captacao_kw_consumido"),
                "secador_kwh": soma(fora, "secador_kw_consumido"),
                "rede_kwh": soma(fora, "rede_kwh"),
                "custo_rs": soma(fora, "custo_r"),
                "n_horas": len(fora),
            },
        }

    # ------------------------------------------------------------------ #
    # Violações por hora-do-dia                                            #
    # ------------------------------------------------------------------ #

    def get_hourly_violations(self, agente: str = "iql_eval") -> dict:
        """Agrega violações por hora-do-dia para diagnóstico do LLM-juiz.

        Retorna, para cada hora 0-23: total de violações SOC, PCC, teto excedido,
        custo médio e SOC médio.
        """
        passos = self.passos.get(agente, [])
        if not passos:
            return {"aviso": f"Nenhum passo registrado para '{agente}'"}

        por_hora: dict[int, dict] = {h: {"n": 0, "soc_vals": [], "custo": 0.0,
                                          "viol_soc": 0, "viol_pcc": 0,
                                          "teto_excedido": 0, "kwh_cortado": 0.0}
                                     for h in range(24)}
        for p in passos:
            h = int(p.get("hora", 0))
            d = por_hora[h]
            d["n"] += 1
            d["soc_vals"].append(p["soc"])
            d["custo"] += p.get("custo_r", 0.0)
            if p["soc"] < _SOC_MIN_PCT:
                d["viol_soc"] += 1
            if p.get("pcc_violado", False):
                d["viol_pcc"] += 1
            if p.get("teto_excedido", False):
                d["teto_excedido"] += 1
            d["kwh_cortado"] += p.get("kwh_cortado", 0.0)

        resultado = {}
        for h, d in por_hora.items():
            if d["n"] == 0:
                continue
            resultado[h] = {
                "n_observacoes": d["n"],
                "soc_medio": float(np.mean(d["soc_vals"])),
                "custo_total_rs": round(d["custo"], 4),
                "violacoes_soc": d["viol_soc"],
                "violacoes_pcc": d["viol_pcc"],
                "teto_excedido": d["teto_excedido"],
                "kwh_cortado_total": round(d["kwh_cortado"], 4),
            }
        return resultado

    # ------------------------------------------------------------------ #
    # Snapshot completo de um episódio                                    #
    # ------------------------------------------------------------------ #

    def get_trace_ultimo_episodio(self, agente: str) -> list[dict]:
        """Retorna as 24 entradas de info do último episódio registrado."""
        passos = self.passos.get(agente, [])
        return passos[-24:] if len(passos) >= 24 else passos
