# Relatório — O que falta para validar T1, T2 e T3

> **Escopo:** apenas os blocos **T1 (ambiente), T2 (treino Q-learning) e T3
> (validação do otimizador)** do Plano de Testes. Tudo relativo a **seeds**
> foi excluído a pedido (não entra em T2 nem aqui).
> **Base:** suíte atual `pytest -m "not slow"` → **36 passed, 1 deselected**
> (o teste desmarcado é o de reprodutibilidade por semente).
> **Natureza:** diagnóstico. Nenhum código foi alterado; cada apontamento é
> rastreável por `arquivo:linha`.

---

## Legenda de esforço

🟢 **baixo** — agregação/relatório sobre dados que o histórico já grava.
🟡 **médio** — novo teste ou métrica com decisão de formulação (P3).
🔴 **alto** — exige treino longo, varredura ou infraestrutura nova.

---

## Panorama

| Bloco | Situação | Lacunas | Bloqueia a defesa? |
|---|---|---|---|
| **T1** — física do ambiente | Forte | 2 (balanço completo, transição de SoC) | Não — completa a rede de segurança |
| **T2** — treino Q-learning | Parcial | 3 (cobertura, sanidade, convergência) | Parcial — cobertura é argumento do TCC |
| **T3** — validação otimizador | Parcial | métricas 4.1 + estatística pareada | **Sim** — é o experimento principal |

O insumo que mais destrava T3 (e parte de T1) é o **módulo de métricas 4.1**,
detalhado na seção própria abaixo — tudo derivável do histórico já existente.

---

## T1 — Verificação do ambiente

### O que já está validado ✅
`tests/test_constraints.py` roda **31 dias × 3 políticas** (heurística,
aleatória, manter) e verifica: SoC ∈ [0,100], PCC e não-simultaneidade
import/export, `fontes = consumo`, teto de consumo, throughput diário da
bateria, cronograma da bomba, janela de 8h do pivô, meta do secador e desvio
da sede. Cobertura sólida das restrições **HARD**.

### Lacuna T1.1 — Balanço energético completo 🟡
- **O plano pede** (bloco T1): a cada passo,
  `geração + importação + descarga = consumo + carga + exportação + corte`.
- **O que existe:** apenas o lado do suprimento —
  `fonte_geracao + fonte_bateria + fonte_rede = consumo`
  ([test_constraints.py:109-114](tests/test_constraints.py#L109-L114)).
- **O que falta:** um teste que feche a **identidade completa**, incluindo
  `bat_carga`, `exportacao` e `kwh_cortado` no lado do escoamento. Todas as
  parcelas já estão no histórico ([environment.py:320-346](src/smarty_energy/environment.py#L320-L346)):
  `geracao_kw, importacao, bat_descarga` × `consumo_kw, bat_carga, exportacao,
  kwh_cortado`. É escrever a asserção e definir a tolerância numérica.

### Lacuna T1.2 — Dinâmica/transição do SoC 🟡
- **O plano pede:** SoC nos limites (✅ já testado) **e** eficiências de
  carga/descarga aplicadas corretamente, com conservação entre passos.
- **O que existe:** só os limites ([test_constraints.py:77-80](tests/test_constraints.py#L77-L80),
  [test_environment.py:61-67](tests/test_environment.py#L61-L67)).
- **O que falta:** um teste da equação de transição —
  `SoC[t+1] ≈ SoC[t] + bat_carga·η_carga − bat_descarga/η_descarga`
  (usando `eficiencia_carga`/`eficiencia_descarga` do CONFIG). Prova que a
  bateria não "cria" energia. Dados já disponíveis (`soc, bat_carga, bat_descarga`).

> **Observação (fora do mínimo):** o "limite de exposição do grão" do secador é
> hoje penalidade *soft* (`pen_secador_pico`), não restrição rígida. Se o texto
> alegar teto rígido de exposição, precisaria virar um teste HARD — decisão de
> modelagem, não urgente.

---

## T2 — Verificação do treino Q-learning  *(seeds excluídos)*

### O que já existe ✅
- Treino grava `rewards / custos / epsilons` por episódio + `custo_final`,
  `best_ep` e `duracao_s` ([training.py:152-163](src/smarty_energy/training.py#L152-L163)).
- Contagem de estados distintos visitados por agente
  ([agents.py:55-58](src/smarty_energy/agents.py#L55-L58)).
- Sanidade parcial: RL supera "sem agente"
  ([test_resultados.py:87-92](tests/test_resultados.py#L87-L92)).

### Lacuna T2.1 — Cobertura do espaço de estados 🟢  *(alta prioridade argumentativa)*
- **O plano pede:** fração de estados discretos visitados no treino — estados
  nunca vistos são **o argumento que motiva a camada de julgamento**.
- **O que existe:** o *número* absoluto (`n_estados`), impresso durante o treino
  ([training.py:114](src/smarty_energy/training.py#L114)) mas **não** a fração.
- **O que falta:** dividir `n_estados` pelo total do espaço =
  **2160** estados (`bucket_hora 4 × soc 10 × solar 3 × stress 3 × meta 2 ×
  bomba 3`, conforme [environment.py:4-10](src/smarty_energy/environment.py#L4-L10)).
  Reportar a fração (e, idealmente, distinguir estados *alcançáveis* dos
  combinatoriamente impossíveis, ex.: hora × progresso da bomba). Cálculo trivial.

### Lacuna T2.2 — Sanidade "RL > política aleatória" 🟢
- **O plano pede:** política treinada supera a **aleatória** e o caso-base na
  validação; se não superar, há erro de formulação.
- **O que existe:** a política aleatória só aparece como *fixture de restrições*
  ([test_constraints.py:40-49](tests/test_constraints.py#L40-L49)), nunca como
  comparação de **desempenho**. RL > sem-agente já é testado; RL > aleatório não.
- **O que falta:** um teste que rode a política aleatória nos dias de validação
  e assevere custo/reward do RL melhor. Reutiliza `_rodar_aleatorio` e `resumo_mes`.

### Lacuna T2.3 — Convergência automatizada 🟡
- **O plano pede:** curva de recompensa com estabilização; variação da Q-table
  entre janelas abaixo de um limiar.
- **O que existe:** a curva é apenas **visual**; o early-stopping usa média móvel
  do custo internamente ([training.py:96-105](src/smarty_energy/training.py#L96-L105)),
  mas não há **verificação** exportada de convergência.
- **O que falta:** medir a estabilização (ex.: variação relativa da média móvel
  de reward nas últimas N janelas < limiar) e reportá-la como critério objetivo.

> **Fora do mínimo:** sensibilidade a hiperparâmetros (varredura de α, γ,
> decaimento de ε, granularidade) é 🔴 — varredura pesada; sugiro deixar para
> depois do núcleo T1–T3.

---

## T3 — Validação do otimizador (experimento principal)

### O que já existe ✅
- Protocolo C0/C1/RL nos mesmos 31 dias + tabela de economia
  ([test_resultados.py:42-78](tests/test_resultados.py#L42-L78)).
- **Wilcoxon pareado pronto para reúso** (sem scipy), com z, p-valor e
  tamanho de efeito `r` ([benchmark.py:59-105](src/smarty_energy/benchmark.py#L59-L105)),
  além de `custos_por_dia` / `rede_por_dia`
  ([benchmark.py:46-52](src/smarty_energy/benchmark.py#L46-L52)).

### Lacuna T3.1 — Métricas primárias 4.1 🟡  *(núcleo — ver seção dedicada)*
`resumo_mes` só devolve custo, rede, violações de SoC e reward
([evaluation.py:92-106](src/smarty_energy/evaluation.py#L92-L106)). Faltam
**autoconsumo, autossuficiência, pico de demanda, energia cortada, ciclos de
bateria e gap de otimalidade** — todas deriváveis (próxima seção).

### Lacuna T3.2 — Estatística pareada aplicada a T3 🟢
- **O plano pede:** comparação pareada por dia RL × cada baseline, com tamanho
  de efeito e IC 95% (não só p-valor).
- **O que existe:** `wilcoxon_pareado` montado, mas **aplicado só a RL×LLM**
  ([benchmark.py:199](src/smarty_energy/benchmark.py#L199)).
- **O que falta:** aplicá-lo a **RL×C0** e **RL×C1** sobre `custos_por_dia`
  (e sobre as demais métricas primárias). É orquestração, a função já existe.

### Lacuna T3.3 — Gap de otimalidade 🟢
- **Definição do plano (4.1):** `(custo_config − custo_heurístico)/custo_heurístico`.
- Calculável **sem MILP**, direto contra C1. O MILP (teto teórico) continua
  "forte recomendação", mas **não** é o mínimo — fica como peça separada.

### Lacuna T3.4 — Despacho qualitativo 🟢
- **O plano pede:** gráfico de despacho de um dia típico por configuração
  (geração, cargas, SoC, importação) para explicar *de onde vem o ganho*.
- Provavelmente já há material em `visualization.py`; falta confirmar que cobre
  o "dia típico por configuração" pedido em T3. (A confirmar — não bloqueia.)

---

## Seção dedicada — Métricas primárias 4.1 (o insumo central)

Todas deriváveis do histórico atual
([environment.py:320-346](src/smarty_energy/environment.py#L320-L346)). Sugestão:
um módulo novo `metrics.py` com uma função `metricas_dia(historico) -> dict`,
consumido por `resumo_mes`, pelo `benchmark` e pelos testes de T3.

| Métrica (4.1) | Fórmula proposta (P3) | Chaves do histórico | Esforço |
|---|---|---|---|
| Custo total | `Σ custo_r` | `custo_r` | ✅ já existe |
| **Autossuficiência** | `Σ(fonte_geracao+fonte_bateria) ÷ Σ consumo_kw` | `fonte_geracao_kwh, fonte_bateria_kwh, consumo_kw` | 🟢 |
| **Autoconsumo** | `(Σ geracao_kw − Σ exportacao − Σ kwh_cortado) ÷ Σ geracao_kw` | `geracao_kw, exportacao, kwh_cortado` | 🟢 |
| **Pico de demanda** | `max(importacao)` no dia | `importacao` | 🟢 |
| **Importada / Exportada / Cortada** | `Σ importacao`, `Σ exportacao`, `Σ kwh_cortado` | idem | 🟢 |
| **Ciclos de bateria** | `Σ(bat_carga+bat_descarga) ÷ (2·cap_kwh)` | `bat_carga, bat_descarga` + `bateria_cap_kwh` | 🟢 |
| **Gap de otimalidade** | `(custo − custo_C1)/custo_C1` | custo agregado por braço | 🟢 |

> **Ponto de atenção de construto (seção 7 do plano):** *autoconsumo* e
> *autossuficiência* são conceitos distintos e não podem ser confundidos — as
> fórmulas acima precisam ser **fixadas no texto (P3)** antes de qualquer número
> ir para o Capítulo 5. A definição de autoconsumo tem variações (tratar ou não
> a energia que carrega a bateria e depois é usada); a escolha deve ser explícita.

---

## Ordem sugerida (mínimo para validar T1–T3)

1. 🟢 **Métricas 4.1** (`metrics.py`) — destrava T3.1/T3.3 e alimenta o resto.
2. 🟢 **T2.1 cobertura de estados** — número de alto valor argumentativo, custo baixo.
3. 🟢 **T3.2 estatística pareada** RL×C0 e RL×C1 (reusa `wilcoxon_pareado`).
4. 🟡 **T1.1 balanço** + **T1.2 transição de SoC** — fecham a rede de segurança física.
5. 🟢 **T2.2 sanidade RL>aleatório** — teste curto.
6. 🟡 **T2.3 convergência** medida — critério objetivo de parada.

**Fora deste escopo (peças separadas):** MILP (C2/gap teórico), sensibilidade a
hiperparâmetros, e tudo de seeds/estabilidade entre sementes.

---

## Reúso já disponível (não reescrever)
- `benchmark.wilcoxon_pareado`, `custos_por_dia`, `rede_por_dia`, `_phi`
  ([benchmark.py:46-105](src/smarty_energy/benchmark.py#L46-L105)).
- `evaluation.resumo_mes`, `rodar_sem_agente/heuristico/rl`
  ([evaluation.py](src/smarty_energy/evaluation.py)).
- `_rodar_aleatorio` / fixture `execucoes`
  ([test_constraints.py:40-68](tests/test_constraints.py#L40-L68)).
- Total do espaço de estados = **2160** ([environment.py:4-10](src/smarty_energy/environment.py#L4-L10)).
