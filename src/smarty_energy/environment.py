"""
FazendaEnergyEnv — Ambiente de simulação energética da fazenda.

Estado discreto (chave Q-table): (bucket_hora, bucket_soc, bucket_solar, bucket_tarifa)
  bucket_hora  : hora // 6        -> 4 valores  (0-5h / 6-11h / 12-17h / 18-23h)
  bucket_soc   : soc // 20        -> 5 valores  (0-20 / 20-40 / … / 80-100 %)
  bucket_solar : low/med/high     -> 3 valores  (<5 kW / 5-15 / >15)
  bucket_tarifa: normal/pico      -> 2 valores
  Total: 4x5x3x2 = 120 estados

Ações por agente:
  Armazenamento : 0=carregar  1=manter  2=descarregar
  Consumo       : 0=nada  1=corta_pivo  2=corta_captacao  3=corta_ambos
  Gerente       : 0=conservador(20kW)  1=moderado(30kW)  2=liberal(40kW)

Restrições implementadas:
  R1. Balanço de potência horário (fechamento energético)
  R2. Limite PCC ≤ 65,8 kW (importação e exportação)
  R3. Inversor FV ≤ 50 kW + eólico ≤ nominal
  R4. Não simultaneidade: importação/exportação mutuamente exclusivos
  R5. Dinâmica da bateria: η carga/descarga, SoC, throughput diário
"""

import pandas as pd
import numpy as np

from .config import CONFIG, TETOS_KW
from .agents import AgenteFinanceiro


class FazendaEnergyEnv:

    def __init__(self, dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, cfg: dict = CONFIG):
        self.dados  = dados_dia.reset_index(drop=True)
        self.tarifa = tarifa_24h
        self.cfg    = cfg
        self.fin    = AgenteFinanceiro(cfg)
        self.reset()

    def reset(self, soc_inicial: float | None = None) -> dict:
        """Reinicia o ambiente para um novo dia."""
        self.hora      = 0
        self.soc       = soc_inicial if soc_inicial is not None else self.cfg["soc_inicial_pct"]
        self.historico  = []
        self.bat_throughput_dia = 0.0
        
        # Novos contadores de restrições
        self.pivo_timer     = 0     # Horas seguidas ligado
        self.bomba_timer    = -4    # Positivo: ligado, Negativo: desligado (start com descanso)
        self.bomba_total_h  = 0     # Total de horas ON no dia
        self.secador_kwh_ac = 0.0   # Energia acumulada no secador
        
        return self._estado()

    def _estado(self) -> dict:
        r = self.dados.iloc[self.hora]
        return {
            "hora"     : self.hora,
            "soc"      : self.soc,
            "solar_kw" : float(r["solar_kw"]),
            "eolico_kw": float(r["eolico_kw"]),
            "tarifa"   : self.tarifa[self.hora],
            "stress"   : self.fin.calcular_estresse(self.tarifa[self.hora], 0.0), # Simplificado
            "sec_ac"   : self.secador_kwh_ac
        }

    def discretizar(self, est: dict) -> tuple:
        h = est["hora"] // 6
        s = min(int(est["soc"]), 100)
        g = 0 if est["solar_kw"] < 5 else (1 if est["solar_kw"] < 15 else 2)
        # Novo: Stress em 3 buckets
        str_val = est["stress"]
        st = 0 if str_val < 30 else (1 if str_val < 70 else 2)
        # Meta secador concluída?
        meta = 1 if est["sec_ac"] >= self.cfg["secador_meta_kwh"] else 0
        return (h, s, g, st, meta)

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

        # ── Gerente: define teto ──────────────────────────────────
        teto = TETOS_KW[a_ger]

        # ── R3: Geração com limites de inversor/nominal ───────────
        solar_kw  = min(float(r["solar_kw"]),  cfg["inversor_fv_max_kw"])
        eolico_kw = min(float(r["eolico_kw"]), cfg["eolico_nominal_kw"])
        geracao   = solar_kw + eolico_kw

        # ── Consumo após cortes e restrições ──────────────────────
        fixo     = float(r["sede_kw"]) + float(r["silo_kw"])
        pivo_nom = float(r["pivo_kw"])
        cap_nom  = float(r["captacao_kw"])
        
        # Sede Eco-Mode: reduz 20% se estresse alto (>80)
        stress_lvl = est["stress"]
        sede_ideal = float(r["sede_kw"])
        uso_eco = stress_lvl > 80
        sede_real = sede_ideal * 0.8 if uso_eco else sede_ideal
        fixo = sede_real + float(r["silo_kw"])

        # Mapeamento de ações do consumo (0-7 para os 3 dispositivos)
        # bit 0: pivo, bit 1: bomba, bit 2: secador
        c_pivo = (a_cons & 1) > 0
        c_bomba = (a_cons & 2) > 0
        c_sec   = (a_cons & 4) > 0

        # Penalidades Operacionais
        pen_oper = 0.0

        # R: Pivo 8h consecutivas
        if c_pivo:
            if 0 < self.pivo_timer < self.cfg["pivo_horas_alvo"]:
                pen_oper += self.cfg["pen_pivo_quebra"]
            self.pivo_timer = 0
        else:
            self.pivo_timer += 1

        # R: Bomba (2h ON / 4h OFF)
        if not c_bomba: # Quer ligar
            if self.bomba_timer < 0 and abs(self.bomba_timer) < self.cfg["bomba_off_min"]:
                pen_oper += self.cfg["pen_bomba_ciclo"]
                c_bomba = True # Força corte por segurança física
            elif self.bomba_timer >= self.cfg["bomba_on_max"]:
                pen_oper += self.cfg["pen_bomba_ciclo"]
                c_bomba = True # Força corte
            
            if not c_bomba: # Se ainda estiver ligada
                self.bomba_timer = max(1, self.bomba_timer + 1)
                self.bomba_total_h += 1
        else: # Cortada
            self.bomba_timer = min(-1, self.bomba_timer - 1)

        # R: Secador (Consumo variável 0.44 - 2.2 kW)
        # Se não cortado, consome proporcional ao teto ou geração excedente
        p_sec = 0.0
        if not c_sec:
            p_sec = 2.2 if stress_lvl < 40 else 0.44
            self.secador_kwh_ac += p_sec

        consumo       = min(fixo + (0 if c_pivo else pivo_nom) + (0 if c_bomba else cap_nom) + p_sec, teto)
        teto_excedido = consumo >= teto * 0.99
        corte_producao = c_bomba or c_pivo or c_sec

        # ── R5: Bateria com η carga/descarga + throughput diário ──
        soc_kwh     = (self.soc / 100.0) * cap
        soc_min_kwh = (cfg["soc_min_pct"] / 100.0) * cap
        soc_max_kwh = (cfg["soc_max_pct"] / 100.0) * cap
        eta_c       = cfg["eficiencia_carga"]
        eta_d       = cfg["eficiencia_descarga"]
        tp_restante = cfg["bat_throughput_max_kwh"] - self.bat_throughput_dia

        bat_carga    = 0.0  # kWh entrando na bateria (lado DC)
        bat_descarga = 0.0  # kWh saindo da bateria (lado DC)

        if a_arm == 0:    # carregar
            disponivel  = max(0.0, geracao - consumo)
            carga_dc    = min(disponivel * eta_c, soc_max_kwh - soc_kwh, tp_restante)
            soc_kwh    += carga_dc
            bat_carga   = carga_dc
        elif a_arm == 2:  # descarregar
            falta       = max(0.0, consumo - geracao)
            descarga_dc = min(falta / eta_d, soc_kwh - soc_min_kwh, tp_restante)
            soc_kwh    -= descarga_dc
            bat_descarga = descarga_dc

        self.bat_throughput_dia += bat_carga + bat_descarga
        self.soc    = max(0.0, min(100.0, (soc_kwh / cap) * 100.0))
        soc_critico = self.soc < cfg["soc_min_pct"]

        # ── R1 + R4: Balanço de potência (fechamento energético) ──
        # Energia útil entregue pela bateria à carga (lado AC)
        descarga_util = bat_descarga * eta_d
        # Energia consumida da geração para carregar (lado AC)
        carga_consumida = bat_carga / eta_c if eta_c > 0 else 0.0

        # Balanço: o que sobra/falta após geração atender consumo e bateria
        saldo = geracao - consumo - carga_consumida + descarga_util

        # R4: importação e exportação mutuamente exclusivos
        if saldo >= 0:
            importacao = 0.0
            exportacao = saldo
        else:
            importacao = -saldo
            exportacao = 0.0

        # ── R2: Limite PCC ────────────────────────────────────────
        pcc_max      = cfg["pcc_max_kw"]
        pcc_violado  = importacao > pcc_max or exportacao > pcc_max
        importacao   = min(importacao, pcc_max)
        exportacao   = min(exportacao, pcc_max)

        self.fin.atualizar_saldo(importacao, exportacao)

        rede_kwh  = importacao
        excedente = exportacao
        custo     = rede_kwh * est["tarifa"]

        # ── Decomposição da origem do consumo (kWh por hora) ──────
        # Geração própria direto, bateria e rede. Soma fecha com `consumo`.
        ger_disp_carga    = max(0.0, geracao - carga_consumida)
        fonte_geracao_kwh = min(consumo, ger_disp_carga)
        restante_consumo  = consumo - fonte_geracao_kwh
        fonte_bateria_kwh = min(restante_consumo, descarga_util)
        fonte_rede_kwh    = max(0.0, consumo - fonte_geracao_kwh - fonte_bateria_kwh)

        # Consumo nominal por máquina (kWh na hora, antes do corte pelo teto)
        pivo_kw_consumido     = 0.0 if c_pivo  else pivo_nom
        captacao_kw_consumido = 0.0 if c_bomba else cap_nom
        secador_kw_consumido  = p_sec
        sede_kw_consumido     = sede_real
        silo_kw_consumido     = float(r["silo_kw"])

        self.hora += 1
        done  = self.hora >= 24

        # ── Final do dia: metas diárias ───────────────────────────
        pen_metas = 0.0
        if done:
            if self.secador_kwh_ac < cfg["secador_meta_kwh"]:
                pen_metas += cfg["pen_secador_meta"]
            if self.bomba_total_h < 6: # Mínimo diário bomba
                pen_metas += cfg["pen_bomba_ciclo"]

        # ── Shaping: ponto ótimo de uso por máquina ───────────────
        # Pico tarifário (18-20h em tarifa azul → > 0.9 R$/kWh)
        em_pico_tarifa = est["tarifa"] > 0.9
        # Janela solar forte para irrigação/pivô
        sol_forte      = solar_kw >= 15.0
        # Excedente disponível (após cargas fixas) — bom para secador
        excedente_ger  = (geracao - fixo) >= 5.0

        pivo_ligado    = not c_pivo
        bomba_ligada   = not c_bomba
        secador_ligado = not c_sec

        pen_bomba_pico      = cfg["pen_bomba_pico"]      if (bomba_ligada  and em_pico_tarifa) else 0.0
        bonus_pivo_solar    = cfg["bonus_pivo_solar"]    if (pivo_ligado   and sol_forte)      else 0.0
        bonus_sec_excedente = cfg["bonus_sec_excedente"] if (secador_ligado and excedente_ger)  else 0.0
        bonus_bomba_offpeak = cfg["bonus_bomba_offpeak"] if (bomba_ligada  and not em_pico_tarifa) else 0.0

        # ── Reward cooperativo ────────────────────────────────────
        reward = (
            - cfg["w_custo"]         * custo
            - cfg["w_estresse"]      * (stress_lvl / 10.0)
            - cfg["pen_soc"]         * float(soc_critico)
            - cfg["pen_teto"]        * float(teto_excedido)
            - cfg["pen_pcc"]         * float(pcc_violado)
            - pen_oper
            - pen_metas
            - pen_bomba_pico
            + bonus_pivo_solar
            + bonus_sec_excedente
            + bonus_bomba_offpeak
            + cfg["bonus_excedente"] * excedente * est["tarifa"]
            + cfg["bonus_soc_ok"]    * float(30 < self.soc < 80)
        )

        self.historico.append({
            "hora": self.hora - 1, "soc": self.soc,
            "geracao_kw": geracao, "consumo_kw": consumo,
            "solar_kw": solar_kw, "eolico_kw": eolico_kw,
            "rede_kwh": rede_kwh, "excedente": excedente,
            "importacao": importacao, "exportacao": exportacao,
            "custo_r": custo, "tarifa": est["tarifa"], "reward": reward,
            "a_arm": a_arm, "a_cons": a_cons, "a_ger": a_ger,
            "bat_carga": bat_carga, "bat_descarga": bat_descarga,
            "pcc_violado": pcc_violado,
            # Origem da energia consumida
            "fonte_geracao_kwh": fonte_geracao_kwh,
            "fonte_bateria_kwh": fonte_bateria_kwh,
            "fonte_rede_kwh"   : fonte_rede_kwh,
            # Consumo realizado por máquina
            "pivo_kw_consumido"    : pivo_kw_consumido,
            "captacao_kw_consumido": captacao_kw_consumido,
            "sede_kw_consumido"    : sede_kw_consumido,
            "silo_kw_consumido"    : silo_kw_consumido,
            "secador_kw_consumido" : secador_kw_consumido,
            # Flags de contexto (para auditoria)
            "em_pico_tarifa": em_pico_tarifa,
            "bomba_ligada"  : bomba_ligada,
        })

        prox  = self._estado() if not done else est
        return prox, reward, done, {"custo": custo, "rede_kwh": rede_kwh}
