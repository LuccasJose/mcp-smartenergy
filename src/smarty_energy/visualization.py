"""Funções de visualização — todos os plots salvam em outputs/plots/."""

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from .config import CONFIG, OUTPUT_DIR

_PLOTS_DIR = OUTPUT_DIR / "plots"
_COR_H = "#e74c3c"
_COR_R = "#27ae60"


def _save(fig: plt.Figure, nome: str) -> None:
    _PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _PLOTS_DIR / nome
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Plot salvo: {path}")


def _media_movel(arr: list, w: int = 50) -> np.ndarray:
    return np.convolve(arr, np.ones(w) / w, mode="valid")


def plot_curvas_aprendizado(rewards_hist: list, custos_hist: list) -> None:
    """Plota reward e custo ao longo dos episódios de treinamento."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4))
    fig.suptitle("Curva de Aprendizado — Q-Learning Cooperativo", fontsize=13, fontweight="bold")

    ax1.plot(rewards_hist, alpha=0.2, color="steelblue", lw=0.8)
    ax1.plot(_media_movel(rewards_hist), color="steelblue", lw=2.2, label="Média móvel (50 ep.)")
    ax1.set_xlabel("Episódio"); ax1.set_ylabel("Reward total do dia")
    ax1.set_title("Reward por Episódio"); ax1.legend(); ax1.grid(alpha=0.3)

    ax2.plot(custos_hist, alpha=0.2, color="tomato", lw=0.8)
    ax2.plot(_media_movel(custos_hist), color="tomato", lw=2.2, label="Média móvel (50 ep.)")
    ax2.set_xlabel("Episódio"); ax2.set_ylabel("Custo (R$)")
    ax2.set_title("Custo de Energia por Episódio"); ax2.legend(); ax2.grid(alpha=0.3)

    plt.tight_layout()
    _save(fig, "curva_aprendizado.png")
    plt.show()

    c_ini = np.mean(custos_hist[:50])
    c_fim = np.mean(custos_hist[-50:])
    print(f"Custo médio (primeiros 50 ep.) : R${c_ini:.2f}")
    print(f"Custo médio (últimos  50 ep.)  : R${c_fim:.2f}")
    if c_ini > 0:
        print(f"Redução aprendida              : {((c_ini - c_fim) / c_ini * 100):.1f} %")


def plot_comparacao_dia(
    hist_h: list[dict],
    hist_r: list[dict],
    data_str: str = "",
) -> None:
    """Plota comparação detalhada entre heurístico e RL para um dia."""
    horas = list(range(24))
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    titulo = f"Heurístico vs RL  —  {data_str}  (maior diferença de custo)" if data_str else "Heurístico vs RL"
    fig.suptitle(titulo, fontsize=13, fontweight="bold")

    # 1. Custo por hora
    ax = axes[0, 0]
    ax.bar([h - 0.2 for h in horas], [r["custo_r"] for r in hist_h], 0.4,
           label="Heurístico", color=_COR_H, alpha=0.85)
    ax.bar([h + 0.2 for h in horas], [r["custo_r"] for r in hist_r], 0.4,
           label="RL", color=_COR_R, alpha=0.85)
    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange", label="Pico tarifário")
    ch_ = sum(r["custo_r"] for r in hist_h)
    cr_ = sum(r["custo_r"] for r in hist_r)
    ax.set_title(f"Custo por Hora  |  Heur R${ch_:.2f}  →  RL R${cr_:.2f}  ({((cr_-ch_)/ch_*100):+.1f} %)")
    ax.set_xlabel("Hora"); ax.set_ylabel("R$"); ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    # 2. SOC da bateria
    ax = axes[0, 1]
    ax.plot(horas, [r["soc"] for r in hist_h], "o-", color=_COR_H, label="Heurístico", ms=4)
    ax.plot(horas, [r["soc"] for r in hist_r], "s-", color=_COR_R, label="RL", ms=4)
    ax.axhline(CONFIG["soc_min_pct"], color="red",  ls="--", alpha=0.6,
               label=f"SOC crítico ({CONFIG['soc_min_pct']} %)")
    ax.axhline(80, color="blue", ls="--", alpha=0.4, label="SOC ótimo (80 %)")
    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange")
    ax.set_title("Estado de Carga da Bateria (%)"); ax.set_xlabel("Hora"); ax.set_ylabel("SOC (%)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3); ax.set_ylim(0, 105)

    # 3. Geração vs Consumo
    ax = axes[1, 0]
    ger_vals = [r["geracao_kw"] for r in hist_r]
    ax.fill_between(horas, ger_vals, alpha=0.3, color="gold", label="Geração (solar+eólico)")
    ax.plot(horas, [r["consumo_kw"] for r in hist_h], "o-", color=_COR_H, label="Consumo Heurístico", ms=4)
    ax.plot(horas, [r["consumo_kw"] for r in hist_r], "s-", color=_COR_R, label="Consumo RL", ms=4)
    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange")
    ax.set_title("Geração vs Consumo (kW)"); ax.set_xlabel("Hora"); ax.set_ylabel("kW")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # 4. Mapa de decisões do RL
    ax = axes[1, 1]
    cores_arm  = ["#3498db", "#95a5a6", "#e67e22"]
    cores_cons = ["#27ae60", "#f1c40f", "#e67e22", "#e74c3c"]
    cores_ger  = ["#e74c3c", "#e67e22", "#27ae60"]

    for h in range(24):
        ax.barh(2.5, 1, left=h, height=0.75, color=cores_arm[hist_r[h]["a_arm"]],  alpha=0.9)
        ax.barh(1.5, 1, left=h, height=0.75, color=cores_cons[hist_r[h]["a_cons"]], alpha=0.9)
        ax.barh(0.5, 1, left=h, height=0.75, color=cores_ger[hist_r[h]["a_ger"]],  alpha=0.9)

    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange")
    ax.set_yticks([0.5, 1.5, 2.5])
    ax.set_yticklabels(["Gerente", "Consumo", "Armaz."])
    ax.set_xlabel("Hora"); ax.set_title("Decisões dos Agentes RL por Hora"); ax.set_xlim(0, 24)
    leg_arm = [mpatches.Patch(color=c, label=l) for c, l in
               zip(cores_arm, ["Carregar", "Manter", "Descarregar"])]
    ax.legend(handles=leg_arm, loc="upper left", fontsize=7, title="Armaz.", title_fontsize=7)

    plt.tight_layout()
    _save(fig, "comparativo_dia.png")
    plt.show()


def plot_cenarios(
    dias: list,
    resultados: dict[str, tuple],
) -> None:
    """Plota comparação heurístico vs RL para os três cenários.

    Args:
        dias       : lista de DataFrames diários
        resultados : dict {nome_cenario: (hist_h, hist_r, custo_h, custo_r, idx)}
    """
    horas = list(range(24))
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle("Cenários: Heurístico vs RL", fontsize=14, fontweight="bold")

    for row, (nome, (h_h, h_r, c_h, c_r, idx)) in enumerate(resultados.items()):
        data_s = dias[idx]["data"].iloc[0].strftime("%d/%m/%Y")
        delt   = ((c_r - c_h) / c_h * 100) if c_h > 0 else 0

        ax1 = axes[row, 0]
        ax1.bar([h - 0.2 for h in horas], [r["custo_r"] for r in h_h], 0.4,
                color=_COR_H, alpha=0.85, label="Heurístico")
        ax1.bar([h + 0.2 for h in horas], [r["custo_r"] for r in h_r], 0.4,
                color=_COR_R, alpha=0.85, label="RL")
        ax1.axvspan(17.5, 20.5, alpha=0.12, color="orange")
        ax1.set_title(f"{nome}  {data_s}  |  R${c_h:.2f} → R${c_r:.2f}  ({delt:+.1f} %)")
        ax1.set_ylabel("R$"); ax1.legend(fontsize=7); ax1.grid(axis="y", alpha=0.3)

        ax2 = axes[row, 1]
        ax2.plot(horas, [r["soc"] for r in h_h], "o-", color=_COR_H, label="Heurístico", ms=3)
        ax2.plot(horas, [r["soc"] for r in h_r], "s-", color=_COR_R, label="RL", ms=3)
        ax2.axhline(CONFIG["soc_min_pct"], color="red",  ls="--", alpha=0.5)
        ax2.axhline(80,                    color="blue", ls="--", alpha=0.3)
        ax2.axvspan(17.5, 20.5, alpha=0.12, color="orange")
        ax2.set_title(f"SOC da Bateria — {nome}"); ax2.set_ylabel("SOC (%)"); ax2.set_ylim(0, 105)
        ax2.legend(fontsize=7); ax2.grid(alpha=0.3)
        if row == 2:
            ax1.set_xlabel("Hora"); ax2.set_xlabel("Hora")

    plt.tight_layout()
    _save(fig, "cenarios.png")
    plt.show()
