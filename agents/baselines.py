"""
Baselines para comparação com o IQLSystem.

AgentesHeuristicos — regras fixas (espelha smarty_energy.agents.AgentesHeuristicos).
SemAgente         — bateria em manter, nenhuma carga cortada, gerente liberal.
"""

import numpy as np

from config import CONFIG


class AgentesHeuristicos:
    """Baseline com regras fixas + cálculo próprio de estresse."""

    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg

    def stress_financeiro(self, est: dict) -> float:
        """Estresse 0-100 com base em tarifa e SOC (diferente do AgenteFinanceiro do env)."""
        t_min, t_max = 0.681282, 1.103868
        s_tar = (est["tarifa"] - t_min) / (t_max - t_min) * 70.0
        s_bat = 30.0 if est["soc"] < 20 else (10.0 if est["soc"] < 40 else 0.0)
        return min(100.0, s_tar + s_bat)

    def armazenamento(self, est: dict) -> int:
        soc, solar, tarifa = est["soc"], est["solar_kw"], est["tarifa"]
        if soc > self.cfg["soc_max_pct"]:
            return 1
        if soc < self.cfg["soc_min_pct"] + 2:
            return 1
        if tarifa > 0.9:
            return 2
        if solar > 10 and soc < 80:
            return 0
        if solar > 3 and soc < 50:
            return 0
        return 1

    def consumo(self, est: dict, stress: float) -> int:
        """bit0=pivo, bit1=bomba, bit2=secador."""
        if stress > 85:
            return 7
        if stress > 70:
            return 3
        if stress > 50:
            return 2
        if stress > 30:
            return 1
        return 0

    def gerente(self, est: dict, stress: float) -> int:
        if stress > 70:
            return 0
        if stress > 35:
            return 1
        return 2

    def agir(self, est: dict) -> tuple[int, int, int]:
        stress = self.stress_financeiro(est)
        return self.armazenamento(est), self.consumo(est, stress), self.gerente(est, stress)

    def avaliar(self, dias, tarifa_24h, env_cls, n_dias: int = 30,
                tracker=None, tracker_key: str = "heuristico",
                propagar_soc: bool = True) -> dict:
        custos, redes, viols_soc, rewards = [], [], [], []
        soc_proximo = self.cfg["soc_inicial_pct"]

        for ep in range(n_dias):
            dados_dia = dias[ep % len(dias)]
            env = env_cls(dados_dia, tarifa_24h, self.cfg)
            est = env.reset(soc_inicial=soc_proximo)

            custo_dia = rede_dia = viols = reward_dia = 0.0
            for _ in range(24):
                a_arm, a_cons, a_ger = self.agir(est)
                est, reward, done, info = env.step(a_arm, a_cons, a_ger)
                custo_dia += info["custo_r"]
                rede_dia  += info["rede_kwh"]
                reward_dia += info["reward"]
                if info["soc"] < self.cfg["soc_min_pct"]:
                    viols += 1
                if tracker:
                    tracker.registrar_passo(info, agente=tracker_key)

            if propagar_soc:
                soc_proximo = env.soc

            custos.append(custo_dia)
            redes.append(rede_dia)
            viols_soc.append(viols)
            rewards.append(reward_dia)

            if tracker:
                tracker.fechar_episodio(
                    agente=tracker_key, reward_total=reward_dia,
                    custo_total=custo_dia, epsilon=0.0, cenario="REAL",
                )

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(redes)),
            "violacoes_soc_media_h_dia": float(np.mean(viols_soc)),
            "reward_medio_dia": float(np.mean(rewards)),
        }


class SemAgente:
    """Cenário sem gestão: manter bateria, nada cortado, gerente liberal."""

    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg

    def agir(self, est: dict) -> tuple[int, int, int]:
        return 1, 0, 2

    def avaliar(self, dias, tarifa_24h, env_cls, n_dias: int = 30,
                tracker=None, tracker_key: str = "sem_agente",
                propagar_soc: bool = True) -> dict:
        custos, redes, viols_soc, rewards = [], [], [], []
        soc_proximo = self.cfg["soc_inicial_pct"]

        for ep in range(n_dias):
            dados_dia = dias[ep % len(dias)]
            env = env_cls(dados_dia, tarifa_24h, self.cfg)
            est = env.reset(soc_inicial=soc_proximo)

            custo_dia = rede_dia = viols = reward_dia = 0.0
            for _ in range(24):
                a_arm, a_cons, a_ger = self.agir(est)
                est, reward, done, info = env.step(a_arm, a_cons, a_ger)
                custo_dia += info["custo_r"]
                rede_dia  += info["rede_kwh"]
                reward_dia += info["reward"]
                if info["soc"] < self.cfg["soc_min_pct"]:
                    viols += 1
                if tracker:
                    tracker.registrar_passo(info, agente=tracker_key)

            if propagar_soc:
                soc_proximo = env.soc

            custos.append(custo_dia)
            redes.append(rede_dia)
            viols_soc.append(viols)
            rewards.append(reward_dia)

            if tracker:
                tracker.fechar_episodio(
                    agente=tracker_key, reward_total=reward_dia,
                    custo_total=custo_dia, epsilon=0.0, cenario="REAL",
                )

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(redes)),
            "violacoes_soc_media_h_dia": float(np.mean(viols_soc)),
            "reward_medio_dia": float(np.mean(rewards)),
        }
