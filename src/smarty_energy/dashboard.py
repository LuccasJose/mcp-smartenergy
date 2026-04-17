"""Dashboard unificado — embute todas as figuras em uma única janela Tk.

Substitui as 3 janelas matplotlib sequenciais por uma janela com abas
(ttk.Notebook). Cada aba contém uma figura matplotlib embutida via
FigureCanvasTkAgg e a barra de navegação padrão (zoom/pan/save).

Uso:
    from smarty_energy.dashboard import abrir_dashboard
    abrir_dashboard(figuras)   # dict {"Aba": Figure, ...}
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


def abrir_dashboard(figuras: dict[str, Figure], titulo: str = "SmartEnergy MAS — Dashboard") -> None:
    """Abre uma janela única com uma aba por figura.

    Args:
        figuras : dict ordenado {nome_aba: Figure}. A ordem do dict é a
                  ordem das abas (Python 3.7+ garante).
        titulo  : título da janela.
    """
    root = tk.Tk()
    root.title(titulo)
    # Tenta iniciar em tela cheia/grande; cai para 1400x900 se necessário.
    try:
        root.state("zoomed")
    except tk.TclError:
        root.geometry("1400x900")

    # Estilo das abas
    estilo = ttk.Style()
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("TNotebook.Tab", padding=(14, 6), font=("Segoe UI", 10, "bold"))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    for nome, fig in figuras.items():
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=nome)

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()

        barra = NavigationToolbar2Tk(canvas, frame, pack_toolbar=False)
        barra.update()
        barra.pack(side=tk.BOTTOM, fill=tk.X)

        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # Rodapé discreto
    rodape = ttk.Label(
        root,
        text="Navegue pelas abas  •  Use a barra inferior para zoom/pan/salvar  •  Feche a janela para encerrar",
        anchor="center",
        padding=(0, 4),
    )
    rodape.pack(side=tk.BOTTOM, fill=tk.X)

    root.mainloop()
