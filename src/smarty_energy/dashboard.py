"""Dashboard unificado — embute todas as figuras em uma única janela Tk.

Substitui as janelas matplotlib sequenciais por uma janela com abas
(ttk.Notebook). Cada aba contém uma figura matplotlib embutida via
FigureCanvasTkAgg e a barra de navegação padrão (zoom/pan/save).

Abas interativas (criadas sob demanda):
    - Explorar Dia        : combo com os 31 dias; mostra perfil detalhado
    - Fonte de Energia    : combo de dia; stacked area de origem (ger/bat/rede)
                            para as 3 estratégias (Sem Agente × Heurístico × RL)
    - Máquina Detalhada   : combo de máquina; heatmap + perfil horário + diário
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import (  # noqa: E402
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure  # noqa: E402


def _embutir_figura(
    frame: ttk.Frame,
    fig: Figure,
) -> FigureCanvasTkAgg:
    """Embute uma Figure no frame com barra de navegação padrão."""
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    barra = NavigationToolbar2Tk(canvas, frame, pack_toolbar=False)
    barra.update()
    barra.pack(side=tk.BOTTOM, fill=tk.X)
    return canvas


def _criar_aba_explorar(notebook: ttk.Notebook, dados: dict) -> None:
    """Cria aba interativa com combobox para selecionar o dia."""
    from smarty_energy.visualization import plot_explorar_dia

    dias = dados["dias"]
    res_h = dados["res_h"]
    res_r = dados["res_r"]
    labels = [d["data"].iloc[0].strftime("%d/%m/%Y") for d in dias]

    frame = ttk.Frame(notebook)
    notebook.add(frame, text="Explorar Dia")

    controle = ttk.Frame(frame)
    controle.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
    ttk.Label(controle, text="Selecione o dia:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 8))
    combo = ttk.Combobox(controle, values=labels, state="readonly", width=14, font=("Segoe UI", 10))
    combo.current(0)
    combo.pack(side=tk.LEFT)

    ttk.Label(controle, text="Máquina:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(20, 8))
    opcoes_maq = ["Todas", "Pivô", "Bomba Captação", "Sede/Escritório", "Secadora/silo"]
    combo_maq = ttk.Combobox(controle, values=opcoes_maq, state="readonly", width=18, font=("Segoe UI", 10))
    combo_maq.current(0)
    combo_maq.pack(side=tk.LEFT)

    fig = Figure(figsize=(15, 12))
    canvas = _embutir_figura(frame, fig)

    def _atualizar(_event=None):
        idx = combo.current()
        plot_explorar_dia(fig, dias[idx], res_h[idx], res_r[idx], labels[idx],
                          todos_dias=dias, filtro_maquina=combo_maq.get())
        canvas.draw_idle()

    combo.bind("<<ComboboxSelected>>", _atualizar)
    combo_maq.bind("<<ComboboxSelected>>", _atualizar)
    _atualizar()


def _criar_aba_fonte_energia(notebook: ttk.Notebook, dados: dict) -> None:
    """Aba interativa — origem da energia (ger/bat/rede) por dia e estratégia."""
    from smarty_energy.visualization import plot_fonte_energia

    dias  = dados["dias"]
    res_s = dados["res_s"]
    res_h = dados["res_h"]
    res_r = dados["res_r"]
    labels = [d["data"].iloc[0].strftime("%d/%m/%Y") for d in dias]

    frame = ttk.Frame(notebook)
    notebook.add(frame, text="Fonte de Energia")

    controle = ttk.Frame(frame)
    controle.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
    ttk.Label(controle, text="Selecione o dia:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 8))
    combo = ttk.Combobox(controle, values=labels, state="readonly", width=14, font=("Segoe UI", 10))
    combo.current(0)
    combo.pack(side=tk.LEFT)
    ttk.Label(
        controle,
        text="  (geração própria = solar + eólico direto na carga; bateria = descarga)",
        font=("Segoe UI", 8), foreground="#555"
    ).pack(side=tk.LEFT, padx=(10, 0))

    fig = Figure(figsize=(15, 9))
    canvas = _embutir_figura(frame, fig)

    def _atualizar(_event=None):
        idx = combo.current()
        plot_fonte_energia(fig, res_s[idx], res_h[idx], res_r[idx], labels[idx])
        canvas.draw_idle()

    combo.bind("<<ComboboxSelected>>", _atualizar)
    _atualizar()


def _criar_aba_visao_geral(notebook: ttk.Notebook, dados: dict) -> None:
    """Aba consolidada com KPIs operacionais e métricas de microgrid."""
    from smarty_energy.visualization import plot_visao_geral_operacional

    frame = ttk.Frame(notebook)
    notebook.add(frame, text="Visão Geral Operacional")

    info = ttk.Label(
        frame,
        text="KPIs por máquina  •  comparação mensal por estratégia  •  SCR/SSR/PAR  •  heatmap consolidado",
        font=("Segoe UI", 9), foreground="#555",
    )
    info.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(6, 0))

    fig = Figure(figsize=(15, 10))
    _embutir_figura(frame, fig)
    plot_visao_geral_operacional(fig, dados["dias"], dados["res_s"], dados["res_h"], dados["res_r"])


def _criar_aba_maquina_detalhada(notebook: ttk.Notebook, dados: dict) -> None:
    """Aba interativa — drill-down por máquina."""
    from smarty_energy.visualization import plot_maquina_detalhada, _MAQUINAS_DETALHE

    dias  = dados["dias"]
    res_s = dados["res_s"]
    res_h = dados["res_h"]
    res_r = dados["res_r"]
    nomes_maq = list(_MAQUINAS_DETALHE.keys())

    frame = ttk.Frame(notebook)
    notebook.add(frame, text="Máquina Detalhada")

    controle = ttk.Frame(frame)
    controle.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
    ttk.Label(controle, text="Selecione a máquina:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 8))
    combo = ttk.Combobox(controle, values=nomes_maq, state="readonly", width=24, font=("Segoe UI", 10))
    combo.current(0)
    combo.pack(side=tk.LEFT)
    ttk.Label(
        controle,
        text="  (heatmap mostra demanda; barras e linhas mostram quanto cada estratégia usou)",
        font=("Segoe UI", 8), foreground="#555"
    ).pack(side=tk.LEFT, padx=(10, 0))

    fig = Figure(figsize=(15, 10))
    canvas = _embutir_figura(frame, fig)

    def _atualizar(_event=None):
        plot_maquina_detalhada(fig, combo.get(), dias, res_s, res_h, res_r)
        canvas.draw_idle()

    combo.bind("<<ComboboxSelected>>", _atualizar)
    _atualizar()


def _derivar_dados(dados_3: dict) -> tuple[dict, dict, dict]:
    """Quebra um dict {dias,res_s,res_h,res_r} nos 3 dados das abas interativas."""
    d_explorar = {
        "dias" : dados_3["dias"],
        "res_h": dados_3["res_h"],
        "res_r": dados_3["res_r"],
    }
    return d_explorar, dados_3, dados_3


def abrir_dashboard(
    figuras: dict[str, Figure],
    titulo: str = "SmartEnergy MAS — Dashboard",
    dados_explorar: dict | None = None,
    dados_fonte: dict | None = None,
    dados_maquina: dict | None = None,
    construtor=None,
    runs_disp: list[dict] | None = None,
    run_inicial: str | None = None,
) -> None:
    """Abre uma janela única com uma aba por figura + abas interativas.

    Args:
        figuras        : dict ordenado {nome_aba: Figure} do run inicial.
        titulo         : título da janela.
        dados_explorar : {"dias", "res_h", "res_r"} — aba "Explorar Dia".
        dados_fonte    : {"dias", "res_s", "res_h", "res_r"} — aba "Fonte de Energia".
        dados_maquina  : {"dias", "res_s", "res_h", "res_r"} — aba "Máquina Detalhada".
        construtor     : callable(run_id) -> (figuras, dados_3) usado para
                         reconstruir as abas ao trocar de run. Se None, o
                         seletor de run não é exibido.
        runs_disp      : lista de runs (saída de runs.listar_runs) p/ o seletor.
        run_inicial    : run_id selecionado ao abrir.
    """
    root = tk.Tk()
    root.title(titulo)
    try:
        root.state("zoomed")
    except tk.TclError:
        root.geometry("1400x900")

    estilo = ttk.Style()
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("TNotebook.Tab", padding=(14, 6), font=("Segoe UI", 10, "bold"))

    usar_seletor = construtor is not None and runs_disp

    # ── Barra superior com seletor de run (opcional) ──────────────
    status_var = tk.StringVar(value="")
    if usar_seletor:
        labels = [r["label"] for r in runs_disp]
        ids    = [r["run_id"] for r in runs_disp]
        try:
            idx_ini = ids.index(run_inicial)
        except ValueError:
            idx_ini = 0

        barra = ttk.Frame(root)
        barra.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        ttk.Label(barra, text="Run (treino):", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        combo_run = ttk.Combobox(barra, values=labels, state="readonly",
                                 width=46, font=("Segoe UI", 10))
        combo_run.current(idx_ini)
        combo_run.pack(side=tk.LEFT)
        root.title(f"{titulo} — {labels[idx_ini]}")
        ttk.Label(barra, textvariable=status_var, foreground="#c0392b",
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(12, 0))

    container = ttk.Frame(root)
    container.pack(fill="both", expand=True)

    estado: dict = {"notebook": None}

    def _popular(figs, d_explorar, d_fonte, d_maquina):
        if estado["notebook"] is not None:
            estado["notebook"].destroy()
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)
        estado["notebook"] = notebook

        for nome, fig in figs.items():
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=nome)
            _embutir_figura(frame, fig).draw()

        if d_explorar is not None:
            _criar_aba_explorar(notebook, d_explorar)
        if d_fonte is not None:
            _criar_aba_fonte_energia(notebook, d_fonte)
        if d_maquina is not None:
            _criar_aba_visao_geral(notebook, d_maquina)
            _criar_aba_maquina_detalhada(notebook, d_maquina)

    _popular(figuras, dados_explorar, dados_fonte, dados_maquina)

    if usar_seletor:
        def _trocar_run(_event=None):
            i = combo_run.current()
            run_id = ids[i]
            status_var.set(f"Recalculando run {run_id}…")
            root.update_idletasks()
            figs, dados_3 = construtor(run_id)
            d_expl, d_fonte, d_maq = _derivar_dados(dados_3)
            _popular(figs, d_expl, d_fonte, d_maq)
            root.title(f"{titulo} — {labels[i]}")
            status_var.set("")

        combo_run.bind("<<ComboboxSelected>>", _trocar_run)

    rodape = ttk.Label(
        root,
        text="Navegue pelas abas  •  Use a barra inferior para zoom/pan/salvar  •  Feche a janela para encerrar",
        anchor="center",
        padding=(0, 4),
    )
    rodape.pack(side=tk.BOTTOM, fill=tk.X)

    root.mainloop()
