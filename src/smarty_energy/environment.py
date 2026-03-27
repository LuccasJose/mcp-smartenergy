"""
FazendaEnergyEnv — Ambiente de simulação energética da fazenda.

Estado discreto (chave Q-table): (bucket_hora, bucket_soc, bucket_solar, bucket_tarifa)
  bucket_hora  : hora // 6        -> 4 valores  (0-5h / 6-11h / 12-17h / 18-23h)
  bucket_soc   : soc // 20        -> 5 valores  (0-20 / 20-40 / … / 80-100 %)
  bucket_solar : low/med/high     -> 3 valores  (<5 kW / 5-15 / >15)
  bucket_tarifa: normal/pico      -> 2 valores
  Total: 4×5×3×2 = 120 estados

Ações por agente:
  Armazenamento : 0=carregar  1=manter  2=descarregar
  Consumo       : 0=nada  1=corta_pivo  2=corta_captacao  3=corta_ambos
  Gerente       : 0=conservador(20kW)  1=moderado(30kW)  2=liberal(40kW)
"""

import pandas as pd
import numpy as np

from .config import CONFIG, TETOS_KW


class FazendaEnergyEnv:

    def __init__(self, dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, cfg: dict = CONFIG):
        self.dados  = dados_dia.reset_index(drop=True)
        self.tarifa = tarifa_24h
        self.cfg    = cfg
        self.reset()

    def reset(self) -> dict:
        self.hora      = 0
        self.soc       = self.cfg["soc_inicial_pct"]
        self.historico = []
        return self._estado()

    def _estado(self) -> dict:
        r = self.dados.iloc[self.hora]
        return {
            "hora"     : self.hora,
            "soc"      : self.soc,
            "solar_kw" : float(r["solar_kw"]),
            "eolico_kw": float(r["eolico_kw"]),
            "tarifa"   : self.tarifa[self.hora],
        }

    def discretizar(self, est: dict) -> tuple:
        h = est["hora"] // 6
        s = min(int(est["soc"] / 20), 4)
        g = 0 if est["solar_kw"] < 5 else (1 if est["solar_kw"] < 15 else 2)
        t = 1 if est["tarifa"] > 0.9 else 0
        return (h, s, g, t)

    def step(self, a_arm: int, a_cons: int, a_ger: int) -> tuple[dict, float, bool, dict]:
        """Executa um timestep (1 hora).

        Args:
            a_arm  : ação do agente de armazenamento (0=carregar, 1=manter, 2=descarregar)
            a_cons : ação do agente de consumo       (0=nada, 1=pivo, 2=captacao, 3=ambos)
            a_ger  : ação do gerente de carga        (0=20kW, 1=30kW, 2=40kW)

        Returns:
            (próximo_estado, reward, done, info)
        """
        est = self._estado()
        r   = self.dados.iloc[self.hora]
        cfg = self.cfg
        cap = cfg["bateria_cap_kwh"]

        # Gerente: define teto
        teto = TETOS_KW[a_ger]

        # Geração total
        geracao = float(r["solar_kw"]) + float(r["eolico_kw"])

        # Consumo após cortes
        fixo     = float(r["sede_kw"]) + float(r["silo_kw"])  # não cortável
        pivo     = float(r["pivo_kw"])
        captacao = float(r["captacao_kw"])

        cortes = {0: (0, 0), 1: (pivo, 0), 2: (0, captacao), 3: (pivo, captacao)}
        c_pivo, c_cap = cortes[a_cons]
        corte_producao = c_cap > 0  # captação = bomba principal

        consumo       = min(fixo + (pivo - c_pivo) + (captacao - c_cap), teto)
        teto_excedido = consumo >= teto * 0.99

        # Bateria
        soc_kwh     = (self.soc / 100.0) * cap
        soc_min_kwh = (cfg["soc_min_pct"] / 100.0) * cap
        soc_max_kwh = (cfg["soc_max_pct"] / 100.0) * cap
        efic        = cfg["eficiencia"]

        if a_arm == 0:    # carregar
            disponivel = max(0.0, geracao - consumo)
            carga      = min(disponivel * efic, soc_max_kwh - soc_kwh)
            soc_kwh   += carga
            bat_delta  = carga
        elif a_arm == 2:  # descarregar
            falta      = max(0.0, consumo - geracao)
            descarga   = min(falta, soc_kwh - soc_min_kwh)
            soc_kwh   -= descarga
            bat_delta  = -descarga
        else:             # manter
            bat_delta  = 0.0

        self.soc    = max(0.0, min(100.0, (soc_kwh / cap) * 100.0))
        soc_critico = self.soc < cfg["soc_min_pct"]

        # Energia da rede
        descarga_util = abs(bat_delta) if bat_delta < 0 else 0.0
        rede_kwh      = max(0.0, consumo - geracao - descarga_util)
        excedente     = max(0.0, geracao - consumo - max(0.0, bat_delta))
        custo         = rede_kwh * est["tarifa"]

        # Reward cooperativo
        reward = (
            - cfg["w_custo"]         * custo
            - cfg["pen_soc"]         * float(soc_critico)
            - cfg["pen_teto"]        * float(teto_excedido)
            - cfg["pen_producao"]    * float(corte_producao)
            + cfg["bonus_excedente"] * excedente
            + cfg["bonus_soc_ok"]   * float(30 < self.soc < 80)
        )

        self.historico.append({
            "hora": self.hora, "soc": self.soc,
            "geracao_kw": geracao, "consumo_kw": consumo,
            "rede_kwh": rede_kwh, "excedente": excedente,
            "custo_r": custo, "tarifa": est["tarifa"], "reward": reward,
            "a_arm": a_arm, "a_cons": a_cons, "a_ger": a_ger,
        })

        self.hora += 1
        done  = self.hora >= 24
        prox  = self._estado() if not done else est
        return prox, reward, done, {"custo": custo, "rede_kwh": rede_kwh}
