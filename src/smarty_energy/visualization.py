"""Funções de visualização — todos os plots salvam em outputs/plots/.

Cada função monta uma `Figure` e a retorna. O dashboard (``dashboard.py``)
embute essas figuras em abas de uma única janela Tk. Chamar ``plt.show()``
fica a cargo do consumidor (dashboard ou script standalone).
"""

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import CONFIG, OUTPUT_DIR

_PLOTS_DIR = OUTPUT_DIR / "plots"
_COR_H = "#e74c3c"
_COR_R = "#27ae60"

# Cores para as decisões dos agentes (reutilizadas em plot_comparacao_dia e plot_explorar_dia)
_CORES_ARM  = ["#3498db", "#95a5a6", "#f1c40f", "#e67e22", "#c0392b"]
_CORES_CONS = ["#27ae60", "#f1c40f", "#e67e22", "#d35400", "#c0392b", "#e74c3c", "#962d22", "#2c3e50"]
_CORES_GER  = ["#e74c3c", "#e67e22", "#27ae60"]


def _save(fig: plt.Figure, nome: str) -> None:
    _PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _PLOTS_DIR / nome
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Plot salvo: {path}")


def _media_movel(arr: list, w: int | None = None) -> np.ndarray:
    """Média móvel com janela adaptativa ao tamanho do histórico."""
    if w is None:
        w = max(50, len(arr) // 200)   # ~500 em 100k eps; 50 em 10k eps
    w = max(1, min(w, len(arr)))
    return np.convolve(arr, np.ones(w) / w, mode="valid")


def plot_curvas_aprendizado(
    rewards_hist: list,
    custos_hist: list,
    eps_hist: list | None = None,
    custo_baseline_sem: float | None = None,
    custo_baseline_heur: float | None = None,
) -> plt.Figure:
    """Plota reward, custo e (opcional) epsilon ao longo do treinamento.

    Args:
        rewards_hist        : reward total por episódio
        custos_hist         : custo (R$) por episódio
        eps_hist            : epsilon por episódio (opcional). Se fornecido,
                              adiciona um terceiro painel com o decaimento.
        custo_baseline_sem  : custo médio diário do baseline "Sem Agente"
                              — desenhado como linha horizontal de referência.
        custo_baseline_heur : custo médio diário do Heurístico — idem.
    """
    n_ep  = len(rewards_hist)
    # Subamostragem do scatter de fundo: limita a ~5000 pontos para não saturar
    step  = max(1, n_ep // 5000)
    x_sub = np.arange(0, n_ep, step)
    w_med = max(50, n_ep // 200)

    n_paineis = 3 if eps_hist is not None else 2
    fig, axes = plt.subplots(1, n_paineis, figsize=(6 * n_paineis, 4))
    if n_paineis == 2:
        ax1, ax2 = axes
    else:
        ax1, ax2, ax3 = axes
    fig.suptitle(
        f"Curva de Aprendizado — Q-Learning Cooperativo  ({n_ep:,} episódios)",
        fontsize=13, fontweight="bold",
    )

    # Reward por episódio
    ax1.plot(x_sub, np.array(rewards_hist)[x_sub], alpha=0.2, color="steelblue", lw=0.6)
    rewards_smooth = _media_movel(rewards_hist, w_med)
    ax1.plot(np.arange(len(rewards_smooth)) + w_med // 2,
             rewards_smooth, color="steelblue", lw=2.2,
             label=f"Média móvel ({w_med} ep.)")
    ax1.set_xlabel("Episódio"); ax1.set_ylabel("Reward total do dia")
    ax1.set_title("Reward por Episódio"); ax1.legend(fontsize=9); ax1.grid(alpha=0.3)

    # Custo por episódio com baselines horizontais
    ax2.plot(x_sub, np.array(custos_hist)[x_sub], alpha=0.2, color="tomato", lw=0.6)
    custos_smooth = _media_movel(custos_hist, w_med)
    ax2.plot(np.arange(len(custos_smooth)) + w_med // 2,
             custos_smooth, color="tomato", lw=2.2,
             label=f"Média móvel ({w_med} ep.)")
    if custo_baseline_sem is not None:
        ax2.axhline(custo_baseline_sem, color="#7f8c8d", ls="--", lw=1.5,
                    label=f"Sem Agente: R${custo_baseline_sem:.2f}")
    if custo_baseline_heur is not None:
        ax2.axhline(custo_baseline_heur, color="#e74c3c", ls=":", lw=1.5,
                    label=f"Heurístico: R${custo_baseline_heur:.2f}")
    ax2.set_xlabel("Episódio"); ax2.set_ylabel("Custo (R$/dia)")
    ax2.set_title("Custo de Energia por Episódio"); ax2.legend(fontsize=8); ax2.grid(alpha=0.3)

    # Decaimento do epsilon
    if eps_hist is not None:
        ax3.plot(x_sub, np.array(eps_hist)[x_sub], color="#8e44ad", lw=1.6)
        ax3.set_xlabel("Episódio"); ax3.set_ylabel("ε (taxa de exploração)")
        ax3.set_title("Decaimento do Epsilon"); ax3.grid(alpha=0.3)
        ax3.set_ylim(0, 1.05)

    plt.tight_layout()
    _save(fig, "curva_aprendizado.png")

    # Estatísticas — janela adaptativa para inicial vs final
    w_stat = max(50, n_ep // 100)
    c_ini = float(np.mean(custos_hist[:w_stat]))
    c_fim = float(np.mean(custos_hist[-w_stat:]))
    print(f"Custo médio (primeiros {w_stat} ep.) : R${c_ini:.2f}")
    print(f"Custo médio (últimos  {w_stat} ep.)  : R${c_fim:.2f}")
    if c_ini > 0:
        print(f"Redução aprendida                 : {((c_ini - c_fim) / c_ini * 100):.1f} %")
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
    for h in range(24):
        ax.barh(2.5, 1, left=h, height=0.75, color=_CORES_ARM[hist_r[h]["a_arm"]],  alpha=0.9)
        ax.barh(1.5, 1, left=h, height=0.75, color=_CORES_CONS[hist_r[h]["a_cons"]], alpha=0.9)
        ax.barh(0.5, 1, left=h, height=0.75, color=_CORES_GER[hist_r[h]["a_ger"]],  alpha=0.9)

    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange")
    ax.set_yticks([0.5, 1.5, 2.5])
    ax.set_yticklabels(["Gerente", "Consumo", "Armaz."])
    ax.set_xlabel("Hora"); ax.set_title("Decisões dos Agentes RL por Hora"); ax.set_xlim(0, 24)
    leg_arm = [mpatches.Patch(color=c, label=l) for c, l in
               zip(_CORES_ARM, ["Carregar", "Manter", "Desc. 25%", "Desc. 50%", "Desc. 100%"]) ]
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


# ──────────────────────────────────────────────────────────────
# Aba interativa: explorar dia individual
# ──────────────────────────────────────────────────────────────

def plot_explorar_dia(
    fig: plt.Figure,
    dados_dia: pd.DataFrame,
    hist_h: list[dict],
    hist_r: list[dict],
    data_str: str = "",
    todos_dias: list | None = None,
    filtro_maquina: str = "Todas",
) -> None:
    """Desenha painéis detalhados de um dia na Figure fornecida (in-place).

    Usado pela aba interativa do dashboard — não salva arquivo.

    Args:
        todos_dias : lista com todos os DataFrames do mês, usada para
                     calcular médias de referência no perfil do dia.
    """
    fig.clf()
    axes = fig.subplots(3, 2)
    horas = list(range(24))

    titulo = f"Explorar Dia — {data_str}" if data_str else "Explorar Dia"
    fig.suptitle(titulo, fontsize=13, fontweight="bold")

    # ── Métricas comuns ───────────────────────────────────────────
    ch = sum(r["custo_r"] for r in hist_h)
    cr = sum(r["custo_r"] for r in hist_r)
    delt = ((cr - ch) / ch * 100) if ch > 0 else 0
    rede_h = sum(r["rede_kwh"] for r in hist_h)
    rede_r = sum(r["rede_kwh"] for r in hist_r)
    solar_dia  = dados_dia["solar_kw"].sum()
    eolico_dia = dados_dia["eolico_kw"].sum()
    ger_total  = solar_dia + eolico_dia
    cons_total = (dados_dia["pivo_kw"] + dados_dia["captacao_kw"]
                  + dados_dia["sede_kw"] + dados_dia["silo_kw"]).sum()

    # ── 1. Custo por hora ─────────────────────────────────────────
    ax = axes[0, 0]
    ax.bar([h - 0.2 for h in horas], [r["custo_r"] for r in hist_h], 0.4,
           label="Heurístico", color=_COR_H, alpha=0.85)
    ax.bar([h + 0.2 for h in horas], [r["custo_r"] for r in hist_r], 0.4,
           label="RL", color=_COR_R, alpha=0.85)
    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange", label="Pico tarifário")
    ax.set_title(f"Custo por Hora  |  Heur R${ch:.2f}  →  RL R${cr:.2f}  ({delt:+.1f} %)")
    ax.set_xlabel("Hora"); ax.set_ylabel("R$")
    ax.set_xticks(range(24)); ax.set_xticklabels(range(24), fontsize=8)
    ax.set_xlim(-0.6, 23.6)
    ax.grid(axis="x", which="major", alpha=0.15, linestyle=":")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8)

    # ── 2. Geração vs Consumo ─────────────────────────────────────
    ax = axes[0, 1]
    ger_vals = [r["geracao_kw"] for r in hist_r]
    ax.fill_between(horas, ger_vals, alpha=0.3, color="gold", label="Geração (solar+eólico)")
    ax.plot(horas, [r["consumo_kw"] for r in hist_h], "o-", color=_COR_H, label="Consumo Heurístico", ms=4)
    ax.plot(horas, [r["consumo_kw"] for r in hist_r], "s-", color=_COR_R, label="Consumo RL", ms=4)
    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange")
    ax.set_title("Geração vs Consumo (kW)")
    ax.set_xlabel("Hora"); ax.set_ylabel("kW")
    ax.set_xticks(range(0, 24, 2)); ax.set_xticklabels(range(0, 24, 2), fontsize=8)
    ax.set_xlim(-0.6, 23.6)
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # ── 3. Uso REAL das máquinas pelo RL (stacked bars) ───────────
    # Mostra o consumo que o RL EFETIVAMENTE deixou rodar; a linha cinza
    # tracejada por trás é a demanda histórica (o que a fazenda "queria").
    ax = axes[1, 0]
    # Cada entrada: (label, cor, [cols_demanda], [cols_real])
    _maq_stack = [
        ("Pivô",            "#e74c3c", ["pivo_kw"],            ["pivo_kw_consumido"]),
        ("Bomba Captação",  "#3498db", ["captacao_kw"],        ["captacao_kw_consumido"]),
        ("Sede/Escritório", "#9b59b6", ["sede_kw"],            ["sede_kw_consumido"]),
        ("Secadora/silo",   "#d35400", ["silo_kw", "secador_kw"],
                                       ["silo_kw_consumido", "secador_kw_consumido"]),
    ]
    if filtro_maquina != "Todas":
        _maq_stack = [m for m in _maq_stack if m[0] == filtro_maquina]

    # Demanda histórica empilhada como contorno fantasma
    demanda_total = np.zeros(24)
    for _, _, cols_dem, _ in _maq_stack:
        for col in cols_dem:
            if col in dados_dia.columns:
                demanda_total += dados_dia[col].to_numpy(dtype=float)
    ax.step(np.arange(24) + 0.5, demanda_total, where="mid", color="#7f8c8d",
            ls="--", lw=1.2, alpha=0.85, label="Demanda histórica")

    # Consumo realizado pelo RL (stacked)
    bottom = np.zeros(24)
    sede_bottom = None
    for label, cor, _, cols_real in _maq_stack:
        vals = np.zeros(24)
        for col in cols_real:
            vals += np.array([h.get(col, 0.0) for h in hist_r])
        ax.bar(horas, vals, bottom=bottom, label=label, color=cor, alpha=0.85, width=0.8)
        if label == "Sede/Escritório":
            sede_bottom = bottom.copy()
            sede_top = bottom + vals
        bottom += vals
    ax.axvspan(17.5, 20.5, alpha=0.1, color="orange")

    # Marcador de eco-mode: estrela acima das barras de sede nas horas com redução
    eco_horas = [h for h, reg in enumerate(hist_r) if reg.get("sede_eco")]
    if eco_horas and sede_bottom is not None:
        topo_max = float(np.max(bottom)) if bottom.size else 1.0
        offset = topo_max * 0.04 + 0.3
        eco_y = [sede_top[h] + offset for h in eco_horas]
        ax.scatter(eco_horas, eco_y, marker="*", color="#16a085",
                   s=110, zorder=5, edgecolors="white", linewidths=0.5,
                   label="Sede em eco-mode (-20%)")

    sub = f" — {filtro_maquina}" if filtro_maquina != "Todas" else ""
    ax.set_title(f"Consumo REALIZADO pelo RL (kW){sub}  —  cinza tracejado = demanda histórica")
    ax.set_xlabel("Hora"); ax.set_ylabel("kW")
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24), fontsize=8)
    ax.set_xlim(-0.6, 23.6)
    ax.grid(axis="x", which="major", alpha=0.15, linestyle=":")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=7, loc="upper left")

    # Métrica de confirmação: bomba/pivô/secador no pico (h18-20)
    # Colocada DENTRO do painel (canto sup. direito) com caixa para evitar
    # colisão com o título.
    pico_h     = list(range(18, 21))
    bomba_pico = sum(hist_r[h]["captacao_kw_consumido"] for h in pico_h)
    pivo_pico  = sum(hist_r[h]["pivo_kw_consumido"]    for h in pico_h)
    sec_pico   = sum(hist_r[h]["secador_kw_consumido"] for h in pico_h)
    badge = (
        f"Em pico (18-20h):\n"
        f"  bomba   = {bomba_pico:5.1f} kWh\n"
        f"  pivô    = {pivo_pico:5.1f} kWh\n"
        f"  secador = {sec_pico:5.1f} kWh"
    )
    cor_badge = "#27ae60" if (bomba_pico + pivo_pico + sec_pico) < 0.5 else "#c0392b"
    ax.text(
        0.985, 0.97, badge, transform=ax.transAxes,
        ha="right", va="top", fontsize=8, fontweight="bold",
        color=cor_badge, fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor=cor_badge, linewidth=1.2, alpha=0.92),
    )

    # ── 4. Perfil do dia ──────────────────────────────────────────
    ax = axes[1, 1]
    ax.axis("off")

    # Calcula médias de referência
    if todos_dias:
        media_solar  = np.mean([d["solar_kw"].sum()  for d in todos_dias])
        media_eolico = np.mean([d["eolico_kw"].sum() for d in todos_dias])
        media_cons   = np.mean([(d["pivo_kw"] + d["captacao_kw"]
                                 + d["sede_kw"] + d["silo_kw"]).sum() for d in todos_dias])
    else:
        media_solar  = solar_dia
        media_eolico = eolico_dia
        media_cons   = cons_total

    pct_solar  = ((solar_dia  - media_solar)  / media_solar  * 100) if media_solar  > 0 else 0
    pct_eolico = ((eolico_dia - media_eolico) / media_eolico * 100) if media_eolico > 0 else 0
    pct_cons   = ((cons_total - media_cons)   / media_cons   * 100) if media_cons   > 0 else 0
    balanco    = ger_total - cons_total

    # Classificação do dia
    if pct_solar < -30:
        class_label = "NUBLADO"
        class_cor   = "#7f8c8d"
        class_desc  = "Baixa geração solar"
    elif pct_solar > 25:
        class_label = "ENSOLARADO"
        class_cor   = "#f39c12"
        class_desc  = "Alta geração solar"
    elif pct_cons > 25:
        class_label = "ALTO CONSUMO"
        class_cor   = "#e74c3c"
        class_desc  = "Demanda elevada"
    elif pct_cons < -25:
        class_label = "BAIXO CONSUMO"
        class_cor   = "#27ae60"
        class_desc  = "Demanda reduzida"
    else:
        class_label = "EQUILIBRADO"
        class_cor   = "#2980b9"
        class_desc  = "Dia dentro da média"

    # Badge de classificação
    ax.text(0.5, 0.92, class_label, transform=ax.transAxes, fontsize=16,
            fontweight="bold", ha="center", va="top", color="white",
            bbox=dict(boxstyle="round,pad=0.4", facecolor=class_cor, alpha=0.9))
    ax.text(0.5, 0.76, class_desc, transform=ax.transAxes, fontsize=10,
            ha="center", va="top", color=class_cor, style="italic")

    # Comparação com a média do mês (mini gráfico de barras horizontal)
    metricas  = ["Solar",    "Eólico",    "Consumo"]
    pcts      = [pct_solar,  pct_eolico,  pct_cons]
    cores_bar = ["#f39c12" if p >= 0 else "#95a5a6" for p in pcts[:2]] + \
                ["#e74c3c" if pct_cons > 0 else "#27ae60"]
    y_pos = [0.58, 0.44, 0.30]
    for met, pct, cor, y in zip(metricas, pcts, cores_bar, y_pos):
        bar_w = min(abs(pct) / 100 * 0.4, 0.4)
        x0 = 0.5 if pct >= 0 else 0.5 - bar_w
        ax.add_patch(
            __import__("matplotlib.patches", fromlist=["FancyBboxPatch"]).FancyBboxPatch(
                (x0, y - 0.04), bar_w, 0.08,
                boxstyle="round,pad=0.005", facecolor=cor, alpha=0.75,
                transform=ax.transAxes, clip_on=False,
            )
        )
        ax.text(0.5, y, f"{met}: {pct:+.1f} % vs média", transform=ax.transAxes,
                fontsize=9, ha="center", va="center", color="black")
    ax.plot([0.5, 0.5], [0.28, 0.62], color="#bdc3c7", lw=1, transform=ax.transAxes)
    ax.text(0.5, 0.16, f"Balanço energético: {balanco:+.1f} kWh",
            transform=ax.transAxes, fontsize=9, ha="center", va="top",
            color="#2c3e50", fontweight="bold")
    ax.set_title("Perfil do Dia  (vs média do mês)")

    # ── 5. Resumo estatístico ─────────────────────────────────────
    ax = axes[2, 0]
    ax.axis("off")
    resumo = (
        f"RESUMO DO DIA\n"
        f"{'─' * 40}\n"
        f"Custo Heurístico : R$ {ch:.2f}\n"
        f"Custo RL         : R$ {cr:.2f}  ({delt:+.1f} %)\n"
        f"{'─' * 40}\n"
        f"Rede Heurístico  : {rede_h:.2f} kWh\n"
        f"Rede RL          : {rede_r:.2f} kWh\n"
        f"{'─' * 40}\n"
        f"Geração solar    : {solar_dia:.1f} kWh  ({pct_solar:+.1f} % vs média)\n"
        f"Geração eólica   : {eolico_dia:.1f} kWh  ({pct_eolico:+.1f} % vs média)\n"
        f"Geração total    : {ger_total:.1f} kWh\n"
        f"{'─' * 40}\n"
        f"Consumo total    : {cons_total:.1f} kWh  ({pct_cons:+.1f} % vs média)\n"
        f"Balanço          : {balanco:+.1f} kWh"
    )
    ax.text(0.05, 0.95, resumo, transform=ax.transAxes, fontsize=10,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f0f0f0", alpha=0.8))

    # ── 6. Estado de Carga da bateria (SOC) ───────────────────────
    ax = axes[2, 1]
    ax.plot(horas, [r["soc"] for r in hist_h], "o-", color=_COR_H, label="Heurístico", ms=4)
    ax.plot(horas, [r["soc"] for r in hist_r], "s-", color=_COR_R, label="RL", ms=4)
    ax.axhline(CONFIG["soc_min_pct"], color="red",  ls="--", alpha=0.6,
               label=f"SOC crítico ({CONFIG['soc_min_pct']} %)")
    ax.axhline(80, color="blue", ls="--", alpha=0.4, label="SOC ótimo (80 %)")
    ax.axvspan(17.5, 20.5, alpha=0.12, color="orange", label="Pico tarifário")
    ax.set_title("Estado de Carga da Bateria (%)")
    ax.set_xlabel("Hora"); ax.set_ylabel("SOC (%)")
    ax.legend(fontsize=8, loc="lower right"); ax.grid(alpha=0.3); ax.set_ylim(0, 105)

    fig.tight_layout()


# ──────────────────────────────────────────────────────────────
# Comparativo 3-vias: Sem Agente vs Heurístico vs RL
# ──────────────────────────────────────────────────────────────

_COR_S = "#7f8c8d"  # cinza para baseline "sem agente"


def plot_comparativo_3vias(
    dias: list[pd.DataFrame],
    res_s: list[list[dict]],
    res_h: list[list[dict]],
    res_r: list[list[dict]],
) -> plt.Figure:
    """Compara três estratégias: Sem Agente (baseline) vs Heurístico vs RL.

    Quatro painéis:
      1. Custo diário (barras agrupadas)
      2. kWh da rede por dia
      3. Custo mensal total (barras com Δ% vs baseline)
      4. Consumo total por máquina (mensal) — idêntico entre estratégias
         quando não há corte, mas diferente quando RL/Heur cortam cargas.
    """
    n = len(dias)
    dias_x = np.arange(n)
    labels = [d["data"].iloc[0].strftime("%d") for d in dias]

    custo_s = np.array([sum(h["custo_r"]  for h in hist) for hist in res_s])
    custo_h = np.array([sum(h["custo_r"]  for h in hist) for hist in res_h])
    custo_r = np.array([sum(h["custo_r"]  for h in hist) for hist in res_r])
    rede_s  = np.array([sum(h["rede_kwh"] for h in hist) for hist in res_s])
    rede_h  = np.array([sum(h["rede_kwh"] for h in hist) for hist in res_h])
    rede_r  = np.array([sum(h["rede_kwh"] for h in hist) for hist in res_r])

    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    fig.suptitle("Comparativo de Estratégias — Sem Agente × Heurístico × RL",
                 fontsize=13, fontweight="bold")

    # 1. Custo diário (3 barras agrupadas)
    ax = axes[0, 0]
    w = 0.28
    ax.bar(dias_x - w, custo_s, w, color=_COR_S, alpha=0.85, label="Sem Agente")
    ax.bar(dias_x,     custo_h, w, color=_COR_H, alpha=0.85, label="Heurístico")
    ax.bar(dias_x + w, custo_r, w, color=_COR_R, alpha=0.85, label="RL")
    ax.set_title("Custo Diário (R$)")
    ax.set_xticks(dias_x[::2]); ax.set_xticklabels(labels[::2], fontsize=7)
    ax.set_xlabel("Dia"); ax.set_ylabel("R$")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    # 2. kWh rede diário (3 barras agrupadas)
    ax = axes[0, 1]
    ax.bar(dias_x - w, rede_s, w, color=_COR_S, alpha=0.85, label="Sem Agente")
    ax.bar(dias_x,     rede_h, w, color=_COR_H, alpha=0.85, label="Heurístico")
    ax.bar(dias_x + w, rede_r, w, color=_COR_R, alpha=0.85, label="RL")
    ax.set_title(f"Energia da Rede (kWh/dia)  |  Média: {rede_s.mean():.1f} → {rede_h.mean():.1f} → {rede_r.mean():.1f}")
    ax.set_xticks(dias_x[::2]); ax.set_xticklabels(labels[::2], fontsize=7)
    ax.set_xlabel("Dia"); ax.set_ylabel("kWh")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    # 3. Totais mensais (custo e rede)
    ax = axes[1, 0]
    estrategias = ["Sem Agente", "Heurístico", "RL"]
    cores       = [_COR_S, _COR_H, _COR_R]
    totais_c    = [custo_s.sum(), custo_h.sum(), custo_r.sum()]
    bars = ax.bar(estrategias, totais_c, color=cores, alpha=0.9)
    for b, v in zip(bars, totais_c):
        delt_base = ((v - totais_c[0]) / totais_c[0] * 100) if totais_c[0] > 0 else 0
        rot = f"R$ {v:.0f}" + (f"\n({delt_base:+.1f}%)" if v != totais_c[0] else "")
        ax.text(b.get_x() + b.get_width()/2, v, rot, ha="center", va="bottom", fontsize=9,
                fontweight="bold")
    ax.set_title("Custo Total do Mês (R$)  —  Δ% vs Sem Agente")
    ax.set_ylabel("R$"); ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(totais_c) * 1.15)

    # 4. Consumo total por máquina (mensal) — Sem Agente vs RL (Heur já visível nos outros)
    ax = axes[1, 1]
    _maquinas_plot = [
        ("pivo_kw_consumido",     "Pivô"),
        ("captacao_kw_consumido", "Bomba Captação"),
        ("sede_kw_consumido",     "Sede"),
        ("silo_kw_consumido",     "Silo"),
        ("secador_kw_consumido",  "Secador"),
    ]
    nomes_maq = [n for _, n in _maquinas_plot]
    y_pos = np.arange(len(nomes_maq))
    bw = 0.28

    def _soma_maquinas(resultados):
        totais = []
        for campo, _ in _maquinas_plot:
            s = 0.0
            for hist in resultados:
                s += sum(h.get(campo, 0.0) for h in hist)
            totais.append(s)
        return totais

    vals_s = _soma_maquinas(res_s)
    vals_h = _soma_maquinas(res_h)
    vals_r = _soma_maquinas(res_r)
    ax.barh(y_pos + bw, vals_s, bw, color=_COR_S, alpha=0.85, label="Sem Agente")
    ax.barh(y_pos,       vals_h, bw, color=_COR_H, alpha=0.85, label="Heurístico")
    ax.barh(y_pos - bw,  vals_r, bw, color=_COR_R, alpha=0.85, label="RL")
    ax.set_yticks(y_pos); ax.set_yticklabels(nomes_maq)
    ax.set_xlabel("kWh no mês")
    ax.set_title("Consumo Total por Máquina (mês) — quanto cada estratégia cortou")
    ax.legend(fontsize=8); ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    _save(fig, "comparativo_3vias.png")
    return fig


# ──────────────────────────────────────────────────────────────
# Fonte de Energia — origem do consumo (geração própria / bateria / rede)
# ──────────────────────────────────────────────────────────────

_CORES_FONTE = {
    "Geração própria": "#f1c40f",   # amarelo/dourado (solar+eólico)
    "Bateria"        : "#27ae60",   # verde
    "Rede"           : "#e74c3c",   # vermelho
}


def plot_fonte_energia(
    fig: plt.Figure,
    hist_s: list[dict],
    hist_h: list[dict],
    hist_r: list[dict],
    data_str: str = "",
) -> None:
    """Desenha in-place: origem do consumo por hora, para 3 estratégias.

    Linha 1: stacked area (geração própria / bateria / rede) para cada estratégia.
    Linha 2: pizza com participação percentual de cada fonte no dia.
    """
    fig.clf()
    axes = fig.subplots(2, 3)
    horas = list(range(24))

    titulo = f"Origem da Energia Consumida — {data_str}" if data_str else "Origem da Energia Consumida"
    fig.suptitle(titulo, fontsize=13, fontweight="bold")

    estrategias = [
        ("Sem Agente", hist_s),
        ("Heurístico", hist_h),
        ("RL",         hist_r),
    ]

    for col, (nome, hist) in enumerate(estrategias):
        ger = np.array([h.get("fonte_geracao_kwh", 0.0) for h in hist])
        bat = np.array([h.get("fonte_bateria_kwh", 0.0) for h in hist])
        red = np.array([h.get("fonte_rede_kwh",    0.0) for h in hist])
        total_dia = ger.sum() + bat.sum() + red.sum()

        # ── Stacked area por hora ────────────────────────────────
        ax = axes[0, col]
        ax.stackplot(
            horas, ger, bat, red,
            labels=["Geração própria", "Bateria", "Rede"],
            colors=[_CORES_FONTE["Geração própria"],
                    _CORES_FONTE["Bateria"],
                    _CORES_FONTE["Rede"]],
            alpha=0.9,
        )
        ax.axvspan(17.5, 20.5, alpha=0.12, color="orange")
        custo_dia = sum(h["custo_r"] for h in hist)
        ax.set_title(f"{nome}\nCusto R${custo_dia:.2f}  |  {total_dia:.1f} kWh")
        ax.set_xlabel("Hora"); ax.set_ylabel("kW")
        ax.set_xlim(0, 23); ax.legend(fontsize=7, loc="upper left")
        ax.grid(alpha=0.3)

        # ── Pizza com participação percentual ────────────────────
        ax = axes[1, col]
        valores = [ger.sum(), bat.sum(), red.sum()]
        nomes_f = list(_CORES_FONTE.keys())
        cores_f = list(_CORES_FONTE.values())
        valores_nz = [max(v, 1e-9) for v in valores]
        ax.pie(
            valores_nz, labels=nomes_f, colors=cores_f,
            autopct=lambda p: f"{p:.1f}%" if p > 1 else "",
            startangle=90, wedgeprops=dict(alpha=0.9, edgecolor="white", linewidth=2),
        )
        pct_propria = (valores[0] + valores[1]) / max(total_dia, 1e-9) * 100
        ax.set_title(f"Autossuficiência: {pct_propria:.1f}%", fontsize=10)

    fig.tight_layout()


# ──────────────────────────────────────────────────────────────
# Máquina Detalhada — drill-down por equipamento
# ──────────────────────────────────────────────────────────────

# Valores: (cols_demanda_list_or_None, cols_consumido_list, cor, cmap).
# Entradas com múltiplas colunas são somadas (caso de "Secadora/silo").
_MAQUINAS_DETALHE = {
    "Pivô (irrigação)"    : (["pivo_kw"],            ["pivo_kw_consumido"],     "#e74c3c", "YlOrRd"),
    "Bomba de Captação"   : (["captacao_kw"],        ["captacao_kw_consumido"], "#3498db", "Blues"),
    "Sede / Escritório"   : (["sede_kw"],            ["sede_kw_consumido"],     "#9b59b6", "Purples"),
    "Secadora/silo"       : (["silo_kw", "secador_kw"],
                             ["silo_kw_consumido", "secador_kw_consumido"],     "#d35400", "YlOrBr"),
}


def plot_maquina_detalhada(
    fig: plt.Figure,
    nome_maquina: str,
    dias: list[pd.DataFrame],
    res_s: list[list[dict]],
    res_h: list[list[dict]],
    res_r: list[list[dict]],
) -> None:
    """Desenha in-place um drill-down para uma máquina selecionada.

    Painéis:
      (0,0) Heatmap dia × hora do consumo nominal (demanda) da máquina
      (0,1) Perfil horário médio (linha) — demanda vs consumo nas 3 estratégias
      (1,0) Consumo diário total (kWh) — 3 estratégias lado a lado
      (1,1) Boxplot da distribuição de kWh diário
      (2,0) Cumprimento da restrição operacional (texto)
      (2,1) Origem da energia (donut) — geração/bateria/rede
    """
    fig.clf()
    gs = fig.add_gridspec(3, 2)
    ax_heat    = fig.add_subplot(gs[0, 0])
    ax_perfil  = fig.add_subplot(gs[0, 1])
    ax_diario  = fig.add_subplot(gs[1, 0])
    ax_box     = fig.add_subplot(gs[1, 1])
    ax_texto   = fig.add_subplot(gs[2, 0])
    ax_donut   = fig.add_subplot(gs[2, 1])

    cols_nom, cols_cons, cor, cmap = _MAQUINAS_DETALHE[nome_maquina]
    fig.suptitle(f"Máquina: {nome_maquina}", fontsize=13, fontweight="bold")

    def _soma_cols_dia(df, cols):
        v = np.zeros(24)
        for c in cols:
            if c in df.columns:
                v += df[c].to_numpy(dtype=float)
        return v

    def _soma_cols_hist(hist, cols):
        s = 0.0
        for c in cols:
            s += hist.get(c, 0.0)
        return s

    n_dias = len(dias)
    horas  = list(range(24))

    # ── Heatmap dia × hora da demanda nominal ────────────────────
    matriz = np.array([_soma_cols_dia(d, cols_nom) for d in dias])
    im = ax_heat.imshow(matriz, aspect="auto", cmap=cmap, interpolation="nearest")
    fig.colorbar(im, ax=ax_heat, fraction=0.04, pad=0.02, label="kW nominal")
    total = matriz.sum()
    pico  = matriz.max()
    ax_heat.set_title(f"Demanda nominal (dia × hora)\nTotal: {total:.0f} kWh  |  Pico: {pico:.1f} kW",
                      fontsize=10)

    ax_heat.axvspan(17.5, 20.5, alpha=0.15, color="white")
    ax_heat.set_xlabel("Hora"); ax_heat.set_ylabel("Dia")
    ax_heat.set_xticks(range(0, 24, 3))
    step = max(1, n_dias // 10)
    datas_labels = [d["data"].iloc[0].strftime("%d") for d in dias]
    ax_heat.set_yticks(range(0, n_dias, step))
    ax_heat.set_yticklabels(datas_labels[::step], fontsize=7)

    # ── Perfil horário médio (24 horas) ─────────────────────────
    def _perfil_consumo(resultados):
        m = np.zeros(24)
        for hist in resultados:
            for h in hist:
                m[h["hora"]] += _soma_cols_hist(h, cols_cons)
        return m / max(len(resultados), 1)

    perfil_s = _perfil_consumo(res_s)
    perfil_h = _perfil_consumo(res_h)
    perfil_r = _perfil_consumo(res_r)

    demanda_media = np.mean([_soma_cols_dia(d, cols_nom) for d in dias], axis=0)
    if demanda_media.sum() > 0:
        ax_perfil.fill_between(horas, demanda_media, alpha=0.18, color=cor,
                               label="Demanda média")

    ax_perfil.plot(horas, perfil_s, "-",  color=_COR_S, lw=2, label="Sem Agente", alpha=0.9)
    ax_perfil.plot(horas, perfil_h, "--", color=_COR_H, lw=2, label="Heurístico")
    ax_perfil.plot(horas, perfil_r, "-.", color=_COR_R, lw=2.2, label="RL")
    ax_perfil.axvspan(17.5, 20.5, alpha=0.12, color="orange", label="Pico tarifário")
    ax_perfil.set_title("Perfil horário médio (consumo por estratégia)")
    ax_perfil.set_xlabel("Hora"); ax_perfil.set_ylabel("kW (média diária)")
    ax_perfil.legend(fontsize=7); ax_perfil.grid(alpha=0.3)
    ax_perfil.set_xlim(0, 23)

    # ── Consumo diário total (kWh) — 3 estratégias ──────────────
    diario_s = np.array([sum(_soma_cols_hist(h, cols_cons) for h in hist) for hist in res_s])
    diario_h = np.array([sum(_soma_cols_hist(h, cols_cons) for h in hist) for hist in res_h])
    diario_r = np.array([sum(_soma_cols_hist(h, cols_cons) for h in hist) for hist in res_r])
    dias_x = np.arange(n_dias)
    w = 0.28
    ax_diario.bar(dias_x - w, diario_s, w, color=_COR_S, alpha=0.85, label="Sem Agente")
    ax_diario.bar(dias_x,     diario_h, w, color=_COR_H, alpha=0.85, label="Heurístico")
    ax_diario.bar(dias_x + w, diario_r, w, color=_COR_R, alpha=0.85, label="RL")
    ax_diario.set_title("Consumo diário total (kWh)")
    ax_diario.set_xticks(dias_x[::2])
    ax_diario.set_xticklabels(datas_labels[::2], fontsize=7)
    ax_diario.set_xlabel("Dia"); ax_diario.set_ylabel("kWh")
    ax_diario.legend(fontsize=7); ax_diario.grid(axis="y", alpha=0.3)

    # ── Boxplot da distribuição diária ──────────────────────────
    # `labels=` foi removido do boxplot no matplotlib 3.10; setar os rótulos
    # via set_xticklabels funciona em qualquer versão.
    bp = ax_box.boxplot(
        [diario_s, diario_h, diario_r],
        patch_artist=True, widths=0.55,
    )
    ax_box.set_xticks([1, 2, 3])
    ax_box.set_xticklabels(["Sem Agente", "Heurístico", "RL"])
    for patch, c in zip(bp["boxes"], [_COR_S, _COR_H, _COR_R]):
        patch.set_facecolor(c); patch.set_alpha(0.6)
    ax_box.set_title("Distribuição de kWh diário")
    ax_box.set_ylabel("kWh/dia"); ax_box.grid(axis="y", alpha=0.3)

    # ── Cumprimento da restrição operacional (texto) ────────────
    ax_texto.axis("off")
    total_s, total_h, total_r = diario_s.sum(), diario_h.sum(), diario_r.sum()
    pct_pico_r = sum(_soma_cols_hist(h, cols_cons)
                     for hist in res_r for h in hist if 18 <= h["hora"] <= 20)
    pct_pico_r = (pct_pico_r / max(total_r, 1e-9)) * 100

    # Cálculos específicos por máquina
    extra_linhas = []
    if nome_maquina == "Pivô (irrigação)":
        dias_ativ = sum(1 for hist in res_r
                        if any(_soma_cols_hist(h, cols_cons) > 0 for h in hist))
        horas_inicio = [next((h["hora"] for h in hist
                              if _soma_cols_hist(h, cols_cons) > 0), None)
                        for hist in res_r]
        horas_inicio = [h for h in horas_inicio if h is not None]
        h_med = float(np.mean(horas_inicio)) if horas_inicio else 0.0
        # Verifica 8h consecutivas
        dias_8h = 0
        for hist in res_r:
            on = [_soma_cols_hist(h, cols_cons) > 0 for h in hist]
            streak = 0; max_streak = 0
            for v in on:
                streak = streak + 1 if v else 0
                max_streak = max(max_streak, streak)
            if max_streak >= 8:
                dias_8h += 1
        extra_linhas += [
            f"Dias ativado     : {dias_ativ}/{n_dias}",
            f"Hora início méd. : {h_med:5.1f}h",
            f"Dias com 8h cons.: {dias_8h}/{n_dias}",
        ]
    elif nome_maquina == "Bomba de Captação":
        # Schedule fixo {0,1,6,7,12,13,21,22}
        from .config import BOMBA_HORAS_ON
        horas_esperadas = sum(len(BOMBA_HORAS_ON) for _ in res_r)
        horas_cumpridas = sum(1 for hist in res_r for h in hist
                              if h["hora"] in BOMBA_HORAS_ON
                              and _soma_cols_hist(h, cols_cons) > 0)
        pct_cumpr = (horas_cumpridas / max(horas_esperadas, 1)) * 100
        kwh_med_dia = total_r / max(n_dias, 1)
        extra_linhas += [
            f"Schedule cumprido: {pct_cumpr:5.1f}% ({horas_cumpridas}/{horas_esperadas})",
            f"kWh médio/dia    : {kwh_med_dia:6.1f}",
            f"kWh em pico (RL) : {pct_pico_r:5.1f}%  (esperado: 0)",
        ]
    elif nome_maquina == "Secadora/silo":
        meta = CONFIG["secador_meta_kwh"]
        dias_meta = sum(1 for d in diario_r if d >= meta)
        media_dia = float(np.mean(diario_r))
        extra_linhas += [
            f"Meta diária secador: {meta:.1f} kWh",
            f"Dias atingiram   : {dias_meta}/{n_dias}",
            f"kWh médio/dia    : {media_dia:6.1f}",
            f"kWh em pico (RL) : {pct_pico_r:5.1f}%",
        ]
    else:
        extra_linhas += [
            f"Carga não controlada pelo agente",
            f"kWh médio/dia (RL): {total_r/max(n_dias,1):6.1f}",
        ]

    resumo = (
        f"RESUMO — {nome_maquina}\n"
        f"{'─' * 42}\n"
        f"Consumo total (kWh):\n"
        f"  Sem Agente : {total_s:>8.1f}\n"
        f"  Heurístico : {total_h:>8.1f}\n"
        f"  RL         : {total_r:>8.1f}\n"
        f"{'─' * 42}\n"
        f"Restrição operacional:\n"
    )
    for ln in extra_linhas:
        resumo += f"  {ln}\n"
    ax_texto.text(0.02, 0.98, resumo, transform=ax_texto.transAxes, fontsize=9,
                  va="top", fontfamily="monospace",
                  bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f5f5", alpha=0.9))

    # ── Donut da origem da energia (RL) ─────────────────────────
    # Calcula a energia gasta pela máquina dividida entre geração/bateria/rede
    # usando a proporção das fontes na hora respectiva.
    ger_kwh = bat_kwh = rede_kwh = 0.0
    for hist in res_r:
        for h in hist:
            v = _soma_cols_hist(h, cols_cons)
            if v <= 0:
                continue
            cons_total_h = h.get("consumo_kw", 0.0)
            if cons_total_h <= 0:
                continue
            frac = v / cons_total_h
            ger_kwh  += frac * h.get("fonte_geracao_kwh", 0.0)
            bat_kwh  += frac * h.get("fonte_bateria_kwh", 0.0)
            rede_kwh += frac * h.get("fonte_rede_kwh",    0.0)
    soma_origem = ger_kwh + bat_kwh + rede_kwh
    if soma_origem > 0:
        wedges, _, autotexts = ax_donut.pie(
            [ger_kwh, bat_kwh, rede_kwh],
            labels=["Geração", "Bateria", "Rede"],
            colors=["#f1c40f", "#3498db", "#e74c3c"],
            autopct="%1.0f%%", startangle=90,
            wedgeprops=dict(width=0.4, edgecolor="white"),
            textprops=dict(fontsize=9),
        )
        for t in autotexts:
            t.set_color("white"); t.set_fontweight("bold")
        ax_donut.set_title(f"Origem da energia consumida (RL)\nTotal: {soma_origem:.0f} kWh",
                           fontsize=10)
    else:
        ax_donut.axis("off")
        ax_donut.text(0.5, 0.5, "Sem consumo no RL",
                      ha="center", va="center", fontsize=11, color="#666")

    fig.tight_layout()


# ──────────────────────────────────────────────────────────────
# Visão Geral Operacional — BI consolidado
# ──────────────────────────────────────────────────────────────

# Pares (coluna_consumida, label) para iterar as 5 máquinas do modelo.
# Cada entrada: (lista_de_colunas, label, cor). Listas com >1 entrada são somadas.
_MAQ_KPI = [
    (["pivo_kw_consumido"],                              "Pivô",            "#e74c3c"),
    (["captacao_kw_consumido"],                          "Bomba Captação",  "#3498db"),
    (["sede_kw_consumido"],                              "Sede/Escritório", "#9b59b6"),
    (["silo_kw_consumido", "secador_kw_consumido"],      "Secadora/silo",   "#d35400"),
]


def _kpis_maquinas(historicos: list[list[dict]]) -> dict[str, dict]:
    """Calcula KPIs operacionais por máquina ao longo de todos os dias."""
    saida = {}
    for cols, label, _ in _MAQ_KPI:
        vals = np.array([[sum(h.get(c, 0.0) for c in cols) for h in hist]
                         for hist in historicos])
        kwh_mes  = float(vals.sum())
        h_ativ   = int((vals > 0).sum())
        pico_arr = vals[:, 18:21]
        kwh_pico = float(pico_arr.sum())
        pct_pico = (kwh_pico / kwh_mes * 100) if kwh_mes > 0 else 0.0
        kwh_dia  = float(vals.sum(axis=1).mean())
        saida[label] = dict(kwh_mes=kwh_mes, h_ativ=h_ativ,
                            kwh_pico=kwh_pico, pct_pico=pct_pico,
                            kwh_dia=kwh_dia)
    return saida


def _custo_por_maquina(historicos: list[list[dict]]) -> dict[str, float]:
    """Custo teórico (R$) por máquina = Σ kWh × tarifa(hora).

    Não desconta bateria/solar (representa o "custo natural" de cada carga).
    Útil para ranking de prioridade no BI.
    """
    saida = {}
    for cols, label, _ in _MAQ_KPI:
        custo = 0.0
        for hist in historicos:
            for h in hist:
                kwh = sum(h.get(c, 0.0) for c in cols)
                custo += kwh * h.get("tarifa", 0.0)
        saida[label] = custo
    return saida


def _custo_real_por_maquina(historicos: list[list[dict]]) -> dict[str, float]:
    """Custo real (R$) por máquina = rateio da fatura paga à rede.

    A cada hora, o custo efetivo da rede (`custo_r`, já líquido de bateria/solar)
    é distribuído entre as máquinas proporcionalmente à sua participação no
    consumo daquela hora. Soma exata = fatura total da estratégia, permitindo
    comparar onde cada estratégia efetivamente gasta.
    """
    saida = {label: 0.0 for _, label, _ in _MAQ_KPI}
    for hist in historicos:
        for h in hist:
            custo_h = h.get("custo_r", 0.0)
            if custo_h == 0:
                continue
            kwh_maq = {label: sum(h.get(c, 0.0) for c in cols)
                       for cols, label, _ in _MAQ_KPI}
            total = sum(kwh_maq.values())
            if total <= 0:
                continue
            for label, kwh in kwh_maq.items():
                saida[label] += custo_h * (kwh / total)
    return saida


def _custos_estrategia(historicos: list[list[dict]]) -> dict[str, float]:
    """Custos reais (fatura) e teóricos de uma estratégia.

    Returns:
        dict com chaves:
          custo_fatura_total : R$ pagos à rede no mês (= sum de custo_r)
          custo_medio_dia    : R$ por dia
          rede_kwh_total     : kWh importados da rede
          custo_por_kwh      : R$/kWh efetivo (na carga total)
    """
    custo_total = sum(h["custo_r"] for hist in historicos for h in hist)
    rede_total  = sum(h["rede_kwh"] for hist in historicos for h in hist)
    consumo_total = sum(h["consumo_kw"] for hist in historicos for h in hist)
    n_dias = max(len(historicos), 1)
    return {
        "custo_fatura_total" : custo_total,
        "custo_medio_dia"    : custo_total / n_dias,
        "rede_kwh_total"     : rede_total,
        "custo_por_kwh"      : (custo_total / consumo_total) if consumo_total > 0 else 0.0,
    }


def _metricas_microgrid(hist: list[list[dict]]) -> dict[str, float]:
    """Calcula SCR, SSR e PAR para uma estratégia.

    SCR = (geração consumida na hora) / (geração total)
    SSR = (consumo atendido por geração própria) / (consumo total)
    PAR = pico da rede / média da rede (importação)
    """
    ger_total = sum(h["geracao_kw"]   for d in hist for h in d)
    con_total = sum(h["consumo_kw"]   for d in hist for h in d)
    ger_dir   = sum(h.get("fonte_geracao_kwh", 0.0) for d in hist for h in d)
    bat_used  = sum(h.get("fonte_bateria_kwh", 0.0) for d in hist for h in d)
    rede_arr  = np.array([h["rede_kwh"] for d in hist for h in d])
    rede_med  = float(rede_arr.mean()) if rede_arr.size else 0.0
    rede_max  = float(rede_arr.max())  if rede_arr.size else 0.0

    scr = (ger_dir / ger_total * 100) if ger_total > 0 else 0.0
    ssr = ((ger_dir + bat_used) / con_total * 100) if con_total > 0 else 0.0
    par = (rede_max / rede_med) if rede_med > 0 else 0.0
    return {"SCR": scr, "SSR": ssr, "PAR": par}


def plot_visao_geral_operacional(
    fig: plt.Figure,
    dias: list[pd.DataFrame],
    res_s: list[list[dict]],
    res_h: list[list[dict]],
    res_r: list[list[dict]],
) -> None:
    """Painel BI consolidado de métricas operacionais e de microgrid."""
    fig.clf()
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1])
    ax_tab = fig.add_subplot(gs[0, 0])
    ax_bar = fig.add_subplot(gs[0, 1])
    ax_mg  = fig.add_subplot(gs[1, 0])
    ax_heat = fig.add_subplot(gs[1, 1])

    fig.suptitle("Visão Geral Operacional — todas as máquinas",
                 fontsize=13, fontweight="bold")

    kpi_s = _kpis_maquinas(res_s)
    kpi_h = _kpis_maquinas(res_h)
    kpi_r = _kpis_maquinas(res_r)
    cst_s_maq = _custo_por_maquina(res_s)
    cst_h_maq = _custo_por_maquina(res_h)
    cst_r_maq = _custo_por_maquina(res_r)
    real_h_maq = _custo_real_por_maquina(res_h)
    real_r_maq = _custo_real_por_maquina(res_r)
    cst_s = _custos_estrategia(res_s)
    cst_h = _custos_estrategia(res_h)
    cst_r = _custos_estrategia(res_r)

    # ── 1. Tabela de KPIs por máquina (RL) — com cascata de custo ────
    ax_tab.axis("off")
    headers = ["Máquina", "kWh mês", "Custo teórico R$", "Custo real R$",
               "% pico", "Δ$ real vs Heur"]
    linhas = []
    for cols, label, _ in _MAQ_KPI:
        r = kpi_r[label]
        c_r = cst_r_maq[label]
        real_r = real_r_maq[label]; real_h = real_h_maq[label]
        d_custo = ((real_r - real_h) / real_h * 100) if real_h > 0 else 0.0
        linhas.append([label, f"{r['kwh_mes']:.0f}",
                       f"R$ {c_r:,.0f}".replace(",", "."),
                       f"R$ {real_r:,.0f}".replace(",", "."),
                       f"{r['pct_pico']:.1f}%",
                       f"{d_custo:+.1f}%"])
    # Cascata: soma teórica → economia bat./solar → fatura real
    teorico_total = sum(cst_r_maq.values())
    economia_bs = teorico_total - cst_r["custo_fatura_total"]
    pct_econ = (economia_bs / teorico_total * 100) if teorico_total > 0 else 0.0
    d_fatura = ((cst_r["custo_fatura_total"] - cst_h["custo_fatura_total"])
                / max(cst_h["custo_fatura_total"], 1e-9) * 100)
    linhas.append(["Soma teórica", "—",
                   f"R$ {teorico_total:,.0f}".replace(",", "."),
                   "—", "—", "—"])
    linhas.append(["(−) Bat./solar", "—",
                   f"−R$ {economia_bs:,.0f}".replace(",", "."),
                   "—", "—", f"−{pct_econ:.1f}%"])
    linhas.append(["TOTAL FATURA (real)",
                   f"{cst_r['rede_kwh_total']:.0f}", "—",
                   f"R$ {cst_r['custo_fatura_total']:,.0f}".replace(",", "."),
                   "—", f"{d_fatura:+.1f}%"])

    tabela = ax_tab.table(cellText=linhas, colLabels=headers,
                          cellLoc="center", loc="center")
    tabela.auto_set_font_size(False); tabela.set_fontsize(9)
    tabela.scale(1.0, 1.4)
    for j in range(len(headers)):
        tabela[(0, j)].set_facecolor("#2c3e50")
        tabela[(0, j)].set_text_props(color="white", fontweight="bold")
    # Cores: soma=cinza, economia=verde, fatura=destaque azul
    n_linhas = len(linhas)
    cores_tot = ["#ecf0f1", "#d5f5e3", "#d6eaf8"]
    for k, cor in zip(range(n_linhas - 2, n_linhas + 1), cores_tot):
        for j in range(len(headers)):
            tabela[(k, j)].set_facecolor(cor)
            tabela[(k, j)].set_text_props(fontweight="bold")
    ax_tab.set_title("KPIs por máquina (RL) — teórico (kWh × tarifa) vs real (rateio da fatura) | cascata final: fatura paga",
                     fontsize=10)

    # ── 2. Custo R$ real por máquina × estratégia (stacked) ──────
    # Rateio da fatura paga (líquida de bateria/solar): pilha soma a fatura
    # real de cada estratégia, evidenciando onde o RL efetivamente economiza.
    labels_est = ["Sem Agente", "Heurístico", "RL"]
    real_s_maq = _custo_real_por_maquina(res_s)
    real_maq_por_est = [real_s_maq, real_h_maq, real_r_maq]
    bottoms = np.zeros(3)
    for cols, label, cor in _MAQ_KPI:
        vals = np.array([m[label] for m in real_maq_por_est])
        ax_bar.bar(labels_est, vals, bottom=bottoms, label=label, color=cor, alpha=0.85)
        bottoms += vals
    # Rótulo do total (= fatura real) no topo de cada pilha
    for i, total in enumerate(bottoms):
        ax_bar.text(i, total + max(bottoms) * 0.015,
                    f"R${total:,.0f}".replace(",", "."),
                    ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color="#1b4f72")
    ax_bar.set_title(
        "Custo R$ real por máquina × estratégia\n"
        "Pilha = rateio da fatura paga (após bateria/solar)",
        fontsize=10)
    ax_bar.set_ylabel("R$")
    ax_bar.legend(fontsize=7, loc="upper left")
    ax_bar.grid(axis="y", alpha=0.3)
    ax_bar.set_ylim(0, max(bottoms) * 1.20)

    # ── 3. Métricas de microgrid (SCR, SSR, PAR) ────────────────
    mg_s = _metricas_microgrid(res_s)
    mg_h = _metricas_microgrid(res_h)
    mg_r = _metricas_microgrid(res_r)
    metricas = ["SCR", "SSR", "PAR"]
    x = np.arange(len(metricas)); w = 0.27
    ax_mg.bar(x - w, [mg_s[m] for m in metricas], w, label="Sem Agente", color=_COR_S)
    ax_mg.bar(x,     [mg_h[m] for m in metricas], w, label="Heurístico", color=_COR_H)
    ax_mg.bar(x + w, [mg_r[m] for m in metricas], w, label="RL",          color=_COR_R)
    ax_mg.set_xticks(x); ax_mg.set_xticklabels(metricas)
    ax_mg.set_title("Métricas de microgrid", fontsize=11)
    ax_mg.legend(fontsize=8); ax_mg.grid(axis="y", alpha=0.3)
    for i, m in enumerate(metricas):
        suf = "%" if m in ("SCR", "SSR") else ""
        ax_mg.text(i - w, mg_s[m] + 0.5, f"{mg_s[m]:.1f}{suf}", ha="center", fontsize=7)
        ax_mg.text(i,     mg_h[m] + 0.5, f"{mg_h[m]:.1f}{suf}", ha="center", fontsize=7)
        ax_mg.text(i + w, mg_r[m] + 0.5, f"{mg_r[m]:.1f}{suf}", ha="center", fontsize=7)
    # Tooltip explicativo dentro do painel
    ax_mg.text(
        0.99, 0.97,
        "SCR ↑  geração consumida/total\nSSR ↑  consumo atendido localmente\nPAR ↓  achatamento de pico",
        transform=ax_mg.transAxes, ha="right", va="top",
        fontsize=7, fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#fafafa",
                  edgecolor="#bdc3c7", linewidth=0.8, alpha=0.95),
    )

    # ── 4. Heatmap consolidado: uso total × hora ─────────────────
    # Soma kW de todas as máquinas do RL, agregado em (dia × hora).
    matriz = np.zeros((len(res_r), 24))
    for d, hist in enumerate(res_r):
        for h in hist:
            soma = sum(h.get(c, 0.0) for cols, _, _ in _MAQ_KPI for c in cols)
            matriz[d, int(h["hora"])] = soma
    im = ax_heat.imshow(matriz, aspect="auto", cmap="viridis", interpolation="nearest")
    fig.colorbar(im, ax=ax_heat, fraction=0.04, pad=0.02, label="kW total")
    ax_heat.axvspan(17.5, 20.5, alpha=0.18, color="white")
    ax_heat.set_title("Carga total (dia × hora) — RL", fontsize=11)
    ax_heat.set_xlabel("Hora"); ax_heat.set_ylabel("Dia")
    ax_heat.set_xticks(range(0, 24, 3))
    step = max(1, len(dias) // 10)
    datas_labels = [d["data"].iloc[0].strftime("%d") for d in dias]
    ax_heat.set_yticks(range(0, len(dias), step))
    ax_heat.set_yticklabels(datas_labels[::step], fontsize=7)

    fig.tight_layout()


def plot_comparacao_runs(fig, hist_a, hist_b, label_a, label_b=None) -> None:
    """Sobrepõe as curvas de aprendizado (custo/reward) de dois runs numa Figure.

    `hist_a`/`hist_b` são os dicts de `runs.ler_historico`. `hist_b` pode ser
    None (compara só o run A). Séries longas são reduzidas por média de blocos
    para o plot ficar leve.
    """
    def _reduz(serie, alvo=1200):
        n = len(serie)
        if n == 0:
            return [], []
        if n <= alvo:
            return list(range(1, n + 1)), list(serie)
        bloco = n // alvo
        arr = np.asarray(serie[: bloco * alvo], dtype=float).reshape(-1, bloco).mean(axis=1)
        return [(i + 1) * bloco for i in range(len(arr))], arr.tolist()

    fig.clf()
    ax_c = fig.add_subplot(1, 2, 1)
    ax_r = fig.add_subplot(1, 2, 2)

    def _plot(hist, cor, nome):
        if not hist:
            return
        xc, yc = _reduz(hist.get("custos") or [])
        xr, yr = _reduz(hist.get("rewards") or [])
        ax_c.plot(xc, yc, color=cor, label=nome, linewidth=1.3)
        ax_r.plot(xr, yr, color=cor, label=nome, linewidth=1.3)

    _plot(hist_a, "#2980b9", label_a)
    if hist_b is not None:
        _plot(hist_b, "#e67e22", label_b)

    ax_c.set_title("Custo por episódio (R$)"); ax_c.set_xlabel("Episódio")
    ax_c.grid(alpha=0.3); ax_c.legend(fontsize=8)
    ax_r.set_title("Reward por episódio"); ax_r.set_xlabel("Episódio")
    ax_r.grid(alpha=0.3); ax_r.legend(fontsize=8)
    fig.suptitle("Curvas de aprendizado — Run A (azul) vs Run B (laranja)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()


def plot_tradeoff_mcp(res: dict) -> plt.Figure:
    """Gráfico de trade-off do benchmark RL × LLM-via-MCP.

    Recebe o dict de ``benchmark.rodar_benchmark`` e plota dois painéis:
      (a) Pareto — custo de energia (R$/dia, ↓ melhor) × custo operacional de
          API (R$/mês). RL puro fica em X≈0; o LLM se desloca à direita. A
          pergunta do TCC vira visual: o deslocamento em X se justifica?
      (b) Custo operacional do LLM — latência (mediana/p95) e taxa de fallback.
    """
    q = res["eixo1_qualidade"]
    op = res.get("eixo2_operacional", {}) or {}
    ca = res.get("custo_api", {})

    fig, (ax_p, ax_o) = plt.subplots(1, 2, figsize=(13, 5))

    # ── (a) Pareto: custo energia × custo API ──────────────────────
    pontos = [
        ("Sem Agente", q["sem_agente"]["custo_r"], 0.0, "#7f8c8d"),
        ("Heurístico", q["heuristico"]["custo_r"], 0.0, _COR_H),
        ("RL puro",    q["rl"]["custo_r"],         0.0, _COR_R),
        ("LLM/MCP",    q["llm"]["custo_r"], ca.get("brl_total", 0.0), "#8e44ad"),
    ]
    for nome, custo_e, custo_api, cor in pontos:
        ax_p.scatter(custo_api, custo_e, s=160, color=cor, zorder=3,
                     edgecolors="white", linewidths=1.5)
        ax_p.annotate(f"{nome}\nR${custo_e:.2f}/dia", (custo_api, custo_e),
                      textcoords="offset points", xytext=(8, 8), fontsize=9)
    ax_p.set_xlabel("Custo operacional de API (R$/mês)")
    ax_p.set_ylabel("Custo de energia (R$/dia)  ↓ melhor")
    ax_p.set_title("Trade-off: economia × custo de API")
    ax_p.grid(True, alpha=0.3)
    if ca.get("preco", {}).get("snapshot"):
        ax_p.text(0.98, 0.02, f"preço: {ca['preco']['snapshot']}",
                  transform=ax_p.transAxes, ha="right", va="bottom",
                  fontsize=7, color="gray")

    # ── (b) Custo operacional do LLM ───────────────────────────────
    lat_med = op.get("latencia_ms_mediana", 0.0)
    lat_p95 = op.get("latencia_ms_p95", 0.0)
    barras = ax_o.bar(["latência\nmediana", "latência\np95"], [lat_med, lat_p95],
                      color=["#8e44ad", "#c39bd3"])
    ax_o.bar_label(barras, fmt="%.0f ms", padding=3, fontsize=9)
    ax_o.set_ylabel("Latência por decisão (ms)")
    taxa_fb = op.get("taxa_fallback", 0.0) * 100
    ax_o.set_title(f"Custo operacional do LLM  ·  fallback {taxa_fb:.1f}%")
    ax_o.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    _save(fig, "tradeoff_mcp.png")
    return fig
