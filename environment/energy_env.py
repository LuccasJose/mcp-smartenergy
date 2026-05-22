"""
FazendaEnergyEnv — ambiente de simulação energética da fazenda
(porte fiel de smarty_energy/environment.py).

Diferença em relação ao original: o método `step` retorna no `info`
o dict completo do último item de `self.historico` (em vez de só
`{custo, rede_kwh}`), para que o MetricsTracker do MCP funcione sem
ler `env.historico` diretamente.

Estado discreto (2160): hora(4) × soc(10) × solar(3) × stress(3)
                        × meta_sec(2) × bomba(3)

Ações:
  Armazenamento : 0=carregar  1=manter  2=descarregar
  Consumo (3 bits): bit0=corta pivô  bit1=corta bomba  bit2=corta secador
  Gerente       : 0=conservador(20kW)  1=moderado(30kW)  2=liberal(40kW)
"""

import pandas as pd
import numpy as np

from config import CONFIG, TETOS_KW, BOMBA_HORAS_ON
from agents.financeiro import AgenteFinanceiro


class FazendaEnergyEnv:

    def __init__(self, dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, cfg: dict = CONFIG):
        self.dados  = dados_dia.reset_index(drop=True)
        self.tarifa = tarifa_24h
        self.cfg    = cfg
        self.fin    = AgenteFinanceiro(cfg)
        self.reset()

    def reset(self, soc_inicial: float | None = None) -> dict:
        self.hora      = 0
        self.soc       = soc_inicial if soc_inicial is not None else self.cfg["soc_inicial_pct"]
        self.historico = []
        self.bat_throughput_dia = 0.0
        self.pivo_lock         = 0
        self.pivo_ativado_hoje = False
        self.bomba_total_h     = 0
        self.secador_kwh_ac    = 0.0
        return self._estado()

    def _estado(self) -> dict:
        r = self.dados.iloc[self.hora]
        return {
            "hora"     : self.hora,
            "soc"      : self.soc,
            "solar_kw" : float(r["solar_kw"]),
            "eolico_kw": float(r["eolico_kw"]),
            "tarifa"   : float(self.tarifa[self.hora]),
            "stress"   : self.fin.calcular_estresse(self.tarifa[self.hora], 0.0),
            "sec_ac"   : self.secador_kwh_ac,
            "bomba_h"  : self.bomba_total_h,
            "em_pico_tarifa": bool(self.tarifa[self.hora] > 0.9),
            "saldo_creditos_kwh": float(self.fin.saldo_creditos),
        }

    def discretizar(self, est: dict) -> tuple:
        h = est["hora"] // 6
        s = min(int(est["soc"] / 10), 9)
        g = 0 if est["solar_kw"] < 5 else (1 if est["solar_kw"] < 15 else 2)
        str_val = est["stress"]
        st = 0 if str_val < 30 else (1 if str_val < 70 else 2)
        meta = 1 if est["sec_ac"] >= self.cfg["secador_meta_kwh"] else 0
        bh = est["bomba_h"]
        b = 0 if bh < 3 else (1 if bh < 6 else 2)
        return (h, s, g, st, meta, b)

    def step(self, a_arm: int, a_cons: int, a_ger: int) -> tuple[dict, float, bool, dict]:
        est = self._estado()
        r   = self.dados.iloc[self.hora]
        cfg = self.cfg
        cap = cfg["bateria_cap_kwh"]
        teto = TETOS_KW[a_ger]

        # Geração com limites de inversor/nominal
        solar_kw  = min(float(r["solar_kw"]),  cfg["inversor_fv_max_kw"])
        eolico_kw = min(float(r["eolico_kw"]), cfg["eolico_nominal_kw"])
        geracao   = solar_kw + eolico_kw

        # Consumo
        fixo     = float(r["sede_kw"]) + float(r["silo_kw"])
        pivo_nom = float(r["pivo_kw"])
        cap_nom  = float(r["captacao_kw"])

        c_pivo  = (a_cons & 1) > 0
        c_bomba = (a_cons & 2) > 0
        c_sec   = (a_cons & 4) > 0
        stress_lvl = est["stress"]
        pen_oper = 0.0

        # R-SEDE — clamp ±20% + eco-mode em stress alto
        sede_ideal = float(r["sede_kw"])
        sede_real  = sede_ideal * 0.8 if stress_lvl > 80 else sede_ideal
        sede_lo    = sede_ideal * (1.0 - cfg["sede_desvio_max"])
        sede_hi    = sede_ideal * (1.0 + cfg["sede_desvio_max"])
        sede_real  = max(sede_lo, min(sede_hi, sede_real))
        fixo       = sede_real + float(r["silo_kw"])

        # R-PIVO — 8h consecutivas, 1 ativação por dia (HARD)
        pivo_em_lock = self.pivo_lock > 0
        if pivo_em_lock:
            c_pivo = False
            self.pivo_lock -= 1
        elif not c_pivo and not self.pivo_ativado_hoje:
            if self.hora + cfg["pivo_horas_alvo"] <= 24:
                self.pivo_lock = cfg["pivo_horas_alvo"] - 1
                c_pivo = False
                self.pivo_ativado_hoje = True
                pivo_em_lock = True
            else:
                c_pivo = True
        else:
            c_pivo = True
        if pivo_em_lock:
            pivo_nom = max(pivo_nom, cfg["pivo_nominal_kw"])

        # R-BOMBA — cronograma fixo (HARD)
        c_bomba = self.hora not in BOMBA_HORAS_ON
        if not c_bomba:
            cap_nom = max(cap_nom, cfg["bomba_cap_nominal_kw"])
            self.bomba_total_h += 1

        # R-SECADOR — 0.44 ou 2.2 kW conforme stress, meta diária 20 kWh, rescue tardio
        p_sec_pot   = 2.2 if stress_lvl < 40 else 0.44
        p_sec_max   = 2.2
        horas_restantes = 24 - self.hora
        kwh_faltam  = cfg["secador_meta_kwh"] - self.secador_kwh_ac
        if kwh_faltam > 0 and (horas_restantes - 1) * p_sec_max < kwh_faltam:
            c_sec = False
            p_sec_pot = p_sec_max
        p_sec = 0.0 if c_sec else p_sec_pot
        if not c_sec:
            self.secador_kwh_ac += p_sec

        consumo       = min(fixo + (0 if c_pivo else pivo_nom) + (0 if c_bomba else cap_nom) + p_sec, teto)
        teto_excedido = consumo >= teto * 0.99

        kwh_cortado = (
            (pivo_nom  if c_pivo  else 0.0)
            + (cap_nom if c_bomba else 0.0)
            + (p_sec_pot if c_sec else 0.0)
        )

        # Bateria com η carga/descarga + throughput diário
        soc_kwh     = (self.soc / 100.0) * cap
        soc_min_kwh = (cfg["soc_min_pct"] / 100.0) * cap
        soc_max_kwh = (cfg["soc_max_pct"] / 100.0) * cap
        eta_c       = cfg["eficiencia_carga"]
        eta_d       = cfg["eficiencia_descarga"]
        tp_restante = cfg["bat_throughput_max_kwh"] - self.bat_throughput_dia

        bat_carga    = 0.0
        bat_descarga = 0.0

        if a_arm == 0:
            disponivel  = max(0.0, geracao - consumo)
            carga_dc    = min(disponivel * eta_c, soc_max_kwh - soc_kwh, tp_restante)
            soc_kwh    += carga_dc
            bat_carga   = carga_dc
        elif a_arm == 2:
            falta       = max(0.0, consumo - geracao)
            descarga_dc = min(falta / eta_d, soc_kwh - soc_min_kwh, tp_restante)
            soc_kwh    -= descarga_dc
            bat_descarga = descarga_dc

        self.bat_throughput_dia += bat_carga + bat_descarga
        self.soc    = max(0.0, min(100.0, (soc_kwh / cap) * 100.0))
        soc_critico = self.soc < cfg["soc_min_pct"]

        # Balanço energético
        descarga_util   = bat_descarga * eta_d
        carga_consumida = bat_carga / eta_c if eta_c > 0 else 0.0
        saldo = geracao - consumo - carga_consumida + descarga_util
        if saldo >= 0:
            importacao = 0.0
            exportacao = saldo
        else:
            importacao = -saldo
            exportacao = 0.0

        pcc_max     = cfg["pcc_max_kw"]
        pcc_violado = importacao > pcc_max or exportacao > pcc_max
        importacao  = min(importacao, pcc_max)
        exportacao  = min(exportacao, pcc_max)

        self.fin.atualizar_saldo(importacao, exportacao)

        rede_kwh  = importacao
        excedente = exportacao
        custo     = rede_kwh * est["tarifa"]

        # Origem do consumo
        ger_disp_carga    = max(0.0, geracao - carga_consumida)
        fonte_geracao_kwh = min(consumo, ger_disp_carga)
        restante_consumo  = consumo - fonte_geracao_kwh
        fonte_bateria_kwh = min(restante_consumo, descarga_util)
        fonte_rede_kwh    = max(0.0, consumo - fonte_geracao_kwh - fonte_bateria_kwh)

        # Por máquina
        pivo_kw_consumido     = 0.0 if c_pivo  else pivo_nom
        captacao_kw_consumido = 0.0 if c_bomba else cap_nom
        secador_kw_consumido  = p_sec
        sede_kw_consumido     = sede_real
        silo_kw_consumido     = float(r["silo_kw"])

        self.hora += 1
        done = self.hora >= 24

        pen_metas = 0.0
        if done and self.secador_kwh_ac < cfg["secador_meta_kwh"]:
            pen_metas += cfg["pen_secador_meta"]

        # Shaping
        em_pico_tarifa = est["tarifa"] > 0.9
        sol_forte      = solar_kw >= 15.0
        excedente_ger  = (geracao - fixo) >= 5.0
        pivo_ligado    = not c_pivo
        bomba_ligada   = not c_bomba
        secador_ligado = not c_sec

        pen_pivo_pico       = cfg["pen_pivo_pico"]       if (pivo_ligado    and em_pico_tarifa) else 0.0
        pen_secador_pico    = cfg["pen_secador_pico"]    if (secador_ligado and em_pico_tarifa) else 0.0
        bonus_pivo_solar    = cfg["bonus_pivo_solar"]    if (pivo_ligado    and sol_forte)      else 0.0
        bonus_sec_excedente = cfg["bonus_sec_excedente"] if (secador_ligado and excedente_ger)  else 0.0

        bonus_carga_solar = 0.0
        if a_arm == 0 and saldo >= 0:
            bonus_carga_solar = bat_carga * cfg["w_bonus_carga"]

        # Reward cooperativo
        reward = (
            - cfg["w_custo"]         * custo
            - cfg["w_estresse"]      * (stress_lvl / 10.0)
            - cfg["pen_soc"]         * float(soc_critico)
            - cfg["pen_teto"]        * float(teto_excedido)
            - cfg["pen_pcc"]         * float(pcc_violado)
            - cfg["pen_producao"]    * kwh_cortado
            - pen_oper
            - pen_metas
            - pen_pivo_pico
            - pen_secador_pico
            + bonus_pivo_solar
            + bonus_sec_excedente
            + bonus_carga_solar
            + cfg["bonus_excedente"] * excedente * est["tarifa"]
            + cfg["bonus_soc_ok"]    * float(30 < self.soc < 80)
        )

        passo_info = {
            "hora": self.hora - 1, "soc": self.soc,
            "geracao_kw": geracao, "consumo_kw": consumo,
            "solar_kw": solar_kw, "eolico_kw": eolico_kw,
            "rede_kwh": rede_kwh, "excedente": excedente,
            "importacao": importacao, "exportacao": exportacao,
            "custo_r": custo, "tarifa": est["tarifa"], "reward": reward,
            "a_arm": a_arm, "a_cons": a_cons, "a_ger": a_ger,
            "bat_carga": bat_carga, "bat_descarga": bat_descarga,
            "pcc_violado": pcc_violado,
            "soc_violado": soc_critico,
            "fonte_geracao_kwh": fonte_geracao_kwh,
            "fonte_bateria_kwh": fonte_bateria_kwh,
            "fonte_rede_kwh"   : fonte_rede_kwh,
            "pivo_kw_consumido"    : pivo_kw_consumido,
            "captacao_kw_consumido": captacao_kw_consumido,
            "sede_kw_consumido"    : sede_kw_consumido,
            "silo_kw_consumido"    : silo_kw_consumido,
            "secador_kw_consumido" : secador_kw_consumido,
            "em_pico_tarifa": em_pico_tarifa,
            "bomba_ligada"  : bomba_ligada,
            "bomba_agendada": (self.hora - 1) in BOMBA_HORAS_ON,
            "kwh_cortado"   : kwh_cortado,
            "stress": stress_lvl,
            "saldo_creditos_kwh": float(self.fin.saldo_creditos),
            "teto_excedido": teto_excedido,
            "pivo_em_lock": pivo_em_lock,
            "secador_kwh_ac": self.secador_kwh_ac,
        }
        self.historico.append(passo_info)

        prox = self._estado() if not done else est
        return prox, reward, done, passo_info

    def get_full_state(self) -> dict:
        """Estado descritivo para inspeção externa (compatibilidade com server)."""
        est = self._estado()
        return {**est, "n_dias_processados": 0}
