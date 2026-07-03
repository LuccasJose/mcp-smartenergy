"""
SmartEnergy MAS — Pipeline principal.

Execução completa:
    1. Carrega dados do Excel
    2. Instancia os três agentes Q-Learning
    3. Treina por N episódios (ou carrega um run salvo)
    4. Plota curvas de aprendizado
    5. Avalia heurístico vs RL em todos os dias do mês
    6. Plota comparação no dia de maior diferença de custo
    7. Analisa e plota os três cenários (nublado, ensolarado, alto consumo)
    8. Imprime relatório final

Cada treino é versionado em outputs/runs/<run_id>/. O dashboard permite
escolher qual run visualizar.

Uso:
    python main.py                 # treina um novo run e abre o dashboard
    python main.py --replot        # reabre o run mais recente sem treinar
    python main.py --run <run_id>  # reabre um run específico
"""

import argparse
import sys
import warnings
warnings.filterwarnings("ignore")

# Garante saída UTF-8 no console (Windows costuma usar cp1252, o que quebra
# os caracteres de moldura/acentos do relatório).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Garante que o pacote src/smarty_energy é encontrado mesmo sem instalação
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np

from smarty_energy.config import CONFIG, DATA_PATH
from smarty_energy.data_loader import carregar_dados
from smarty_energy.agents import construir_agentes
from smarty_energy.training import treinar
from smarty_energy.evaluation import (
    rodar_sem_agente,
    rodar_heuristico,
    rodar_rl,
    resumo_mes,
    delta_pct,
    identificar_cenarios,
)
from smarty_energy import visualization as viz
from smarty_energy import runs
from smarty_energy.dashboard import abrir_dashboard


_NOMES_CENARIOS = {
    "nublado"     : "Nublado",
    "ensolarado"  : "Ensolarado",
    "alto_consumo": "Alto Consumo",
}


def construir_artefatos(
    run_id: str,
    dias,
    tarifa,
    res_s,
    res_h,
    custo_base_sem: float,
    custo_base_heur: float,
) -> dict:
    """Recarrega um run e monta RES_R + todas as figuras/dados do dashboard.

    Tudo que depende do run escolhido fica centralizado aqui, permitindo que
    o dashboard troque de run em tempo de execução chamando esta função.
    `res_s`, `res_h` e as baselines de custo independem do run.
    """
    res_r, hist = runs.resultados_rl(run_id, dias, tarifa)

    # ── Curvas de aprendizado (com baselines horizontais) ─────────
    fig_aprendizado = viz.plot_curvas_aprendizado(
        hist["rewards"], hist["custos"],
        eps_hist=hist.get("epsilons"),
        custo_baseline_sem=custo_base_sem,
        custo_baseline_heur=custo_base_heur,
    )

    # ── Dia de maior diferença de custo (Heur − RL) ───────────────
    difs = [sum(res_h[i][h]["custo_r"] for h in range(24)) -
            sum(res_r[i][h]["custo_r"] for h in range(24))
            for i in range(len(dias))]
    idx_melhor = int(np.argmax(difs))
    data_str   = dias[idx_melhor]["data"].iloc[0].strftime("%d/%m/%Y")
    fig_dia    = viz.plot_comparacao_dia(res_h[idx_melhor], res_r[idx_melhor], data_str)

    # ── Cenários (reaproveita res_h/res_r já calculados) ──────────
    cenarios_idx = identificar_cenarios(dias)
    resultados_cenarios = {}
    for chave, idx in cenarios_idx.items():
        nome = _NOMES_CENARIOS[chave]
        h_h, h_r = res_h[idx], res_r[idx]
        c_h = sum(r["custo_r"] for r in h_h)
        c_r = sum(r["custo_r"] for r in h_r)
        resultados_cenarios[nome] = (h_h, h_r, c_h, c_r, idx)
    fig_cenarios = viz.plot_cenarios(dias, resultados_cenarios)

    # ── Visualizações operacionais ────────────────────────────────
    fig_maquinas   = viz.plot_uso_maquinas(dias)
    fig_mensal     = viz.plot_visao_mensal(dias, res_h, res_r)
    fig_comp_3vias = viz.plot_comparativo_3vias(dias, res_s, res_h, res_r)

    figuras = {
        "Aprendizado"       : fig_aprendizado,
        "Dia Destaque"      : fig_dia,
        "Cenários"          : fig_cenarios,
        "Uso das Máquinas"  : fig_maquinas,
        "Visão Mensal"      : fig_mensal,
        "Comparativo 3-vias": fig_comp_3vias,
    }
    dados_3 = {"dias": dias, "res_s": res_s, "res_h": res_h, "res_r": res_r}
    return {
        "figuras"            : figuras,
        "dados_3"            : dados_3,
        "res_r"              : res_r,
        "hist"               : hist,
        "idx_melhor"         : idx_melhor,
        "resultados_cenarios": resultados_cenarios,
    }


def main(replot: bool = False, web: bool = False, run_id: str | None = None) -> None:
    # ── 1. Dados ──────────────────────────────────────────────────
    print("Carregando dados...")
    DIAS, TARIFA = carregar_dados()
    print(f"  {len(DIAS)} dias carregados (Janeiro 2025 — Fazenda Buritis)")

    sol_med  = np.mean([d["solar_kw"].mean() for d in DIAS])
    cons_med = np.mean([(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).mean()
                        for d in DIAS])
    print(f"  Geração solar média : {sol_med:.2f} kW/h")
    print(f"  Consumo total médio : {cons_med:.2f} kW/h")

    # Importa o antigo outputs/models/ como run "legado", se ainda não houver runs
    if runs.migrar_legado():
        print("  Run legado importado de outputs/models/")

    # ── 2. Agentes + treino OU carregamento de run salvo ─────────
    AGENTES = construir_agentes(CONFIG)

    if replot or run_id:
        run_atual = run_id or runs.run_mais_recente()
        if run_atual is None:
            print("\n[erro] Nenhum run salvo encontrado. Rode sem --replot para treinar.")
            return
        print(f"\n[--replot] Pulando treinamento. Run selecionado: {run_atual}")
    else:
        print(f"\nIniciando treinamento ({CONFIG['n_episodios']} episódios × 24 timesteps)...\n")
        hist = treinar(DIAS, TARIFA, AGENTES, CONFIG)
        print("\nTreinamento concluído!")
        for ag in AGENTES.values():
            print(f"  {ag.nome:<16} | {ag.n_estados:>3} estados | {ag.n_updates:>6} updates | ε={ag.epsilon:.3f}")
        run_atual = runs.salvar_run(AGENTES, hist, fonte_dados=DATA_PATH.name)
        print(f"  Run salvo em: {runs.caminho_run(run_atual)}")

    # ── 3. Avaliação das baselines (independem do run) ────────────
    print("\nAvaliando em todos os dias (Sem Agente, Heurístico e RL)...")
    RES_S = [rodar_sem_agente(d, TARIFA) for d in DIAS]
    RES_H = [rodar_heuristico(d, TARIFA) for d in DIAS]
    CS, RS, VS, RWS = resumo_mes(RES_S)
    CH, RH, VH, RWH = resumo_mes(RES_H)

    # ── 4. Artefatos do run atual (RES_R + figuras + dados) ───────
    art   = construir_artefatos(run_atual, DIAS, TARIFA, RES_S, RES_H, CS, CH)
    RES_R = art["res_r"]
    CR, RR, VR, RWR = resumo_mes(RES_R)

    print(f"\n{'AVALIAÇÃO — MÉDIA DIÁRIA (Janeiro 2025)':^78}")
    print(f"{'═'*78}")
    print(f"  {'Métrica':<26} {'Sem Agente':>12} {'Heurístico':>12} {'RL':>10} {'Δ RL vs Sem':>12}")
    print(f"  {'─'*72}")
    print(f"  {'Custo (R$/dia)':<26} {CS:>12.2f} {CH:>12.2f} {CR:>10.2f} {delta_pct(CS, CR):>12}")
    print(f"  {'kWh da rede / dia':<26} {RS:>12.2f} {RH:>12.2f} {RR:>10.2f} {delta_pct(RS, RR):>12}")
    print(f"  {'Violações SOC / dia':<26} {VS:>12.2f} {VH:>12.2f} {VR:>10.2f}")
    print(f"  {'Reward médio / dia':<26} {RWS:>12.2f} {RWH:>12.2f} {RWR:>10.2f} {delta_pct(RWS, RWR):>12}")
    print(f"{'═'*78}")

    # ── 5. Tabela de cenários ─────────────────────────────────────
    ger_dia = [d["solar_kw"].sum() + d["eolico_kw"].sum() for d in DIAS]
    print(f"\n{'ANÁLISE DE CENÁRIOS':^68}")
    print(f"{'═'*68}")
    print(f"  {'Cenário':<18} {'Dia':>5} {'Geração':>10} {'Custo Heur.':>12} {'Custo RL':>10} {'Δ%':>7}")
    print(f"  {'─'*64}")
    for nome, (_, _, c_h, c_r, idx) in art["resultados_cenarios"].items():
        data_s = DIAS[idx]["data"].iloc[0].strftime("%d/%m")
        delt   = ((c_r - c_h) / c_h * 100) if c_h > 0 else 0
        print(f"  {nome:<18} {data_s:>5} {ger_dia[idx]:>9.1f} kWh {c_h:>10.2f} R$ {c_r:>8.2f} R$ {delt:>+6.1f} %")
    print(f"{'═'*68}")

    # ── 6. Relatório final ────────────────────────────────────────
    d_custo = ((CR - CH) / CH * 100)    if CH   != 0 else 0
    d_rede  = ((RR - RH) / RH * 100)    if RH   != 0 else 0
    d_rew   = ((RWR - RWH) / abs(RWH) * 100) if RWH != 0 else 0
    sinal_c = "ECONOMIA" if d_custo < 0 else "AUMENTO"
    sinal_r = "MELHORA"  if d_rew   > 0 else "PIORA"

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          RESUMO FINAL — SmartEnergy MAS PoC                 ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Run                  : {run_atual:<37}║")
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
    print("╚══════════════════════════════════════════════════════════════╝")

    # ── 7. Dashboard ──────────────────────────────────────────────
    runs_disp = runs.listar_runs()

    if web:
        from smarty_energy.dashboard_web import abrir_dashboard_web
        print("\nAbrindo dashboard web em localhost... (Ctrl+C para encerrar)")
        abrir_dashboard_web(
            DIAS, RES_S, RES_H, TARIFA,
            run_inicial=run_atual, runs_disp=runs_disp, res_r_inicial=RES_R,
        )
        return

    # Construtor usado pelo tkinter para reconstruir tudo ao trocar de run.
    def construtor(rid: str):
        a = construir_artefatos(rid, DIAS, TARIFA, RES_S, RES_H, CS, CH)
        return a["figuras"], a["dados_3"]

    print("\nAbrindo dashboard unificado... (feche a janela para encerrar)")
    abrir_dashboard(
        art["figuras"],
        dados_explorar={"dias": DIAS, "res_h": RES_H, "res_r": RES_R},
        dados_fonte=art["dados_3"],
        dados_maquina=art["dados_3"],
        construtor=construtor,
        runs_disp=runs_disp,
        run_inicial=run_atual,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartEnergy MAS — pipeline e dashboard.")
    parser.add_argument(
        "--replot",
        action="store_true",
        help="Pula o treinamento e reabre o run mais recente (ou o de --run).",
    )
    parser.add_argument(
        "--run",
        metavar="RUN_ID",
        default=None,
        help="Reabre um run específico de outputs/runs/ (implica --replot).",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Abre o dashboard web (Dash/Plotly) em localhost:8050 em vez do "
             "dashboard tkinter. Pode ser combinado com --replot/--run.",
    )
    args = parser.parse_args()
    main(replot=args.replot, web=args.web, run_id=args.run)
