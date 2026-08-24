import copy
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Caminhos resolvidos a partir da raiz do projeto
_ROOT = Path(__file__).resolve().parents[2]

# Fonte de dados — por padrão usa o arquivo local da base nova.
# Defina SHEET_ID (env) para baixar de um Google Sheets com o mesmo esquema.
SHEET_ID = os.getenv("SHEET_ID", "")

# Dataset Parquet gerado pelo FEMS (scripts/gerar_dataset.py --completo).
# Se definido, tem prioridade sobre SHEET_ID e o Excel local.
FEMS_DATASET_DIR = os.getenv("FEMS_DATASET_DIR", "")
# Mês da série FEMS a usar (1-12); 0 carrega o ano inteiro (365 dias).
FEMS_MES = int(os.getenv("FEMS_MES", "1"))

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
    "n_episodios": 100000,    # dias simulados no treino (cap para evitar drift IQL+hysteretic)
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
    "bat_throughput_max_kwh": 30.0,  # ciclo diário máx (~1.25 ciclos p/ vida útil realista)
    "potencia_max_carga_rede_kw": 24.0,
    "tarifa_referencia_arbitragem": 1.10,

    # Limites de conexão e geração
    "pcc_max_kw": 65.8,          # limite PCC importação/exportação
    "inversor_fv_max_kw": 50.0,  # teto do inversor fotovoltaico
    "eolico_nominal_kw": 10.0,   # potência nominal do aerogerador

    # Financeiro (Agente Financeiro)
    "credito_inicial_kwh": 100.0,
    "tarifa_estresse_limiar": 0.9, # R$/kWh acima disso é estresse alto

    # Metas Operacionais
    "pivo_horas_alvo": 8,           # duração do ciclo travado de irrigação
    "pivo_nominal_kw": 8.0,         # potência do pivô durante lock (Cons_Max V8 FAZ-002)
    "bomba_cap_nominal_kw": 17.6,   # potência da bomba durante hora agendada (Cons_Max V8 FAZ-002)
    "secador_meta_kwh": 20.0,       # meta diária de energia do secador
    "secador_max_kw": 2.4,          # potência máxima do secador (Cons_Max V8 FAZ-002)
    "sede_desvio_max": 0.20,        # 20%

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
    "bonus_descarga_pico": 0.5, # reforço leve por kWh AC da bateria entregue no pico
    "soc_reserva_pre_pico_pct": 60.0,
    "pen_reserva_pre_pico": 0.0,  # experimento; 0 desativa ate calibracao

    # Penalidades Operacionais (proporcionalmente reduzidas)
    "pen_secador_meta": 20.0,   # fallback se rescue não alcançar (defensivo)
    "pen_sede_desvio": 5.0,     # reservado para violações de clamp (defensivo)

    # Deslocamento constante da escala do reward (item 3 das verificações).
    # Horizonte fixo (24 passos) ⇒ somar constante a todo passo preservaria a
    # política ótima NUMA Q-table convergida. Na prática (treino finito +
    # seleção de checkpoint), o offset muda a dinâmica do hysteretic e o efeito
    # NÃO é monotônico — medido em holdout, 8k ep, 3 sementes:
    #   offset   0 → R$60,0/dia · |Q|≈8
    #   offset  60 → R$56,8/dia · |Q|≈107   (melhor: centra a média em ~0)
    #   offset 160 → R$67,6/dia · |Q|≈814   (pior: α domina, Q estoura)
    #   offset 200 → R$68,3/dia · |Q|≈1340  (pior ainda)
    # Ou seja: centrar a média perto de 0 ajuda (~5%); tornar TUDO positivo
    # atrapalha. Default 0.0 mantém o comportamento histórico — mude para ~60
    # apenas com re-treino e re-validação (muda o número oficial). NÃO altera o
    # custo em R$ (medido em `custo_r`, à parte do reward).
    "reward_offset": 0.0,

    # Shaping por ponto ótimo de cada máquina
    "pen_pivo_pico"      : 18.0, # pivô ligado em pico tarifário
    "pen_secador_pico"   : 8.0,  # secador ligado em pico tarifário (carga menor)
    "bonus_pivo_solar"   : 3.0,  # pivô operando em janela solar forte (≥15 kW)
    "bonus_sec_excedente": 2.0,  # secador com excedente de geração (≥5 kW após fixo)
}

# Tetos de consumo por decisão do Gerente de Carga
TETOS_KW = {0: 20.0, 1: 30.0, 2: 40.0}  # conservador / moderado / liberal

# Cronograma fixo da bomba — 4 ciclos de 2h igualmente espaçados (6h),
# evitando o pico tarifário (18-20h). Horas ON: 3-4, 9-10, 15-16, 21-22.
BOMBA_HORAS_ON = frozenset({3, 4, 9, 10, 15, 16, 21, 22})

# ──────────────────────────────────────────────────────────────
# Espaços de ação — fonte única (agentes, servidor MCP e schema das tools)
# ──────────────────────────────────────────────────────────────
FRACOES_DESCARGA = {2: 0.25, 3: 0.50, 4: 1.00}
ACAO_CARREGAR_REDE = 5
N_ACOES_ARMAZENAMENTO = 6   # 0=solar, 1=manter, 2/3/4=25/50/100%, 5=rede
N_ACOES_CONSUMO       = 8   # bitmask 3 bits: pivô(1), bomba(2), secador(4)
N_ACOES_GERENTE       = 3   # 0=conservador, 1=moderado, 2=liberal


def ajustar_decay(cfg: dict = CONFIG, n_episodios: int = None) -> dict:
    """Copia `cfg` para um treino de `n_episodios`, reescalando o decaimento de ε.

    O `epsilon_decay` do CONFIG é calibrado para o treino longo do pipeline
    (100.000 episódios). Em treinos curtos — os do servidor MCP e os da suíte
    de testes — esse decaimento deixaria ε≈1.0 até o último episódio, ou seja,
    agentes praticamente aleatórios. Aqui ele é recalculado para que ε chegue
    perto de `epsilon_final` no fim do treino:

        decay = (ε_final / ε_inicial) ** (1 / n_episodios)

    Args:
        cfg          : config base (não é modificado — a cópia é profunda).
        n_episodios  : episódios do treino; se None, usa `cfg['n_episodios']`.

    Returns:
        Novo dict de config com `n_episodios` e `epsilon_decay` ajustados.
    """
    novo = copy.deepcopy(cfg)
    n = max(1, int(n_episodios if n_episodios is not None else novo["n_episodios"]))
    novo["n_episodios"] = n
    eps_i, eps_f = novo["epsilon_inicial"], novo["epsilon_final"]
    if eps_i > 0:
        novo["epsilon_decay"] = (eps_f / eps_i) ** (1.0 / n)
    return novo
