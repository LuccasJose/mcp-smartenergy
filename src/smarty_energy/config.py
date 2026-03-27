import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Caminhos resolvidos a partir da raiz do projeto
_ROOT = Path(__file__).resolve().parents[2]

# Google Sheets — ID extraído do link de compartilhamento
SHEET_ID = os.getenv(
    "SHEET_ID",
    "1Ih71F74ugD7aZvHk8P56sYPXoClKcNZC1dWq2G5fdSk",
)

# Fallback local (usado apenas se SHEET_ID estiver vazio)
DATA_PATH = _ROOT / os.getenv("DATA_PATH", "data/modelo_dados_gestao_energia_fazenda.xlsx")
OUTPUT_DIR = _ROOT / os.getenv("OUTPUT_DIR", "outputs")

# ──────────────────────────────────────────────────────────────
# Parâmetros globais — ajuste aqui antes de rodar
# ──────────────────────────────────────────────────────────────
CONFIG = {
    # Treinamento
    "n_episodios": 2000,    # dias simulados no treino
    "alpha": 0.1,           # taxa de aprendizado
    "gamma": 0.95,          # fator de desconto futuro
    "epsilon_inicial": 1.0, # exploração inicial (100 %)
    "epsilon_final": 0.05,  # exploração mínima  (5 %)
    "epsilon_decay": 0.9975,# decaimento por episódio

    # Bateria
    "bateria_cap_kwh": 24.0,
    "soc_inicial_pct": 50.0,
    "soc_min_pct": 15.0,    # abaixo disso → estado crítico
    "soc_max_pct": 95.0,    # acima disso  → para de carregar
    "eficiencia": 0.92,

    # Pesos do reward cooperativo
    "w_custo": 1.0,
    "pen_soc": 10.0,        # violação SOC crítico
    "pen_teto": 5.0,        # consumo acima do teto
    "pen_producao": 8.0,    # corte de bomba de captação
    "bonus_excedente": 0.3, # kWh excedente (crédito)
    "bonus_soc_ok": 1.0,    # SOC entre 30 % e 80 %
}

# Tetos de consumo por decisão do Gerente de Carga
TETOS_KW = {0: 20.0, 1: 30.0, 2: 40.0}  # conservador / moderado / liberal
