"""Experimentos explicitos de particionamento que reutilizam o motor IQL."""

import copy
import hashlib
import json
from uuid import uuid4

import numpy as np
import pandas as pd

from . import runs
from .agents import AgentesHeuristicos, SemAgente, avaliar_politica, construir_agentes
from .config import ajustar_decay
from .data_splits import construir_divisoes, descrever_divisao, inicios_de_blocos
from .training import treinar


class PlanoDivisoes:
    """Snapshot em memoria; runs e manifesto persistidos ao executar.

    Uma seed de treino por divisao, sem LLM e sem alterar a politica ativa.
    Nao oferece isolamento concorrente do RNG global usado pelo motor legado.
    """

    def __init__(
        self, dias, tarifa, cfg, fonte, metodos, *, n_episodios=500,
        seed_treino=42, seed_divisao=42, fracao_treino=0.7,
        fracao_validacao=0.15, bloco_dias=7, n_janelas=3,
        intervalo_avaliacao=100, dia_fim_treino=24, dia_fim_validacao=27,
    ):
        if n_episodios < 1 or intervalo_avaliacao < 1:
            raise ValueError("Episodios e intervalo de avaliacao devem ser positivos.")
        if not 0 <= seed_treino < 2**32:
            raise ValueError("Seed de treino deve estar entre 0 e 2**32-1.")
        self.parametros = dict(
            fracao_treino=fracao_treino, fracao_validacao=fracao_validacao,
            seed_divisao=seed_divisao, bloco_dias=bloco_dias, n_janelas=n_janelas,
            dia_fim_treino=dia_fim_treino, dia_fim_validacao=dia_fim_validacao,
        )
        self.divisoes = construir_divisoes(dias, metodos, **self.parametros)
        self.dias = [dia.copy(deep=True) for dia in dias]
        self.tarifa = np.asarray(tarifa, dtype=float).copy()
        if self.tarifa.shape != (24,) or not np.isfinite(self.tarifa).all():
            raise ValueError("Tarifa deve conter 24 valores finitos.")
        self.cfg = ajustar_decay(copy.deepcopy(cfg), n_episodios)
        self.cfg["soc_inicial_pct"] = 50.0
        self.fonte = copy.deepcopy(fonte)
        self.seed_treino = seed_treino
        self.intervalo_avaliacao = min(intervalo_avaliacao, n_episodios)
        self.id = uuid4().hex
        digest = hashlib.sha256()
        for dia in self.dias:
            digest.update(str(tuple(zip(dia.columns, map(str, dia.dtypes)))).encode())
            digest.update(pd.util.hash_pandas_object(dia, index=False).values.tobytes())
        digest.update(self.tarifa.tobytes())
        self.hash_dados = digest.hexdigest()
        self.resultados = {}
        self.politicas = {}
        self.teste_aberto = False

    def resumo(self):
        return copy.deepcopy({
            "plano_id": self.id,
            "protocolo": "divisoes_v1",
            "metodos": list(dict.fromkeys(divisao.metodo for divisao in self.divisoes)),
            "n_treinamentos": len(self.divisoes),
            "n_episodios_por_treino": self.cfg["n_episodios"],
            "n_episodios_total": self.cfg["n_episodios"] * len(self.divisoes),
            "seed_treino": self.seed_treino,
            "intervalo_avaliacao": self.intervalo_avaliacao,
            "parametros": self.parametros,
            "config": self.cfg,
            "fonte": self.fonte,
            "hash_dados": self.hash_dados,
            "soc_inicial_blocos_pct": 50.0,
            "teste_aberto": self.teste_aberto,
            "divisoes": [descrever_divisao(divisao, self.dias) for divisao in self.divisoes],
            "resultados": self.resultados,
        })

    def _divisao(self, identificador):
        for divisao in self.divisoes:
            if divisao.identificador == identificador:
                return divisao
        raise ValueError("Divisao nao pertence aos metodos selecionados neste plano.")

    def _avaliar(self, agentes, indices):
        dias = [self.dias[indice] for indice in indices]
        inicios = inicios_de_blocos(dias)

        def escolher_rl(env, estado):
            discreto = env.discretizar(estado)
            return tuple(int(np.argmax(agentes[nome].q_table.get(
                discreto, np.zeros(agentes[nome].n_acoes),
            ))) for nome in ("armazenamento", "consumo", "gerente"))

        heuristico = AgentesHeuristicos(self.cfg)
        sem_agente = SemAgente(self.cfg)
        politicas = {
            "rl": escolher_rl,
            "heuristico": lambda env, estado: heuristico.agir(estado),
            "sem_agente": lambda env, estado: sem_agente.agir(estado),
        }
        return {nome: avaliar_politica(
            escolher, dias, self.tarifa, cfg=self.cfg, n_dias=len(dias),
            reiniciar_soc_em=inicios,
        ) for nome, escolher in politicas.items()}

    def _persistir(self):
        pasta = runs.RUNS_DIR.parent / "divisoes" / self.id
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / "plano.json"
        temporario = pasta / "plano.tmp"
        temporario.write_text(json.dumps(self.resumo(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(destino)

    def treinar_divisao(self, identificador, *, log=None):
        divisao = self._divisao(identificador)
        if identificador in self.resultados:
            return copy.deepcopy(self.resultados[identificador])
        if self.teste_aberto:
            raise ValueError("Plano congelado: o teste final ja foi aberto.")
        treino = [self.dias[indice] for indice in divisao.treino]
        validacao = [self.dias[indice] for indice in divisao.validacao]
        estado_rng = np.random.get_state()
        try:
            np.random.seed(self.seed_treino)
            agentes = construir_agentes(self.cfg)
            historico = treinar(
                treino, self.tarifa, agentes, self.cfg, log=log,
                dias_selecao=validacao, eval_greedy_cada=self.intervalo_avaliacao,
                reiniciar_soc_treino_em=inicios_de_blocos(treino),
                reiniciar_soc_selecao_em=inicios_de_blocos(validacao),
            )
            metricas = self._avaliar(agentes, divisao.validacao)
        finally:
            np.random.set_state(estado_rng)
        protocolo = {
            "versao": "divisoes_v1", "plano_id": self.id,
            "divisao": descrever_divisao(divisao, self.dias),
            "parametros": self.parametros, "hash_dados": self.hash_dados,
            "seed_treino": self.seed_treino,
            "soc_inicial_blocos_pct": 50.0, "fonte": self.fonte,
            "intervalo_avaliacao": self.intervalo_avaliacao,
        }
        historico["protocolo_divisao"] = protocolo
        run_id = runs.salvar_run(
            agentes, historico, run_id=f"{runs.novo_run_id()}_div_{self.id}_{identificador}",
            fonte_dados=self.fonte.get("fonte", "dataset ativo"), definir_como_latest=False,
        )
        resultado = {"run_id": run_id, "best_ep": historico["best_ep"],
                     "validacao": metricas, "teste": None}
        runs.atualizar_meta(run_id, protocolo_divisao=protocolo, resultado_divisao=resultado)
        self.politicas[identificador] = agentes
        self.resultados[identificador] = resultado
        self._persistir()
        return copy.deepcopy(resultado)

    def avaliar_teste(self, identificador, *, confirmar=False):
        divisao = self._divisao(identificador)
        if not confirmar:
            raise ValueError("O teste final exige confirmacao explicita.")
        if len(self.resultados) != len(self.divisoes):
            raise ValueError("Conclua todos os treinos selecionados antes de abrir o teste.")
        resultado = self.resultados[identificador]
        if resultado["teste"] is None:
            self.teste_aberto = True
            self._persistir()
            resultado["teste"] = self._avaliar(self.politicas[identificador], divisao.teste)
            runs.atualizar_meta(resultado["run_id"], resultado_divisao=resultado)
            self._persistir()
        return copy.deepcopy(resultado)