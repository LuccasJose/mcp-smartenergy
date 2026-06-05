import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Caminhos resolvidos a partir da raiz do projeto
_ROOT = Path(__file__).resolve().parents[2]

# Fonte de dados — por padrão usa o arquivo local da base nova.
# Defina SHEET_ID (env) para baixar de um Google Sheets com o mesmo esquema.
SHEET_ID = os.getenv("SHEET_ID", "")

# Base de dados local (contém FAZ-001 e FAZ-002)
DATA_PATH = _ROOT / os.getenv("DATA_PATH", "dados/modelo_gestao_energia_fazenda_v8.xlsx")
OUTPUT_DIR = _ROOT / os.getenv("OUTPUT_DIR", "outputs")

# Fazenda usada no modelo (a base nova traz duas: FAZ-001 e FAZ-002)
ID_FAZENDA = os.getenv("ID_FAZENDA", "FAZ-002")

# ──────────────────────────────────────────────────────────────
# Parâmetros globais — ajuste aqui antes de rodar
# ──────────────────────────────────────────────────────────────
CONFIG = {
    # Treinamento
    "n_episodios": 200000,    # dias simulados no treino (reduzido para testes rápidos)
    "alpha": 0.1,           # taxa de aprendizado
    "gamma": 0.98,          # fator de desconto futuro
    "epsilon_inicial": 1.0, # exploração inicial (100 %)
    "epsilon_final": 0.01,  # exploração mínima  (5 %)
    "epsilon_decay": 0.99993,# decaimento por episódio

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

    # Financeiro (Agente Financeiro)
    "credito_inicial_kwh": 100.0,
    "tarifa_estresse_limiar": 0.9, # R$/kWh acima disso é estresse alto

    # Metas Operacionais
    "pivo_horas_alvo": 8,           # duração do ciclo travado de irrigação
    "pivo_nominal_kw": 3.0,         # potência do pivô durante lock (override de dados)
    "bomba_cap_nominal_kw": 15.0,   # potência da bomba durante hora agendada (override de dados)
    "secador_meta_kwh": 20.0,
    "sede_desvio_max": 0.20,     # 20%

    # Pesos do reward cooperativo (rebalanceados — custo como sinal dominante)
    "w_custo": 8.0,         # peso do custo monetário no reward
    "w_estresse": 0.5,      # peso do estresse financeiro
    "w_bonus_carga": 1.2,   # bônus por carregar com excedente solar (aumentado para 1.2)
    "pen_soc": 12.0,        # penalidade por SOC crítico (rebalanceado: era 30, dominava o sinal)
    "pen_teto": 8.0,            # ↓ era 15: idem
    "pen_producao": 5.0,        # ↓ era 10
    "pen_pcc": 10.0,            # ↓ era 20
    "bonus_excedente": 0.5,     # ↑ era 0.2: mais incentivo para exportar energia
    "bonus_soc_ok": 1.0,        # ↓ era 5.0: evita que agentes "gamifiquem" o SOC

    # Penalidades Operacionais (proporcionalmente reduzidas)
    "pen_secador_meta": 20.0,   # fallback se rescue não alcançar (defensivo)
    "pen_sede_desvio": 5.0,     # reservado para violações de clamp (defensivo)

    # Shaping por ponto ótimo de cada máquina
    "pen_pivo_pico"      : 18.0, # pivô ligado em pico tarifário
    "pen_secador_pico"   : 8.0,  # secador ligado em pico tarifário (carga menor)
    "bonus_pivo_solar"   : 3.0,  # pivô operando em janela solar forte (≥15 kW)
    "bonus_sec_excedente": 2.0,  # secador com excedente de geração (≥5 kW após fixo)
}

# Tetos de consumo por decisão do Gerente de Carga
TETOS_KW = {0: 20.0, 1: 30.0, 2: 40.0}  # conservador / moderado / liberal

# Cronograma fixo da bomba — 4 ciclos de 2h espaçados 6h, evitando pico (18-20h)
BOMBA_HORAS_ON = frozenset({0, 1, 6, 7, 12, 13, 21, 22})
