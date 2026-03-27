"""
SmartEnergy MAS — Pipeline principal.

Execução completa:
    1. Carrega dados do Excel
    2. Instancia os três agentes Q-Learning
    3. Treina por N episódios
    4. Plota curvas de aprendizado
    5. Avalia heurístico vs RL em todos os dias do mês
    6. Plota comparação no dia de maior diferença de custo
    7. Analisa e plota os três cenários (nublado, ensolarado, alto consumo)
    8. Imprime relatório final

Uso:
    python main.py
"""

import sys
import warnings
warnings.filterwarnings("ignore")

# Garante que o pacote src/smarty_energy é encontrado mesmo sem instalação
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np

from smarty_energy.config import CONFIG, OUTPUT_DIR
from smarty_energy.data_loader import carregar_dados
from smarty_energy.agents import AgenteQL
from smarty_energy.training import treinar
from smarty_energy.evaluation import (
    rodar_heuristico,
    rodar_rl,
    resumo_mes,
    delta_pct,
    identificar_cenarios,
)
from smarty_energy import visualization as viz


def main() -> None:
    # ── 1. Dados ──────────────────────────────────────────────────
    print("Carregando dados...")
    DIAS, TARIFA = carregar_dados()
    print(f"  {len(DIAS)} dias carregados (Janeiro 2025 — Fazenda Buritis)")

    sol_med  = np.mean([d["solar_kw"].mean() for d in DIAS])
    cons_med = np.mean([(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).mean()
                        for d in DIAS])
    print(f"  Geração solar média : {sol_med:.2f} kW/h")
    print(f"  Consumo total médio : {cons_med:.2f} kW/h")

    # ── 2. Agentes ────────────────────────────────────────────────
    AGENTES = {
        "armazenamento": AgenteQL(3, "Armazenamento", CONFIG),
        "consumo"      : AgenteQL(4, "Consumo",       CONFIG),
        "gerente"      : AgenteQL(3, "Gerente",        CONFIG),
    }

    # ── 3. Treinamento ────────────────────────────────────────────
    print(f"\nIniciando treinamento ({CONFIG['n_episodios']} episódios × 24 timesteps)...\n")
    REWARDS_HIST, CUSTOS_HIST = treinar(DIAS, TARIFA, AGENTES, CONFIG)
    print("\nTreinamento concluído!")
    for ag in AGENTES.values():
        print(f"  {ag.nome:<16} | {ag.n_estados:>3} estados | {ag.n_updates:>6} updates | ε={ag.epsilon:.3f}")

    # Salvar Q-tables
    models_dir = OUTPUT_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    for ag in AGENTES.values():
        ag.save(models_dir / f"qtable_{ag.nome.lower()}.pkl")
    print(f"  Q-tables salvas em: {models_dir}")

    # ── 4. Curvas de aprendizado ──────────────────────────────────
    print("\nGerando curvas de aprendizado...")
    viz.plot_curvas_aprendizado(REWARDS_HIST, CUSTOS_HIST)

    # ── 5. Avaliação mensal ───────────────────────────────────────
    print("\nAvaliando em todos os 31 dias...")
    RES_H = [rodar_heuristico(d, TARIFA) for d in DIAS]
    RES_R = [rodar_rl(d, TARIFA, AGENTES) for d in DIAS]

    CH, RH, VH, RWH = resumo_mes(RES_H)
    CR, RR, VR, RWR = resumo_mes(RES_R)

    print(f"\n{'AVALIAÇÃO — MÉDIA DIÁRIA (Janeiro 2025)':^62}")
    print(f"{'═'*62}")
    print(f"  {'Métrica':<30} {'Heurístico':>12} {'RL':>10} {'Δ':>8}")
    print(f"  {'─'*58}")
    print(f"  {'Custo (R$/dia)':<30} {CH:>12.2f} {CR:>10.2f} {delta_pct(CH, CR):>8}")
    print(f"  {'kWh da rede / dia':<30} {RH:>12.2f} {RR:>10.2f} {delta_pct(RH, RR):>8}")
    print(f"  {'Violações SOC / dia':<30} {VH:>12.2f} {VR:>10.2f}")
    print(f"  {'Reward médio / dia':<30} {RWH:>12.2f} {RWR:>10.2f} {delta_pct(RWH, RWR):>8}")
    print(f"{'═'*62}")

    # ── 6. Plot do melhor dia ─────────────────────────────────────
    difs = [sum(RES_H[i][h]["custo_r"] for h in range(24)) -
            sum(RES_R[i][h]["custo_r"] for h in range(24))
            for i in range(len(DIAS))]
    idx_melhor = int(np.argmax(difs))
    data_str   = DIAS[idx_melhor]["data"].iloc[0].strftime("%d/%m/%Y")
    print(f"\nGerando comparativo do dia {data_str} (maior diferença de custo)...")
    viz.plot_comparacao_dia(RES_H[idx_melhor], RES_R[idx_melhor], data_str)

    # ── 7. Cenários ───────────────────────────────────────────────
    print("\nAnalisando cenários...")
    cenarios_idx = identificar_cenarios(DIAS)
    NOMES = {
        "nublado"     : "Nublado",
        "ensolarado"  : "Ensolarado",
        "alto_consumo": "Alto Consumo",
    }
    ger_dia = [d["solar_kw"].sum() + d["eolico_kw"].sum() for d in DIAS]

    print(f"\n{'ANÁLISE DE CENÁRIOS':^68}")
    print(f"{'═'*68}")
    print(f"  {'Cenário':<18} {'Dia':>5} {'Geração':>10} {'Custo Heur.':>12} {'Custo RL':>10} {'Δ%':>7}")
    print(f"  {'─'*64}")

    resultados_cenarios = {}
    for chave, idx in cenarios_idx.items():
        nome = NOMES[chave]
        h_h  = rodar_heuristico(DIAS[idx], TARIFA)
        h_r  = rodar_rl(DIAS[idx], TARIFA, AGENTES)
        c_h  = sum(r["custo_r"] for r in h_h)
        c_r  = sum(r["custo_r"] for r in h_r)
        resultados_cenarios[nome] = (h_h, h_r, c_h, c_r, idx)
        data_s = DIAS[idx]["data"].iloc[0].strftime("%d/%m")
        delt   = ((c_r - c_h) / c_h * 100) if c_h > 0 else 0
        print(f"  {nome:<18} {data_s:>5} {ger_dia[idx]:>9.1f} kWh {c_h:>10.2f} R$ {c_r:>8.2f} R$ {delt:>+6.1f} %")
    print(f"{'═'*68}")

    viz.plot_cenarios(DIAS, resultados_cenarios)

    # ── 8. Relatório final ────────────────────────────────────────
    d_custo = ((CR - CH) / CH * 100)    if CH   != 0 else 0
    d_rede  = ((RR - RH) / RH * 100)    if RH   != 0 else 0
    d_rew   = ((RWR - RWH) / abs(RWH) * 100) if RWH != 0 else 0
    sinal_c = "ECONOMIA" if d_custo < 0 else "AUMENTO"
    sinal_r = "MELHORA"  if d_rew   > 0 else "PIORA"

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          RESUMO FINAL — SmartEnergy MAS PoC                 ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Episódios treinados  : {CONFIG['n_episodios']:<5}                              ║")
    print(f"║  Dias avaliados       : {len(DIAS):<5} (Janeiro 2025)                 ║")
    print(f"║  Tamanho bateria      : {CONFIG['bateria_cap_kwh']} kWh                          ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Custo médio heurístico : R$ {CH:>6.2f} / dia                    ║")
    print(f"║  Custo médio RL         : R$ {CR:>6.2f} / dia                    ║")
    print(f"║  Variação de custo      : {sinal_c} {d_custo:>+.1f} %                   ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  kWh da rede / dia (heur) : {RH:>6.2f}                          ║")
    print(f"║  kWh da rede / dia (RL)   : {RR:>6.2f}  ({d_rede:>+.1f} %)              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Violações SOC heurístico : {VH:.2f} / dia                      ║")
    print(f"║  Violações SOC RL         : {VR:.2f} / dia                      ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Reward médio heur. : {RWH:>8.2f}                              ║")
    print(f"║  Reward médio RL    : {RWR:>8.2f}   {sinal_r} {d_rew:>+.1f} %            ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Q-tables aprendidas:                                        ║")
    for ag in AGENTES.values():
        line = f"║    {ag.nome:<16}  {ag.n_estados:>3} estados  {ag.n_updates:>6} updates"
        print(f"{line:<63}║")
    print("╚══════════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
