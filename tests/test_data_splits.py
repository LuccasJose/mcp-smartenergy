import itertools

import numpy as np
import pandas as pd
import pytest

from smarty_energy.data_splits import (
    METODOS, construir_divisoes, datas_dos_dias, descrever_divisao, inicios_de_blocos,
)


@pytest.fixture(scope="module")
def ano():
    return [pd.DataFrame({"data": data, "hora": range(24)})
            for data in pd.date_range("2025-01-01", "2025-12-31")]


@pytest.mark.parametrize("metodos", [
    combinacao for tamanho in range(1, len(METODOS) + 1)
    for combinacao in itertools.combinations(METODOS, tamanho)
])
def test_selecao_explicita_sem_sobreposicao(ano, metodos):
    divisoes = construir_divisoes(ano, metodos)
    assert {divisao.metodo for divisao in divisoes} == set(metodos)
    assert len(divisoes) == len(metodos) + (2 if "progressivo" in metodos else 0)
    for divisao in divisoes:
        grupos = [set(getattr(divisao, nome)) for nome in ("treino", "validacao", "teste")]
        assert all(grupos)
        assert all(not primeiro & segundo for primeiro, segundo in itertools.combinations(grupos, 2))
        for nome in ("treino", "validacao", "teste"):
            assert tuple(sorted(getattr(divisao, nome))) == getattr(divisao, nome)
        if divisao.metodo != "progressivo":
            assert set.union(*grupos) == set(range(365))


def test_cronologico_e_janelas_reservam_futuro(ano):
    simples, *janelas = construir_divisoes(ano, ["cronologico", "progressivo"])
    assert tuple(map(len, (simples.treino, simples.validacao, simples.teste))) == (255, 54, 56)
    for divisao in (simples, *janelas):
        assert max(divisao.treino) < min(divisao.validacao)
        assert max(divisao.validacao) < min(divisao.teste)
        assert divisao.teste == simples.teste
    assert set(janelas[0].treino) < set(janelas[1].treino) < set(janelas[2].treino)
    assert janelas[-1].treino == simples.treino
    assert not set(janelas[0].validacao) & set(janelas[1].validacao)


def test_sazonal_preserva_blocos_e_cobre_trimestres(ano):
    divisao, = construir_divisoes(ano, ["sazonal"])
    datas = datas_dos_dias(ano)
    destinos = {indice: nome for nome in ("treino", "validacao", "teste")
                for indice in getattr(divisao, nome)}
    for trimestre in range(1, 5):
        indices = [indice for indice, data in enumerate(datas) if data.quarter == trimestre]
        assert {destinos[indice] for indice in indices} == {"treino", "validacao", "teste"}
        for inicio in range(0, len(indices), 7):
            assert len({destinos[indice] for indice in indices[inicio:inicio + 7]}) == 1


def test_seed_divisao_reprodutivel_sem_alterar_rng_global(ano):
    np.random.seed(19)
    estado = np.random.get_state()
    primeira = construir_divisoes(ano, ["aleatorio", "sazonal"], seed_divisao=42)
    segunda = construir_divisoes(ano, ["sazonal", "aleatorio"], seed_divisao=42)
    assert primeira == tuple(reversed(segunda))
    assert primeira != construir_divisoes(ano, ["aleatorio", "sazonal"], seed_divisao=43)
    atual = np.random.get_state()
    np.testing.assert_array_equal(estado[1], atual[1])
    assert estado[2:] == atual[2:]


@pytest.mark.parametrize("metodos,opcoes", [
    ([], {}), (["inexistente"], {}), (["aleatorio", "aleatorio"], {}),
    (["cronologico"], {"fracao_treino": 0.9, "fracao_validacao": 0.2}),
    (["progressivo"], {"n_janelas": 99}), (["sazonal"], {"bloco_dias": 0}),
])
def test_rejeita_configuracoes_invalidas(ano, metodos, opcoes):
    with pytest.raises(ValueError):
        construir_divisoes(ano, metodos, **opcoes)


def test_rejeita_dias_incompletos_repetidos_e_desordenados(ano):
    for dias in ([ano[0].iloc[:-1]], [ano[0], ano[0]], [ano[1], ano[0]]):
        with pytest.raises(ValueError):
            datas_dos_dias(dias)


def test_blocos_e_resumo(ano):
    assert inicios_de_blocos([ano[0], ano[1], ano[4], ano[5]]) == {0, 2}
    divisao, = construir_divisoes(ano, ["cronologico"])
    resumo = descrever_divisao(divisao, ano)
    assert resumo["treino"]["n_dias"] == 255
    assert len(resumo["treino"]["blocos"]) == 1
    assert resumo["dias_nao_utilizados"] == 0


def test_mensal_fixo_padrao_e_blocos_soc(ano):
    divisao, = construir_divisoes(ano, ["mensal_fixo"])
    assert tuple(map(len, (divisao.treino, divisao.validacao, divisao.teste))) == (288, 36, 41)
    datas = datas_dos_dias(ano)
    for indices, minimo, maximo in (
        (divisao.treino, 1, 24), (divisao.validacao, 25, 27), (divisao.teste, 28, 31),
    ):
        assert all(minimo <= datas[indice].day <= maximo for indice in indices)
        assert {datas[indice].month for indice in indices} == set(range(1, 13))
        dias = [ano[indice] for indice in indices]
        inicios = inicios_de_blocos(dias)
        assert len(inicios) == 12
        assert all(dias[indice]["data"].iloc[0].day == minimo for indice in inicios)
    resumo = descrever_divisao(divisao, ano)
    assert resumo["dias_nao_utilizados"] == 0
    assert resumo["treino"]["blocos"][0]["fim"].startswith("2025-01-24")
    assert resumo["validacao"]["blocos"][0]["inicio"].startswith("2025-01-25")


@pytest.mark.parametrize("inicio,fim,n_teste", [
    ("2025-02-01", "2025-02-28", 1), ("2024-02-01", "2024-02-29", 2),
    ("2025-04-01", "2025-04-30", 3), ("2025-01-01", "2025-01-31", 4),
])
def test_mensal_fixo_respeita_fim_do_mes(inicio, fim, n_teste):
    dias = [pd.DataFrame({"data": data, "hora": range(24)}) for data in pd.date_range(inicio, fim)]
    divisao, = construir_divisoes(dias, ["mensal_fixo"])
    assert tuple(map(len, (divisao.treino, divisao.validacao, divisao.teste))) == (24, 3, n_teste)


def test_mensal_fixo_cortes_configuraveis_sem_seed_ou_proporcao(ano):
    primeira, = construir_divisoes(ano, ["mensal_fixo"], dia_fim_treino=20, dia_fim_validacao=25)
    segunda, = construir_divisoes(
        ano, ["mensal_fixo"], dia_fim_treino=20, dia_fim_validacao=25,
        seed_divisao=99, fracao_treino=0.99, fracao_validacao=0.99,
    )
    assert primeira == segunda
    assert tuple(map(len, (primeira.treino, primeira.validacao, primeira.teste))) == (240, 60, 65)
    amostra = [ano[indice] for indice in (0, 24, 27)]
    divisao, = construir_divisoes(amostra, ["mensal_fixo"])
    assert (divisao.treino, divisao.validacao, divisao.teste) == ((0,), (1,), (2,))


@pytest.mark.parametrize("treino,validacao", [(0, 27), (24, 24), (27, 24), (24, 31), (24.5, 27), (True, 27)])
def test_mensal_fixo_rejeita_cortes_invalidos(ano, treino, validacao):
    with pytest.raises(ValueError, match="Cortes mensais"):
        construir_divisoes(ano, ["mensal_fixo"], dia_fim_treino=treino, dia_fim_validacao=validacao)


def test_mensal_fixo_valida_cada_mes_e_ano_sem_redistribuir(ano):
    incompleto = [dia for dia in ano if not (dia["data"].iloc[0].month == 2 and dia["data"].iloc[0].day == 28)]
    with pytest.raises(ValueError, match="2025-02"):
        construir_divisoes(incompleto, ["mensal_fixo"])
    outro_ano = ano + [ano[0].assign(data=pd.Timestamp("2026-01-01"))]
    with pytest.raises(ValueError, match="2026-01"):
        construir_divisoes(outro_ano, ["mensal_fixo"])
    with pytest.raises(ValueError, match="2025-02"):
        construir_divisoes(ano, ["mensal_fixo"], dia_fim_treino=24, dia_fim_validacao=28)
    dois_anos = ano + [dia.assign(data=dia["data"] + pd.DateOffset(years=1)) for dia in ano]
    divisao, = construir_divisoes(dois_anos, ["mensal_fixo"])
    assert tuple(map(len, (divisao.treino, divisao.validacao, divisao.teste))) == (576, 72, 82)