import numpy as np
from config import (
    HORAS_PICO, SOC_MINIMO, SOC_MAXIMO, BOMBA_WATCHDOG_HORAS,
    N_ACOES_CONSUMO, PIVO_KW, CAPTACAO_KW, SECADOR_KW,
)


class AgenteHeuristico:
    """
    Agente baseado em regras para uso como baseline de comparação.

    Estratégia:
    - Bateria: carrega fora do pico com excedente solar; descarrega no pico
    - Cargas:  corta pivô e secador durante o pico tarifário
    - Gerente: conservador fora do pico, moderado durante geração alta
    """

    def choose_action(self, obs: dict) -> tuple[int, int, int]:
        hora = obs["hora"]
        soc = obs["soc"]
        em_pico = obs["em_pico_tarifa"]
        geracao = obs["geracao_kw"]
        consumo = obs["consumo_base_kw"]

        # a_arm
        if em_pico and soc > SOC_MINIMO + 0.10:
            a_arm = 2  # descarregar durante pico
        elif not em_pico and geracao > consumo * 0.6 and soc < SOC_MAXIMO - 0.05:
            a_arm = 0  # carregar fora do pico com solar
        else:
            a_arm = 1  # manter

        # a_cons: corta pivô(bit0) e secador(bit2) no pico
        a_cons = 0
        if em_pico:
            a_cons |= 0b001  # corta pivô
            a_cons |= 0b100  # corta secador

        # a_ger
        if geracao > 25.0:
            a_ger = 1  # moderado
        else:
            a_ger = 0  # conservador

        return a_arm, a_cons, a_ger

    def evaluate(self, env, n_dias: int = 30, tracker=None) -> dict:
        custos, redes, violacoes_soc, rewards = [], [], [], []

        for _ in range(n_dias):
            obs = env.reset()
            custo_dia = rede_dia = viols_soc = reward_dia = 0.0
            done = False

            while not done:
                a_arm, a_cons, a_ger = self.choose_action(obs)
                obs, reward, done, info = env.step(a_arm, a_cons, a_ger)

                if tracker:
                    tracker.registrar_passo(info, agente="heuristico")

                custo_dia += info["custo_r"]
                rede_dia += info["rede_kwh"]
                reward_dia += info["reward"]
                if info["soc"] < SOC_MINIMO:
                    viols_soc += 1

            custos.append(custo_dia)
            redes.append(rede_dia)
            violacoes_soc.append(viols_soc)
            rewards.append(reward_dia)

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(redes)),
            "violacoes_soc_media_h_dia": float(np.mean(violacoes_soc)),
            "reward_medio_dia": float(np.mean(rewards)),
        }


class SemAgente:
    """
    Baseline sem controle: tudo ligado, bateria em manutenção, gerente liberal.
    Representa o cenário sem sistema de gestão inteligente.
    """

    def choose_action(self, obs: dict) -> tuple[int, int, int]:
        return 1, 0, 2  # manter bateria, nada cortado, liberal

    def evaluate(self, env, n_dias: int = 30, tracker=None) -> dict:
        custos, redes, violacoes_soc, rewards = [], [], [], []

        for _ in range(n_dias):
            obs = env.reset()
            custo_dia = rede_dia = viols_soc = reward_dia = 0.0
            done = False

            while not done:
                a_arm, a_cons, a_ger = self.choose_action(obs)
                obs, reward, done, info = env.step(a_arm, a_cons, a_ger)

                if tracker:
                    tracker.registrar_passo(info, agente="sem_agente")

                custo_dia += info["custo_r"]
                rede_dia += info["rede_kwh"]
                reward_dia += info["reward"]
                if info["soc"] < SOC_MINIMO:
                    viols_soc += 1

            custos.append(custo_dia)
            redes.append(rede_dia)
            violacoes_soc.append(viols_soc)
            rewards.append(reward_dia)

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(redes)),
            "violacoes_soc_media_h_dia": float(np.mean(violacoes_soc)),
            "reward_medio_dia": float(np.mean(rewards)),
        }
