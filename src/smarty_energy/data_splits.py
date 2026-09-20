"""Particoes por dias completos, sem executar ou modificar o motor de RL."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


METODOS = ("cronologico", "aleatorio", "sazonal", "progressivo", "mensal_fixo")


@dataclass(frozen=True)
class Divisao:
    metodo: str
    janela: int
    treino: tuple[int, ...]
    validacao: tuple[int, ...]
    teste: tuple[int, ...]

    @property
    def identificador(self) -> str:
        return f"{self.metodo}_{self.janela}"


def datas_dos_dias(dias) -> tuple[pd.Timestamp, ...]:
    """Exige dias completos, unicos e ordenados, de uma unica base/fazenda."""
    datas = []
    for dia in dias:
        if len(dia) != 24 or list(dia["hora"]) != list(range(24)):
            raise ValueError("Cada dia deve conter as 24 horas, em ordem e sem duplicatas.")
        coluna = pd.to_datetime(dia["data"], errors="raise")
        normalizada = coluna.dt.normalize()
        if normalizada.isna().any() or normalizada.nunique() != 1:
            raise ValueError("Cada DataFrame deve conter uma unica data valida.")
        datas.append(normalizada.iloc[0])
    if not datas or datas != sorted(set(datas)):
        raise ValueError("Os dias devem ser unicos e estar em ordem cronologica.")
    return tuple(datas)


def inicios_de_blocos(dias) -> frozenset[int]:
    datas = datas_dos_dias(dias)
    return frozenset(
        indice for indice, data in enumerate(datas)
        if indice == 0 or data - datas[indice - 1] != pd.Timedelta(days=1)
    )


def _tamanhos(total: int, treino: float, validacao: float) -> tuple[int, int]:
    n_treino = max(1, int(total * treino))
    n_validacao = max(1, int(total * validacao))
    if n_treino + n_validacao >= total:
        raise ValueError("Dados insuficientes para tres conjuntos nao vazios.")
    return n_treino, n_validacao


def construir_divisoes(
    dias, metodos, *, fracao_treino: float = 0.7,
    fracao_validacao: float = 0.15, seed_divisao: int = 42,
    bloco_dias: int = 7, n_janelas: int = 3,
    dia_fim_treino: int = 24, dia_fim_validacao: int = 27,
) -> tuple[Divisao, ...]:
    """Constroi somente os metodos explicitamente selecionados.

    Sazonal estratifica blocos contiguos por ano/trimestre civil. Progressivo
    expande o treino e usa validacoes sucessivas, com o mesmo teste final
    reservado em todas as janelas. Dias intermediarios podem ficar sem uso.
    Mensal fixo usa cortes inclusivos por dia do calendario, sem proporcoes
    ou sorteio; cada mes/ano presente deve ter amostras nos tres conjuntos.
    """
    if isinstance(metodos, str) or not metodos:
        raise ValueError("Selecione uma lista nao vazia de metodos.")
    if len(set(metodos)) != len(metodos) or set(metodos) - set(METODOS):
        raise ValueError("Metodos desconhecidos ou repetidos.")
    usa_proporcoes = any(metodo != "mensal_fixo" for metodo in metodos)
    if usa_proporcoes and not (0 < fracao_treino < 1 and 0 < fracao_validacao < 1
                              and fracao_treino + fracao_validacao < 1):
        raise ValueError("Fracoes devem ser positivas e reservar dados para teste.")
    if "mensal_fixo" in metodos and (
        type(dia_fim_treino) is not int or type(dia_fim_validacao) is not int
        or not 1 <= dia_fim_treino < dia_fim_validacao <= 30
    ):
        raise ValueError("Cortes mensais devem ser inteiros: 1 <= fim do treino < fim da validacao <= 30.")
    if bloco_dias < 1 or n_janelas < 1 or seed_divisao < 0:
        raise ValueError("Bloco/janelas devem ser positivos e seed nao negativa.")
    datas = datas_dos_dias(dias)
    if usa_proporcoes:
        n_treino, n_validacao = _tamanhos(len(datas), fracao_treino, fracao_validacao)
    indices = tuple(range(len(datas)))
    divisoes = []

    for metodo in metodos:
        if metodo in ("cronologico", "aleatorio"):
            ordem = indices if metodo == "cronologico" else tuple(
                int(indice) for indice in np.random.default_rng(seed_divisao).permutation(len(datas))
            )
            divisoes.append(Divisao(
                metodo, 1, tuple(sorted(ordem[:n_treino])),
                tuple(sorted(ordem[n_treino:n_treino + n_validacao])),
                tuple(sorted(ordem[n_treino + n_validacao:])),
            ))
        elif metodo == "mensal_fixo":
            meses = {}
            for indice, data in enumerate(datas):
                grupos = meses.setdefault((data.year, data.month), [[], [], []])
                destino = 0 if data.day <= dia_fim_treino else (
                    1 if data.day <= dia_fim_validacao else 2
                )
                grupos[destino].append(indice)
            conjuntos = [[], [], []]
            for (ano, mes), grupos in meses.items():
                if not all(grupos):
                    raise ValueError(
                        f"Mes {ano:04d}-{mes:02d} sem dias de treino, validacao ou teste "
                        "para os cortes mensais informados."
                    )
                for conjunto, grupo in zip(conjuntos, grupos):
                    conjunto.extend(grupo)
            divisoes.append(Divisao(metodo, 1, *(tuple(grupo) for grupo in conjuntos)))
        elif metodo == "sazonal":
            grupos = {}
            for indice, data in enumerate(datas):
                grupos.setdefault((data.year, data.quarter), []).append(indice)
            conjuntos = [[], [], []]
            rng = np.random.default_rng(seed_divisao)
            for grupo in grupos.values():
                blocos = []
                for indice in grupo:
                    if (not blocos or len(blocos[-1]) == bloco_dias
                            or datas[indice] - datas[blocos[-1][-1]] != pd.Timedelta(days=1)):
                        blocos.append([])
                    blocos[-1].append(indice)
                qtd_treino, qtd_validacao = _tamanhos(len(blocos), fracao_treino, fracao_validacao)
                ordem = rng.permutation(len(blocos))
                for posicao, indice_bloco in enumerate(ordem):
                    destino = 0 if posicao < qtd_treino else (
                        1 if posicao < qtd_treino + qtd_validacao else 2
                    )
                    conjuntos[destino].extend(blocos[int(indice_bloco)])
            divisoes.append(Divisao(metodo, 1, *(tuple(sorted(grupo)) for grupo in conjuntos)))
        else:
            primeiro_treino = n_treino - (n_janelas - 1) * n_validacao
            if primeiro_treino < 1:
                raise ValueError("Janelas progressivas demais para a fracao de treinamento.")
            for janela in range(n_janelas):
                fim_treino = primeiro_treino + janela * n_validacao
                divisoes.append(Divisao(
                    metodo, janela + 1, indices[:fim_treino],
                    indices[fim_treino:fim_treino + n_validacao],
                    indices[n_treino + n_validacao:],
                ))
    return tuple(divisoes)


def descrever_divisao(divisao: Divisao, dias) -> dict:
    datas = datas_dos_dias(dias)
    resumo = {"id": divisao.identificador, "metodo": divisao.metodo, "janela": divisao.janela}
    usados = set()
    for nome in ("treino", "validacao", "teste"):
        indices = getattr(divisao, nome)
        usados.update(indices)
        blocos = []
        for indice in indices:
            data = datas[indice]
            if not blocos or data - pd.Timestamp(blocos[-1]["fim"]) != pd.Timedelta(days=1):
                blocos.append({"inicio": data.isoformat(), "fim": data.isoformat(), "dias": 1})
            else:
                blocos[-1]["fim"] = data.isoformat()
                blocos[-1]["dias"] += 1
        resumo[nome] = {"n_dias": len(indices), "blocos": blocos}
    resumo["dias_nao_utilizados"] = len(datas) - len(usados)
    return resumo