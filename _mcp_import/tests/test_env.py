"""Invariantes fisicos e comportamentais do FazendaEnergyEnv."""

from config import BOMBA_HORAS_ON, TETOS_KW


# --- reset / step basicos ---------------------------------------------------

def test_reset_retorna_estado_valido(env, cfg):
    est = env.reset()
    assert est["hora"] == 0
    assert est["soc"] == cfg["soc_inicial_pct"]
    for k in ("hora", "soc", "solar_kw", "eolico_kw", "tarifa", "stress",
              "sec_ac", "bomba_h", "em_pico_tarifa", "saldo_creditos_kwh"):
        assert k in est, f"campo {k} faltando em estado"


def test_reset_aceita_soc_inicial(env):
    est = env.reset(soc_inicial=42.5)
    assert est["soc"] == 42.5


def test_step_retorna_tupla(env):
    env.reset()
    saida = env.step(1, 0, 1)
    assert len(saida) == 4
    obs, reward, done, info = saida
    assert isinstance(obs, dict)
    assert isinstance(reward, float)
    assert isinstance(done, bool)
    assert isinstance(info, dict)


def test_done_so_apos_24_passos(env):
    env.reset()
    for h in range(23):
        _, _, done, _ = env.step(1, 0, 1)
        assert done is False, f"done=True na hora {h}, esperado False"
    _, _, done, _ = env.step(1, 0, 1)
    assert done is True


def test_step_avanca_hora_e_zera_no_dia(env):
    env.reset()
    for h in range(24):
        prox, _, done, info = env.step(1, 0, 1)
        assert info["hora"] == h
        if h < 23:
            assert prox["hora"] == h + 1


# --- restricoes fisicas -----------------------------------------------------

def test_soc_sempre_em_0_100(env):
    env.reset()
    for _ in range(24):
        _, _, done, info = env.step(2, 0, 2)  # descarregar agressivo
        assert 0.0 <= info["soc"] <= 100.0
        if done: break


def test_pcc_nunca_excede_limite(env, cfg):
    env.reset()
    for _ in range(24):
        # acao liberal para gerar muito consumo e tentar exceder PCC
        _, _, done, info = env.step(1, 0, 2)
        assert info["importacao"] <= cfg["pcc_max_kw"] + 1e-9
        assert info["exportacao"] <= cfg["pcc_max_kw"] + 1e-9
        if done: break


def test_throughput_diario_respeitado(env, cfg):
    env.reset()
    for _ in range(24):
        _, _, done, _ = env.step(0, 0, 1)  # sempre carregar
        if done: break
    assert env.bat_throughput_dia <= cfg["bat_throughput_max_kwh"] + 1e-9


# --- restricoes HARD por carga ---------------------------------------------

def test_bomba_schedule_fixo(env):
    """Bomba liga exatamente nas horas em BOMBA_HORAS_ON, independente da acao."""
    env.reset()
    horas_bomba_observadas = set()
    for h in range(24):
        # acao 'a_cons=2' tenta CORTAR bomba — env deve ignorar e ligar de toda forma
        _, _, done, info = env.step(1, 2, 1)
        if info["bomba_ligada"]:
            horas_bomba_observadas.add(h)
        if done: break
    assert horas_bomba_observadas == BOMBA_HORAS_ON


def test_pivo_apenas_uma_ativacao_de_8h(env, cfg):
    """Pivo so pode ser ativado uma vez por dia, e fica ON por 8h consecutivas."""
    env.reset()
    pivo_horas = []
    for h in range(24):
        # acao 'a_cons=1' tenta cortar pivo — env decide ativar quando for hora
        _, _, done, info = env.step(1, 1, 1)
        if not info.get("pivo_em_lock", False):
            pass  # nao em lock
        if info["pivo_kw_consumido"] > 0:
            pivo_horas.append(h)
        if done: break
    # se ativou, deve ter exatamente 8h consecutivas
    if pivo_horas:
        assert len(pivo_horas) == cfg["pivo_horas_alvo"]
        for i in range(1, len(pivo_horas)):
            assert pivo_horas[i] == pivo_horas[i-1] + 1


def test_sede_clamp_pm_20pct(env, cfg):
    """Sede real fica em [0.8, 1.2] * sede_ideal."""
    env.reset()
    sede_ideal = 1.0  # vem do dia_fake
    lo, hi = sede_ideal * (1 - cfg["sede_desvio_max"]), sede_ideal * (1 + cfg["sede_desvio_max"])
    for _ in range(24):
        _, _, done, info = env.step(1, 0, 1)
        assert lo - 1e-9 <= info["sede_kw_consumido"] <= hi + 1e-9
        if done: break


def test_secador_atinge_meta_diaria(env, cfg):
    """Mesmo o agente tentando cortar (a_cons=4), o rescue tardio deve fazer
    o secador atingir a meta diaria de 20 kWh."""
    env.reset()
    for _ in range(24):
        _, _, done, info = env.step(1, 4, 1)  # bit2 = corta secador
        if done: break
    assert env.secador_kwh_ac >= cfg["secador_meta_kwh"] - 1e-6


# --- reward responde a pesos -----------------------------------------------

def test_reward_zera_quando_todos_pesos_zerados(dia_fake, tarifa_fake, cfg):
    """Sanity: se todos os pesos sao 0 e nao ha violacao, reward deve ser 0."""
    from environment.energy_env import FazendaEnergyEnv

    cfg_zero = dict(cfg)
    for k in ("w_custo", "w_estresse", "pen_soc", "pen_teto", "pen_pcc",
              "pen_producao", "pen_secador_meta", "pen_pivo_pico",
              "pen_secador_pico", "bonus_excedente", "bonus_soc_ok",
              "bonus_pivo_solar", "bonus_sec_excedente", "w_bonus_carga"):
        cfg_zero[k] = 0.0

    env_zero = FazendaEnergyEnv(dia_fake, tarifa_fake, cfg_zero)
    env_zero.reset()
    soma_reward = 0.0
    for _ in range(24):
        _, r, done, _ = env_zero.step(1, 0, 1)
        soma_reward += r
        if done: break
    assert abs(soma_reward) < 1e-6, f"reward deveria ser 0, foi {soma_reward}"


# --- discretizacao ----------------------------------------------------------

def test_discretizar_retorna_tupla_6(env):
    est = env.reset()
    d = env.discretizar(est)
    assert isinstance(d, tuple)
    assert len(d) == 6


def test_discretizar_buckets_extremos(env):
    """SOC=100 deve cair no ultimo bucket (9), nao em 10."""
    est = env.reset(soc_inicial=100.0)
    h, s, g, st, meta, b = env.discretizar(est)
    assert 0 <= s <= 9
    assert s == 9
