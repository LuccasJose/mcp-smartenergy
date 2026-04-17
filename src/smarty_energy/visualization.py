"""Funções de visualização — todos os plots salvam em outputs/plots/.

Cada função monta uma `Figure` e a retorna. O dashboard (``dashboard.py``)
embute essas figuras em abas de uma única janela Tk. Chamar ``plt.show()``
fica a cargo do consumidor (dashboard ou script standalone).
"""

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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


def plot_curvas_aprendizado(rewards_hist: list, custos_hist: list) -> plt.Figure:
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

    c_ini = np.mean(custos_hist[:50])
    c_fim = np.mean(custos_hist[-50:])
    print(f"Custo médio (primeiros 50 ep.) : R${c_ini:.2f}")
    print(f"Custo médio (últimos  50 ep.)  : R${c_fim:.2f}")
    if c_ini > 0:
        print(f"Redução aprendida              : {((c_ini - c_fim) / c_ini * 100):.1f} %")
    return fig


def plot_comparacao_dia(
    hist_h: list[dict],
    hist_r: list[dict],
    data_str: str = "",
) -> plt.Figure:
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
    cores_cons = ["#27ae60", "#f1c40f", "#e67e22", "#d35400", "#c0392b", "#e74c3c", "#962d22", "#2c3e50"]
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
    return fig


def plot_cenarios(
    dias: list,
    resultados: dict[str, tuple],
) -> plt.Figure:
    """Plota comparação heurístico vs RL para os três cenários."""
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
    return fig


# ──────────────────────────────────────────────────────────────
# Novas visualizações: operação do mês por máquina e resumo mensal
# ──────────────────────────────────────────────────────────────

_MAQUINAS = [
    ("pivo_kw",     "Pivô (irrigação)",  "YlOrRd"),
    ("captacao_kw", "Bomba de Captação", "Blues"),
    ("sede_kw",     "Sede / Escritório", "Purples"),
    ("silo_kw",     "Silo / Secador",    "Oranges"),
    ("solar_kw",    "Geração Solar",     "YlOrBr"),
    ("eolico_kw",   "Geração Eólica",    "Greens"),
]


def plot_uso_maquinas(dias: list[pd.DataFrame]) -> plt.Figure:
    """Heatmap (dia × hora) para cada máquina/fonte.

    Cada célula é o consumo/geração naquela hora daquele dia em kW.
    Permite ver de relance quando cada equipamento é usado ao longo do mês
    e quanto cada dia contrasta com os demais.
    """
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle(
        "Uso Operacional por Máquina — Janeiro 2025\n"
        "Linha = dia do mês, coluna = hora (0–23), cor = kW na hora",
        fontsize=13, fontweight="bold",
    )

    n_dias = len(dias)
    datas_labels = [d["data"].iloc[0].strftime("%d") for d in dias]

    for ax, (col, titulo, cmap) in zip(axes.flat, _MAQUINAS):
        matriz = np.array([d[col].values for d in dias])  # (n_dias, 24)
        im = ax.imshow(matriz, aspect="auto", cmap=cmap, interpolation="nearest")

        total_mes = matriz.sum()
        pico      = matriz.max()
        media_h   = matriz.mean()
        ax.set_title(
            f"{titulo}\nTotal mês: {total_mes:.0f} kWh  |  Pico: {pico:.1f} kW  |  Média: {media_h:.2f} kW",
            fontsize=10,
        )

        ax.set_xlabel("Hora")
        ax.set_ylabel("Dia")
        ax.set_xticks(range(0, 24, 3))
        step = max(1, n_dias // 10)
        ax.set_yticks(range(0, n_dias, step))
        ax.set_yticklabels(datas_labels[::step], fontsize=7)
        ax.axvspan(17.5, 20.5, alpha=0.08, color="white")  # sutil nos heatmaps
        fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="kW")

    plt.tight_layout()
    _save(fig, "uso_maquinas.png")
    return fig


def plot_visao_mensal(
    dias: list[pd.DataFrame],
    res_h: list[list[dict]],
    res_r: list[list[dict]],
) -> plt.Figure:
    """Resumo do mês: custo, rede e bateria por dia.

    Quatro painéis:
      1. Custo diário (Heurístico vs RL) — barras lado a lado
      2. kWh importados da rede por dia
      3. SOC médio da bateria por dia
      4. Geração total por dia (solar + eólico) com classificação de cenário
    """
    n = len(dias)
    dias_x = np.arange(n)
    labels = [d["data"].iloc[0].strftime("%d") for d in dias]

    custo_h = np.array([sum(h["custo_r"]  for h in hist) for hist in res_h])
    custo_r = np.array([sum(h["custo_r"]  for h in hist) for hist in res_r])
    rede_h  = np.array([sum(h["rede_kwh"] for h in hist) for hist in res_h])
    rede_r  = np.array([sum(h["rede_kwh"] for h in hist) for hist in res_r])
    soc_h   = np.array([np.mean([h["soc"] for h in hist]) for hist in res_h])
    soc_r   = np.array([np.mean([h["soc"] for h in hist]) for hist in res_r])
    ger_dia = np.array([d["solar_kw"].sum() + d["eolico_kw"].sum() for d in dias])
    cons_dia = np.array([(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).sum()
                         for d in dias])

    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    fig.suptitle("Visão Mensal — Operação Dia a Dia (Janeiro 2025)",
                 fontsize=13, fontweight="bold")

    # 1. Custo por dia
    ax = axes[0, 0]
    w = 0.4
    ax.bar(dias_x - w/2, custo_h, w, color=_COR_H, alpha=0.85, label="Heurístico")
    ax.bar(dias_x + w/2, custo_r, w, color=_COR_R, alpha=0.85, label="RL")
    total_h, total_r = custo_h.sum(), custo_r.sum()
    delt = ((total_r - total_h) / total_h * 100) if total_h > 0 else 0
    ax.set_title(f"Custo Diário (R$)  |  Total mês: R${total_h:.0f} → R${total_r:.0f}  ({delt:+.1f} %)")
    ax.set_xticks(dias_x[::2]); ax.set_xticklabels(labels[::2], fontsize=7)
    ax.set_xlabel("Dia"); ax.set_ylabel("R$")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    # 2. kWh rede por dia
    ax = axes[0, 1]
    ax.bar(dias_x - w/2, rede_h, w, color=_COR_H, alpha=0.85, label="Heurístico")
    ax.bar(dias_x + w/2, rede_r, w, color=_COR_R, alpha=0.85, label="RL")
    ax.set_title(f"Energia Importada da Rede (kWh/dia)  |  Média: {rede_h.mean():.1f} → {rede_r.mean():.1f} kWh")
    ax.set_xticks(dias_x[::2]); ax.set_xticklabels(labels[::2], fontsize=7)
    ax.set_xlabel("Dia"); ax.set_ylabel("kWh")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    # 3. SOC médio por dia
    ax = axes[1, 0]
    ax.plot(dias_x, soc_h, "o-", color=_COR_H, label="Heurístico", ms=4)
    ax.plot(dias_x, soc_r, "s-", color=_COR_R, label="RL", ms=4)
    ax.axhline(CONFIG["soc_min_pct"], color="red",  ls="--", alpha=0.5, label="SOC crítico")
    ax.axhline(80, color="blue", ls="--", alpha=0.3, label="SOC ótimo")
    ax.set_title("SOC Médio da Bateria por Dia (%)")
    ax.set_xticks(dias_x[::2]); ax.set_xticklabels(labels[::2], fontsize=7)
    ax.set_xlabel("Dia"); ax.set_ylabel("SOC (%)"); ax.set_ylim(0, 105)
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # 4. Geração vs consumo por dia, com marcadores de cenário
    ax = axes[1, 1]
    ax.bar(dias_x, ger_dia, color="gold", alpha=0.75, label="Geração (solar+eólico)")
    ax.plot(dias_x, cons_dia, "o-", color="#2c3e50", lw=1.6, ms=4, label="Consumo total")
    # Marca os 3 cenários
    i_nub  = int(np.argmin(ger_dia))
    i_ens  = int(np.argmax(ger_dia))
    i_alto = int(np.argmax(cons_dia / np.maximum(ger_dia, 0.1)))
    for i, rot, cor in [(i_nub, "Nublado", "#34495e"),
                         (i_ens, "Ensolarado", "#f39c12"),
                         (i_alto, "Alto consumo", "#c0392b")]:
        ax.annotate(rot, xy=(i, max(ger_dia[i], cons_dia[i])),
                    xytext=(0, 12), textcoords="offset points",
                    ha="center", fontsize=8, color=cor, fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color=cor, alpha=0.6))
    ax.set_title("Geração e Consumo Totais por Dia (kWh)")
    ax.set_xticks(dias_x[::2]); ax.set_xticklabels(labels[::2], fontsize=7)
    ax.set_xlabel("Dia"); ax.set_ylabel("kWh")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    _save(fig, "visao_mensal.png")
    return fig
