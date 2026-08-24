import numpy as np
from collections import defaultdict

from ..config import CONFIG, FRACOES_DESCARGA

# Limiar de SOC crítico — em porcentagem (0-100), vindo da config do pacote.
_SOC_MIN_PCT = CONFIG["soc_min_pct"]

# Equipamentos rastreados nos info dicts do env (campo por máquina).
_EQUIPAMENTOS = {
    "pivo":     "pivo_kw_consumido",
    "captacao": "captacao_kw_consumido",
    "secador":  "secador_kw_consumido",
    "sede":     "sede_kw_consumido",
    "silo":     "silo_kw_consumido",
}


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

    def get_battery_dispatch_stats(self, agente: str = "ql_eval") -> dict:
        """Resume carga, descarga e bloqueios da bateria por período tarifário."""
        passos = self.passos.get(agente, [])
        if not passos:
            return {"aviso": f"Nenhum passo registrado para '{agente}'"}

        def soma(campo: str, em_pico: bool) -> float:
            return float(sum(
                p.get(campo, 0.0) for p in passos
                if bool(p.get("em_pico_tarifa", False)) is em_pico
            ))

        bloqueios = {motivo: sum(
            1 for p in passos
            if p.get("motivo_descarga_bloqueada") == motivo
        ) for motivo in ("sem_deficit", "soc_minimo", "throughput_esgotado")}
        pedidos_descarga = sum(1 for p in passos if p.get("a_arm") in FRACOES_DESCARGA)
        pedidos_por_nivel = {
            acao: sum(1 for p in passos if p.get("a_arm") == acao)
            for acao in FRACOES_DESCARGA
        }
        descargas_efetivas = sum(1 for p in passos if p.get("bat_descarga", 0.0) > 0.0)
        descarga_pico = soma("bat_descarga", True)
        descarga_fora_pico = soma("bat_descarga", False)
        descarga_total = descarga_pico + descarga_fora_pico
        carga_solar = float(sum(p.get("carga_solar_ac", 0.0) for p in passos))
        carga_rede = float(sum(p.get("carga_rede_ac", 0.0) for p in passos))
        custo_carga_rede = float(sum(
            p.get("carga_rede_ac", 0.0) * p.get("tarifa", 0.0)
            for p in passos
        ))
        bloqueios_carga_rede = {
            motivo: sum(1 for p in passos if p.get("bloqueio_carga_rede") == motivo)
            for motivo in ("tarifa_alta", "soc_maximo", "throughput_esgotado",
                           "sem_energia_disponivel")
        }
        n_dias = max(1, len(self.episodios.get(agente, [])) or len(passos) // 24)

        def soc_medio_hora(hora: int) -> float | None:
            valores = [p["soc"] for p in passos if p.get("hora") == hora]
            return round(float(np.mean(valores)), 4) if valores else None

        return {
            "pedidos_descarga": pedidos_descarga,
            "pedidos_por_nivel": pedidos_por_nivel,
            "descargas_efetivas": descargas_efetivas,
            "bloqueios_descarga": bloqueios,
            "carga_pico_kwh": soma("bat_carga", True),
            "carga_fora_pico_kwh": soma("bat_carga", False),
            "carga_solar_ac_kwh": round(carga_solar, 4),
            "carga_rede_ac_kwh": round(carga_rede, 4),
            "custo_carga_rede_rs": round(custo_carga_rede, 4),
            "bloqueios_carga_rede": bloqueios_carga_rede,
            "descarga_pico_kwh": descarga_pico,
            "descarga_fora_pico_kwh": descarga_fora_pico,
            "pct_descarga_no_pico": round(descarga_pico / descarga_total * 100, 2)
                                    if descarga_total > 0 else 0.0,
            "taxa_descarga_efetiva_pct": round(descargas_efetivas / pedidos_descarga * 100, 2)
                                           if pedidos_descarga > 0 else 0.0,
            "descarga_pico_media_dia_kwh": round(descarga_pico / n_dias, 4),
            "soc_medio_apos_18h_pct": soc_medio_hora(18),
            "soc_medio_apos_20h_pct": soc_medio_hora(20),
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
    # Equipamentos: uso hora-a-hora e KPIs estilo BI                      #
    # ------------------------------------------------------------------ #

    def get_equipment_hourly(self, agente: str = "iql_eval") -> dict:
        """Uso médio por hora-do-dia de cada equipamento (kW), agregando dias.

        Inclui também bateria (carga/descarga), rede e geração médias, para
        montar o painel de uso hora-a-hora dos equipamentos no dashboard.
        """
        passos = self.passos.get(agente, [])
        if not passos:
            return {"aviso": f"Nenhum passo registrado para '{agente}'"}

        por_hora: dict[int, list[dict]] = defaultdict(list)
        for p in passos:
            por_hora[int(p.get("hora", 0))].append(p)

        def media(lista, campo):
            return float(np.mean([p.get(campo, 0.0) for p in lista])) if lista else 0.0

        resultado = {}
        for h in sorted(por_hora):
            lst = por_hora[h]
            resultado[h] = {
                **{nome: round(media(lst, campo), 4)
                   for nome, campo in _EQUIPAMENTOS.items()},
                "bat_carga":    round(media(lst, "bat_carga"), 4),
                "bat_descarga": round(media(lst, "bat_descarga"), 4),
                "rede_kwh":     round(media(lst, "rede_kwh"), 4),
                "geracao_kw":   round(media(lst, "geracao_kw"), 4),
                "n_observacoes": len(lst),
            }
        return resultado

    def get_equipment_stats(self, agente: str = "iql_eval") -> dict:
        """KPIs por equipamento (lógica de BI): energia, horas ligada, pico, custo.

        custo_energia_rs = Σ (kWh × tarifa da hora) — custo bruto da energia
        consumida pelo equipamento na tarifa vigente, independente da fonte.
        """
        passos = self.passos.get(agente, [])
        if not passos:
            return {"aviso": f"Nenhum passo registrado para '{agente}'"}

        n_dias = max(1, len(self.episodios.get(agente, [])) or len(passos) // 24)

        equipamentos = {}
        for nome, campo in _EQUIPAMENTOS.items():
            kwh_total = kwh_pico = custo = 0.0
            horas_ligada = 0
            for p in passos:
                kw = float(p.get(campo, 0.0))
                if kw <= 0.0:
                    continue
                kwh_total += kw
                horas_ligada += 1
                custo += kw * float(p.get("tarifa", 0.0))
                if p.get("em_pico_tarifa", False):
                    kwh_pico += kw
            equipamentos[nome] = {
                "kwh_total": round(kwh_total, 4),
                "kwh_medio_dia": round(kwh_total / n_dias, 4),
                "horas_ligada_total": horas_ligada,
                "horas_ligada_media_dia": round(horas_ligada / n_dias, 2),
                "kwh_em_pico": round(kwh_pico, 4),
                "pct_kwh_em_pico": round(kwh_pico / kwh_total * 100, 2) if kwh_total > 0 else 0.0,
                "custo_energia_rs": round(custo, 4),
            }

        consumo_total = sum(e["kwh_total"] for e in equipamentos.values())
        for e in equipamentos.values():
            e["pct_do_consumo_total"] = (
                round(e["kwh_total"] / consumo_total * 100, 2) if consumo_total > 0 else 0.0
            )

        return {
            "n_dias": n_dias,
            "consumo_total_kwh": round(consumo_total, 4),
            "equipamentos": equipamentos,
        }

    # ------------------------------------------------------------------ #
    # Snapshot completo de um episódio                                    #
    # ------------------------------------------------------------------ #

    def get_trace_ultimo_episodio(self, agente: str) -> list[dict]:
        """Retorna as 24 entradas de info do último episódio registrado."""
        passos = self.passos.get(agente, [])
        return passos[-24:] if len(passos) >= 24 else passos
