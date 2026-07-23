"""
Configuração do MCP SmartEnergy — espelha o projeto Smart_Energy (FAZ-002).

CONFIG       : dict com hiperparâmetros do treino, parâmetros físicos da fazenda,
               pesos do reward cooperativo e penalidades operacionais.
TETOS_KW     : tetos de consumo por decisão do Gerente de Carga.
BOMBA_HORAS_ON: cronograma fixo da bomba de captação (4 ciclos de 2h).
"""

import os

# ─── Fonte de dados ────────────────────────────────────────────────
# Por padrão usa o SHEET_ID do projeto Smart_Energy (planilha pública).
# Pode ser sobrescrito via variável de ambiente.
SHEET_ID = os.getenv("SHEET_ID", "1sjs2XLNEZp2oPxm_YLwsX9DxPxIfks32")

# Fazenda usada — a base traz FAZ-001 e FAZ-002.
ID_FAZENDA = os.getenv("ID_FAZENDA", "FAZ-002")

# ─── Hiperparâmetros e parâmetros físicos ──────────────────────────
CONFIG = {
    # Treinamento
    "n_episodios": 1000,    # default reduzido (Smart_Energy usa 100000)
    "alpha": 0.1,
    "beta": 0.01,           # taxa pessimista (Hysteretic Q-learning)
    "gamma": 0.98,
    "epsilon_inicial": 1.0,
    "epsilon_final": 0.01,
    "epsilon_decay": 0.995, # default reduzido para 1k episódios

    # Bateria
    "bateria_cap_kwh": 24.0,
    "soc_inicial_pct": 50.0,
    "soc_min_pct": 15.0,
    "soc_max_pct": 95.0,
    "eficiencia_carga": 0.92,
    "eficiencia_descarga": 0.95,
    "bat_throughput_max_kwh": 48.0,

    # Limites de conexão e geração
    "pcc_max_kw": 65.8,
    "inversor_fv_max_kw": 50.0,
    "eolico_nominal_kw": 10.0,

    # Financeiro
    "credito_inicial_kwh": 100.0,
    "tarifa_estresse_limiar": 0.9,

    # Metas operacionais
    "pivo_horas_alvo": 8,
    "pivo_nominal_kw": 3.0,
    "bomba_cap_nominal_kw": 15.0,
    "secador_meta_kwh": 20.0,
    "sede_desvio_max": 0.20,

    # Pesos do reward cooperativo
    "w_custo": 8.0,
    "w_estresse": 0.5,
    "w_bonus_carga": 1.2,
    "pen_soc": 12.0,
    "pen_teto": 8.0,
    "pen_producao": 5.0,
    "pen_pcc": 10.0,
    "bonus_excedente": 0.5,
    "bonus_soc_ok": 1.0,

    # Penalidades operacionais
    "pen_secador_meta": 20.0,
    "pen_sede_desvio": 5.0,

    # Shaping por ponto ótimo
    "pen_pivo_pico":       18.0,
    "pen_secador_pico":    8.0,
    "bonus_pivo_solar":    3.0,
    "bonus_sec_excedente": 2.0,
}

# Tetos de consumo por decisão do Gerente
TETOS_KW = {0: 20.0, 1: 30.0, 2: 40.0}

# Cronograma fixo da bomba (4 ciclos × 2h, evitando pico 18-20h)
BOMBA_HORAS_ON = frozenset({0, 1, 6, 7, 12, 13, 21, 22})

# Espaços de ação
N_ACOES_ARMAZENAMENTO = 3   # 0=carregar, 1=manter, 2=descarregar
N_ACOES_CONSUMO       = 8   # bitmask 3 bits: pivo(1), bomba(2), secador(4)
N_ACOES_GERENTE       = 3   # 0=conservador, 1=moderado, 2=liberal

# Espaço de estados (deve refletir FazendaEnergyEnv.discretizar)
# hora(4) × soc(10) × solar(3) × stress(3) × meta_sec(2) × bomba(3) = 2160
N_ESTADOS_TOTAL = 4 * 10 * 3 * 3 * 2 * 3

# Retro-compat com a versão anterior do MCP — mapeia para CONFIG.
DEFAULT_HYPERPARAMS = {
    "n_episodios": CONFIG["n_episodios"],
    "alpha": CONFIG["alpha"],
    "gamma": CONFIG["gamma"],
    "beta": CONFIG["beta"],
    "epsilon_inicial": CONFIG["epsilon_inicial"],
    "epsilon_final": CONFIG["epsilon_final"],
    "epsilon_decay": CONFIG["epsilon_decay"],
}
