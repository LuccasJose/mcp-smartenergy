DEFAULT_HYPERPARAMS = {
    "n_episodios": 1000,
    "alpha": 0.1,
    "gamma": 0.95,
    "beta": 0.01,
    "epsilon_inicial": 1.0,
    "epsilon_final": 0.05,
    "epsilon_decay": 0.995,
}

# Espaço de ações
N_ACOES_ARMAZENAMENTO = 3   # 0=carregar, 1=manter, 2=descarregar
N_ACOES_CONSUMO = 8         # 3 bits: pivô(1), bomba(2), secador(4)
N_ACOES_GERENTE = 3         # 0=conservador, 1=moderado, 2=liberal
N_ACOES_TOTAL = N_ACOES_ARMAZENAMENTO * N_ACOES_CONSUMO * N_ACOES_GERENTE  # 72

# Restrições físicas
PCC_LIMITE_KW = 65.8
SOC_MINIMO = 0.15
SOC_MAXIMO = 0.95
BATERIA_CAPACIDADE_KWH = 100.0
BATERIA_MAX_CARGA_KW = 30.0
BATERIA_MAX_DESCARGA_KW = 30.0
BATERIA_EF_CARGA = 0.95
BATERIA_EF_DESCARGA = 0.95
SOC_INICIAL = 0.50

# Tarifa (TOU brasileira)
HORAS_PICO = set(range(18, 21))  # 18h–20h
TARIFA_PICO = 0.85        # R$/kWh
TARIFA_FORA_PICO = 0.25   # R$/kWh

# Potências das cargas (kW)
PIVO_KW = 25.0
CAPTACAO_KW = 15.0
SEDE_KW = 3.0
SILO_KW_BASE = 4.0
SECADOR_KW = 20.0

# Watchdog: bomba deve operar ao menos N horas/dia
BOMBA_WATCHDOG_HORAS = 6

# Teto de geração por ação do gerente (kW)
GERENTE_TETO = {0: 20.0, 1: 35.0, 2: 55.0}

# Perfil solar (kW, dia claro, pico ~34 kW)
SOLAR_PERFIL = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    2.0, 8.0, 15.0, 22.0, 28.0, 32.0,
    34.0, 33.0, 30.0, 25.0, 18.0, 10.0,
    3.0, 0.0, 0.0, 0.0, 0.0, 0.0,
]

# Perfil eólico base (kW)
VENTO_PERFIL = [
    8.0, 9.0, 10.0, 10.0, 9.0, 8.0,
    7.0, 6.0, 5.0, 5.0, 4.0, 4.0,
    4.0, 5.0, 5.0, 6.0, 7.0, 8.0,
    9.0, 10.0, 10.0, 10.0, 9.0, 8.0,
]

# Pesos do reward
REWARD_PESO_CUSTO = 2.0
REWARD_PESO_REDE = 0.05
REWARD_PENALIDADE_PCC = 100.0
REWARD_PENALIDADE_SOC = 50.0
REWARD_BONUS_RENOVAVEL = 0.03
