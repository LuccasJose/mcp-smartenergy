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
    "n_episodios": 6000,    # dias simulados no treino
    "alpha": 0.1,           # taxa de aprendizado
    "gamma": 0.98,          # fator de desconto futuro
    "epsilon_inicial": 1.0, # exploração inicial (100 %)
    "epsilon_final": 0.01,  # exploração mínima  (5 %)
    "epsilon_decay": 0.9985,# decaimento por episódio

    # Bateria
    "bateria_cap_kwh": 24.0,
    "soc_inicial_pct": 50.0,
    "soc_min_pct": 15.0,        # abaixo disso → estado crítico
    "soc_max_pct": 95.0,        # acima disso  → para de carregar
    "eficiencia_carga": 0.92,   # η carga
    "eficiencia_descarga": 0.95, # η descarga
    "bat_throughput_max_kwh": 48.0,  # ciclo máximo diário (kWh)

    # Limites de conexão e geração
    "pcc_max_kw": 65.8,          # limite PCC importação/exportação
    "inversor_fv_max_kw": 50.0,  # teto do inversor fotovoltaico
    "eolico_nominal_kw": 10.0,   # potência nominal do aerogerador

    # Pesos do reward cooperativo
    # Referência: custo pico ≈ 30 kW × R$1,10 = R$33/h → penalidades na mesma ordem
    "w_custo": 1.5,
    "pen_soc": 30.0,        # violação SOC crítico    (era 10)
    "pen_teto": 15.0,       # consumo acima do teto   (era  5)
    "pen_producao": 10.0,   # corte de bomba captação (era  8)
    "pen_pcc": 20.0,        # violação do limite PCC  (era  8)
    "bonus_excedente": 0.2, # fator sobre tarifa vigente — convertido para R$ no step() (era 0.3 kWh)
    "bonus_soc_ok": 5.0,    # SOC entre 30 % e 80 %  (era  1)
}

# Tetos de consumo por decisão do Gerente de Carga
TETOS_KW = {0: 20.0, 1: 30.0, 2: 40.0}  # conservador / moderado / liberal
