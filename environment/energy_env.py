import numpy as np
from typing import Optional
from config import (
    PCC_LIMITE_KW, SOC_MINIMO, SOC_MAXIMO,
    BATERIA_CAPACIDADE_KWH, BATERIA_MAX_CARGA_KW, BATERIA_MAX_DESCARGA_KW,
    BATERIA_EF_CARGA, BATERIA_EF_DESCARGA, SOC_INICIAL,
    HORAS_PICO, TARIFA_PICO, TARIFA_FORA_PICO,
    PIVO_KW, CAPTACAO_KW, SEDE_KW, SILO_KW_BASE, SECADOR_KW,
    BOMBA_WATCHDOG_HORAS, GERENTE_TETO,
    SOLAR_PERFIL, VENTO_PERFIL,
    REWARD_PESO_CUSTO, REWARD_PESO_REDE,
    REWARD_PENALIDADE_PCC, REWARD_PENALIDADE_SOC, REWARD_BONUS_RENOVAVEL,
)

# Arrays pré-alocados para geração vetorizada de perfis
_SOLAR_ARRAY = np.array(SOLAR_PERFIL, dtype=np.float64)
_VENTO_ARRAY = np.array(VENTO_PERFIL, dtype=np.float64)


class EnergyEnvironment:
    """
    Simulação horária de um sistema de energia rural com:
    - Geração solar + eólica
    - Bateria (armazenamento)
    - Cargas controláveis (pivô, bomba, secador)
    - Cargas fixas (sede, silo)
    - Conexão com a rede (PCC limitado a 65,8 kW)
    - Tarifa TOU (pico/fora-pico)
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)
        self.reset()

    # ------------------------------------------------------------------ #
    # Interface pública                                                    #
    # ------------------------------------------------------------------ #

    def reset(self) -> dict:
        self.hora = 0
        self.soc = SOC_INICIAL
        self.horas_bomba_hoje = 0
        self.bomba_watchdog = False
        self._gerar_dia()
        return self._get_obs()

    def step(self, a_arm: int, a_cons: int, a_ger: int) -> tuple:
        """Avança uma hora. Retorna (obs, reward, done, info)."""
        # ---- parse a_cons (3 bits) ----
        cortar_pivo = bool(a_cons & 0b001)
        cortar_bomba = bool(a_cons & 0b010)
        cortar_secador = bool(a_cons & 0b100)

        # ---- watchdog: força bomba nas últimas horas se necessário ----
        horas_restantes = 24 - self.hora  # inclui a hora atual
        horas_faltando = max(0, BOMBA_WATCHDOG_HORAS - self.horas_bomba_hoje)
        if horas_faltando > 0 and horas_faltando >= horas_restantes:
            cortar_bomba = False
            self.bomba_watchdog = True
        else:
            self.bomba_watchdog = False

        # ---- cargas ativas ----
        pivo_kw = 0.0 if cortar_pivo else PIVO_KW
        captacao_kw = 0.0 if cortar_bomba else CAPTACAO_KW
        sede_kw = SEDE_KW
        silo_kw = self.silo_kwh_h[self.hora]
        secador_kw = 0.0 if cortar_secador else SECADOR_KW
        consumo_kw = pivo_kw + captacao_kw + sede_kw + silo_kw + secador_kw

        # ---- teto do gerente ----
        teto = GERENTE_TETO[a_ger]
        solar_kw = float(np.clip(self.solar_kw_h[self.hora], 0.0, teto))
        eolico_kw = float(np.clip(self.eolico_kw_h[self.hora], 0.0, max(0.0, teto - solar_kw)))
        geracao_kw = solar_kw + eolico_kw

        # ---- bateria ----
        bat_carga = 0.0
        bat_descarga = 0.0
        saldo = geracao_kw - consumo_kw  # positivo = excedente, negativo = déficit

        if a_arm == 0:  # carregar
            espaco = (SOC_MAXIMO - self.soc) * BATERIA_CAPACIDADE_KWH / BATERIA_EF_CARGA
            bat_carga = float(np.clip(saldo, 0.0, min(BATERIA_MAX_CARGA_KW, espaco)))
        elif a_arm == 2:  # descarregar
            disponivel = (self.soc - SOC_MINIMO) * BATERIA_CAPACIDADE_KWH * BATERIA_EF_DESCARGA
            bat_descarga = float(np.clip(-saldo, 0.0, min(BATERIA_MAX_DESCARGA_KW, disponivel)))

        soc_delta = (bat_carga * BATERIA_EF_CARGA - bat_descarga / BATERIA_EF_DESCARGA) / BATERIA_CAPACIDADE_KWH
        novo_soc = float(np.clip(self.soc + soc_delta, 0.0, 1.0))

        # ---- balanço da rede ----
        balanco = geracao_kw + bat_descarga - bat_carga - consumo_kw
        importacao = float(max(0.0, -balanco))
        exportacao = float(max(0.0, balanco))
        rede_kwh = importacao

        # ---- violações ----
        pcc_violado = importacao >= PCC_LIMITE_KW
        soc_violado = novo_soc < SOC_MINIMO

        # ---- tarifa e custo ----
        em_pico = self.hora in HORAS_PICO
        tarifa = TARIFA_PICO if em_pico else TARIFA_FORA_PICO
        custo_r = rede_kwh * tarifa

        # ---- origens do consumo ----
        fonte_geracao_kwh = min(geracao_kw, consumo_kw)
        restante = consumo_kw - fonte_geracao_kwh
        fonte_bateria_kwh = min(bat_descarga, restante)
        fonte_rede_kwh = max(0.0, restante - fonte_bateria_kwh)

        # ---- kWh cortado ----
        kwh_cortado = (
            (PIVO_KW if cortar_pivo else 0.0)
            + (CAPTACAO_KW if cortar_bomba else 0.0)
            + (SECADOR_KW if cortar_secador else 0.0)
        )

        # ---- reward ----
        reward = (
            -REWARD_PESO_CUSTO * custo_r
            - REWARD_PESO_REDE * rede_kwh
            - REWARD_PENALIDADE_PCC * float(pcc_violado)
            - REWARD_PENALIDADE_SOC * float(soc_violado)
            + REWARD_BONUS_RENOVAVEL * (fonte_geracao_kwh + fonte_bateria_kwh)
        )

        # ---- atualiza estado ----
        self.soc = novo_soc
        if not cortar_bomba:
            self.horas_bomba_hoje += 1
        bomba_ligada = not cortar_bomba

        # ---- info completo ----
        info = {
            "hora": self.hora,
            "soc": float(self.soc),
            "tarifa": tarifa,
            "em_pico_tarifa": em_pico,
            "geracao_kw": geracao_kw,
            "solar_kw": solar_kw,
            "eolico_kw": eolico_kw,
            "consumo_kw": consumo_kw,
            "importacao": importacao,
            "exportacao": exportacao,
            "rede_kwh": rede_kwh,
            "excedente": exportacao,
            "bat_carga": bat_carga,
            "bat_descarga": bat_descarga,
            "fonte_geracao_kwh": fonte_geracao_kwh,
            "fonte_bateria_kwh": fonte_bateria_kwh,
            "fonte_rede_kwh": fonte_rede_kwh,
            "pivo_kw_consumido": pivo_kw,
            "captacao_kw_consumido": captacao_kw,
            "sede_kw_consumido": sede_kw,
            "silo_kw_consumido": silo_kw,
            "secador_kw_consumido": secador_kw,
            "custo_r": custo_r,
            "reward": reward,
            "a_arm": a_arm,
            "a_cons": a_cons,
            "a_ger": a_ger,
            "pcc_violado": pcc_violado,
            "bomba_ligada": bomba_ligada,
            "bomba_watchdog": self.bomba_watchdog,
            "kwh_cortado": kwh_cortado,
        }

        # ---- avança hora ----
        self.hora = (self.hora + 1) % 24
        done = self.hora == 0

        if done:
            self.horas_bomba_hoje = 0
            self.bomba_watchdog = False
            self._gerar_dia()

        return self._get_obs(), reward, done, info

    def get_full_state(self) -> dict:
        return {
            "hora": self.hora,
            "soc": float(self.soc),
            "em_pico_tarifa": self.hora in HORAS_PICO,
            "tarifa": TARIFA_PICO if self.hora in HORAS_PICO else TARIFA_FORA_PICO,
            "solar_kw": float(self.solar_kw_h[self.hora]),
            "eolico_kw": float(self.eolico_kw_h[self.hora]),
            "geracao_kw": float(self.solar_kw_h[self.hora] + self.eolico_kw_h[self.hora]),
            "consumo_base_kw": float(PIVO_KW + CAPTACAO_KW + SEDE_KW + self.silo_kwh_h[self.hora] + SECADOR_KW),
            "cenario_dia": self.cenario_dia,
            "solar_media_dia_kw": round(float(self.solar_media_dia), 2),
            "consumo_medio_dia_kw": round(float(self.consumo_medio_dia), 2),
            "horas_bomba_hoje": self.horas_bomba_hoje,
            "bomba_watchdog_ativo": self.bomba_watchdog,
        }

    # ------------------------------------------------------------------ #
    # Internos                                                             #
    # ------------------------------------------------------------------ #

    def _get_obs(self) -> dict:
        return {
            "hora": self.hora,
            "soc": float(self.soc),
            "em_pico_tarifa": self.hora in HORAS_PICO,
            "geracao_kw": float(self.solar_kw_h[self.hora] + self.eolico_kw_h[self.hora]),
            "consumo_base_kw": PIVO_KW + CAPTACAO_KW + SEDE_KW + self.silo_kwh_h[self.hora] + SECADOR_KW,
            "horas_bomba_hoje": self.horas_bomba_hoje,
        }

    def _gerar_dia(self):
        """Gera perfis de geração e carga para o próximo dia com variabilidade."""
        # clima solar
        clima = self.rng.choice(["ensolarado", "parcial", "nublado"], p=[0.50, 0.20, 0.30])
        fator_solar = {"ensolarado": 1.0, "parcial": 0.55, "nublado": 0.18}[clima]
        ruido_solar = self.rng.normal(1.0, 0.08, 24).clip(0.6, 1.4)
        self.solar_kw_h = _SOLAR_ARRAY * fator_solar * ruido_solar

        # vento
        fator_vento = self.rng.uniform(0.4, 1.6)
        ruido_vento = self.rng.normal(1.0, 0.12, 24).clip(0.3, 2.0)
        self.eolico_kw_h = _VENTO_ARRAY * fator_vento * ruido_vento

        # silo (carga variável, não controlável)
        fator_silo = self.rng.uniform(0.5, 1.5)
        self.silo_kwh_h = np.full(24, SILO_KW_BASE * fator_silo)

        # cenário do dia
        solar_media = float(np.mean(self.solar_kw_h))
        consumo_medio = PIVO_KW + CAPTACAO_KW + SEDE_KW + float(np.mean(self.silo_kwh_h)) + SECADOR_KW
        self.solar_media_dia = solar_media
        self.consumo_medio_dia = consumo_medio
        self.cenario_dia = _classificar_cenario(solar_media, consumo_medio)


def _classificar_cenario(solar_media: float, consumo_medio: float) -> str:
    if solar_media < 8.0:
        return "NUBLADO"
    if solar_media > 22.0 and consumo_medio > 60.0:
        return "ALTO CONSUMO"
    if solar_media > 22.0:
        return "ENSOLARADO"
    return "EQUILIBRADO"
