"""
FazendaEnergyEnv — Ambiente de simulação energética da fazenda.

Estado discreto (chave Q-table): (bucket_hora, bucket_soc, bucket_solar, bucket_stress, meta_sec, bucket_bomba)
  bucket_hora   : hora // 6        -> 4 valores  (0-5h / 6-11h / 12-17h / 18-23h)
  bucket_soc    : soc // 10        -> 10 valores (0-10 / 10-20 / … / 90-100 %)
  bucket_solar  : low/med/high     -> 3 valores  (<5 kW / 5-15 / >15)
  bucket_stress : low/med/high     -> 3 valores  (<30 / 30-70 / >70)
  meta_sec      : 0/1              -> 2 valores  (meta diária do secador atingida)
  bucket_bomba  : longe/perto/ok   -> 3 valores  (h < 3 / 3 ≤ h < 6 / h ≥ 6)
  Total: 4x10x3x3x2x3 = 2160 estados

Ações por agente:
  Armazenamento : 0=carregar  1=manter  2=descarregar
  Consumo       : bitmask de 3 bits — bit0=corta pivô, bit1=corta bomba,
                  bit2=corta secador (0=nada … 7=corta tudo)
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

from .config import CONFIG, TETOS_KW, BOMBA_HORAS_ON
from .agents import AgenteFinanceiro

# Dimensões da discretização do estado — FONTE ÚNICA (ver docstring do módulo).
# (bucket_hora, bucket_soc, bucket_solar, bucket_stress, meta_sec, bucket_bomba)
BUCKETS_ESTADO = (4, 10, 3, 3, 2, 3)
# Total combinatório de estados discretos possíveis. É um teto: parte das
# combinações é fisicamente inalcançável (ex.: hora e progresso da bomba são
# correlacionados), então a cobertura medida contra este total é conservadora.
ESPACO_ESTADOS_TOTAL = int(np.prod(BUCKETS_ESTADO))  # 4·10·3·3·2·3 = 2160


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
        
        # Estado das restrições — contadores e travas (HARD)
        self.pivo_lock         = 0      # R-PIVO: horas ON travadas restantes (lock de 8h)
        self.pivo_ativado_hoje = False  # R-PIVO: apenas 1 ativação de 8h por dia
        self.bomba_total_h     = 0      # R-BOMBA: contador para auditoria (schedule fixo)
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
            "sec_ac"   : self.secador_kwh_ac,
            "bomba_h"  : self.bomba_total_h,
            # Descritivos — não entram na discretização, mas alimentam o
            # prompt do LLM (llm_policy) e as tools do servidor MCP.
            "em_pico_tarifa"    : bool(self.tarifa[self.hora] > 0.9),
            "saldo_creditos_kwh": float(self.fin.saldo_creditos),
        }

    def get_full_state(self) -> dict:
        """Estado descritivo para inspeção externa (tools MCP get_current_state)."""
        return {**self._estado(), "hora_atual": self.hora, "done": self.hora >= 24}

    def discretizar(self, est: dict) -> tuple:
        h = est["hora"] // 6
        s = min(int(est["soc"] / 10), 9)   # 10 buckets: [0,10) [10,20) ... [90,100]
        g = 0 if est["solar_kw"] < 5 else (1 if est["solar_kw"] < 15 else 2)
        # Novo: Stress em 3 buckets
        str_val = est["stress"]
        st = 0 if str_val < 30 else (1 if str_val < 70 else 2)
        # Meta secador concluída?
        meta = 1 if est["sec_ac"] >= self.cfg["secador_meta_kwh"] else 0
        # Progresso da bomba vs meta diária (6h): longe / perto / atingida
        bh = est["bomba_h"]
        b = 0 if bh < 3 else (1 if bh < 6 else 2)
        return (h, s, g, st, meta, b)

    def step(self, a_arm: int, a_cons: int, a_ger: int) -> tuple[dict, float, bool, dict]:
        """Executa um timestep (1 hora).

        Args:
            a_arm  : ação do agente de armazenamento (0=carregar, 1=manter, 2=descarregar)
            a_cons : ação do agente de consumo — bitmask (1=pivô, 2=bomba, 4=secador)
            a_ger  : ação do gerente de carga        (0=20kW, 1=30kW, 2=40kW)

        Returns:
            (próximo_estado, reward, done, info) — `info` é o registro horário
            completo, o mesmo dict apendado em `self.historico`.
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
        
        # Mapeamento de ações do consumo (0-7 para os 3 dispositivos)
        # bit 0: pivo, bit 1: bomba, bit 2: secador
        c_pivo = (a_cons & 1) > 0
        c_bomba = (a_cons & 2) > 0
        c_sec   = (a_cons & 4) > 0
        stress_lvl = est["stress"]

        # Penalidades Operacionais (acumula violações suaves residuais)
        pen_oper = 0.0

        # ╔═════════════════════════════════════════════════════════╗
        # ║ R-SEDE — desvio máximo ±20% da carga ideal (HARD)       ║
        # ║ Eco-mode em estresse alto reduz 20%; clamp defensivo    ║
        # ║ garante que sede_real ∈ [0.8, 1.2] × sede_ideal.        ║
        # ╚═════════════════════════════════════════════════════════╝
        sede_ideal = float(r["sede_kw"])
        # Eco-mode: reduz 20% quando estresse alto (≥70 dispara em pico tarifário).
        sede_eco_ativo = stress_lvl >= 70
        sede_real  = sede_ideal * 0.8 if sede_eco_ativo else sede_ideal
        sede_lo    = sede_ideal * (1.0 - cfg["sede_desvio_max"])
        sede_hi    = sede_ideal * (1.0 + cfg["sede_desvio_max"])
        sede_real  = max(sede_lo, min(sede_hi, sede_real))
        fixo       = sede_real + float(r["silo_kw"])

        # ╔═════════════════════════════════════════════════════════╗
        # ║ R-PIVO — 8h consecutivas + apenas 1 ativação por dia    ║
        # ║ Lock decrementa 7→0 forçando ON. Agente só pode iniciar ║
        # ║ se ainda não ativou hoje E cabem 8h restantes no dia.   ║
        # ╚═════════════════════════════════════════════════════════╝
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
                c_pivo = True                       # não cabe 8h
        else:
            c_pivo = True                           # já ativou hoje ou agente cortou
        if pivo_em_lock:
            pivo_nom = max(pivo_nom, cfg["pivo_nominal_kw"])

        # ╔═════════════════════════════════════════════════════════╗
        # ║ R-BOMBA — Cronograma fixo (HARD)                        ║
        # ║ 4 ciclos × 2h = 8h/dia, espaçados 6h, evitando pico.    ║
        # ║ Horas ON: 3-4, 9-10, 15-16, 21-22 (BOMBA_HORAS_ON).     ║
        # ║ Ação do agente é ignorada — sem espaço para violação.   ║
        # ╚═════════════════════════════════════════════════════════╝
        c_bomba = self.hora not in BOMBA_HORAS_ON
        if not c_bomba:
            cap_nom = max(cap_nom, cfg["bomba_cap_nominal_kw"])
            self.bomba_total_h += 1

        # ╔═════════════════════════════════════════════════════════╗
        # ║ R-SECADOR — usa Secadora real da base + meta ≥ 20 kWh   ║
        # ║ Agente decide cortar (c_sec=True) ou permitir.          ║
        # ║ Rescue: se adiar tornaria a meta inviável, força ON na  ║
        # ║ potência máxima (cfg.secador_max_kw).                   ║
        # ╚═════════════════════════════════════════════════════════╝
        p_sec_pot   = float(r.get("secador_kw", 0.0))    # potência agendada na hora
        p_sec_max   = cfg["secador_max_kw"]              # teto físico para rescue
        horas_restantes = 24 - self.hora
        kwh_faltam  = cfg["secador_meta_kwh"] - self.secador_kwh_ac
        # Adiar essa hora torna a meta inviável? → força ON na potência máxima.
        if kwh_faltam > 0 and (horas_restantes - 1) * p_sec_max < kwh_faltam:
            c_sec = False
            p_sec_pot = max(p_sec_pot, p_sec_max)
        p_sec = 0.0 if c_sec else p_sec_pot
        if not c_sec:
            self.secador_kwh_ac += p_sec

        consumo       = min(fixo + (0 if c_pivo else pivo_nom) + (0 if c_bomba else cap_nom) + p_sec, teto)
        teto_excedido = consumo >= teto * 0.99
        corte_producao = c_bomba or c_pivo or c_sec

        # kWh nominais cortados nesta hora (produção perdida)
        kwh_cortado = (
            (pivo_nom  if c_pivo  else 0.0)
            + (cap_nom if c_bomba else 0.0)
            + (p_sec_pot if c_sec else 0.0)
        )

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
        if done and self.secador_kwh_ac < cfg["secador_meta_kwh"]:
            # Defensivo: rescue do secador deveria garantir; fallback se algo escapar.
            pen_metas += cfg["pen_secador_meta"]

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

        # Bomba não tem shaping: cronograma fixo já evita pico por design.
        pen_pivo_pico       = cfg["pen_pivo_pico"]       if (pivo_ligado    and em_pico_tarifa) else 0.0
        pen_secador_pico    = cfg["pen_secador_pico"]    if (secador_ligado and em_pico_tarifa) else 0.0
        bonus_pivo_solar    = cfg["bonus_pivo_solar"]    if (pivo_ligado    and sol_forte)      else 0.0
        bonus_sec_excedente = cfg["bonus_sec_excedente"] if (secador_ligado and excedente_ger)  else 0.0

        # Bônus por carga solar (Incentivo para aproveitar o sol)
        bonus_carga_solar = 0.0
        if a_arm == 0 and saldo >= 0: # 0 = CARREGAR e saldo positivo (excedente)
            bonus_carga_solar = bat_carga * cfg["w_bonus_carga"]

        # ── Reward cooperativo ────────────────────────────────────
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

        # Registro horário completo — é ao mesmo tempo a linha do histórico e o
        # `info` devolvido pelo step, para que o tracker do servidor MCP e as
        # métricas (metrics.py) leiam a MESMA estrutura, sem acessar
        # `env.historico` por fora.
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
            "teto_excedido": teto_excedido,
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
            "bomba_agendada": self.hora - 1 in BOMBA_HORAS_ON,
            "sede_eco"      : sede_eco_ativo,
            "pivo_em_lock"  : pivo_em_lock,
            "kwh_cortado"   : kwh_cortado,
            # Estado financeiro e progresso de metas
            "stress"            : stress_lvl,
            "saldo_creditos_kwh": float(self.fin.saldo_creditos),
            "secador_kwh_ac"    : self.secador_kwh_ac,
        }
        self.historico.append(passo_info)

        prox  = self._estado() if not done else est
        return prox, reward, done, passo_info
