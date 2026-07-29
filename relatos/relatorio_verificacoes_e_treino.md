# Relatório — Verificações de física, consumo e otimização do treino

**Escopo:** cinco verificações pedidas (física × base v8, igualdade pipeline ×
MCP, escala do reward, valor do consumo, continuidade da bateria) mais a
correção do critério de seleção de checkpoint que as antecedeu.

**Fonte da verdade adotada:** a base v8 (`Cadastro_Cargas`, `Cargas`,
`Consumo_Fatura`, `Resumo_Mensal`). A `Descrição do sistema.docx` é uma spec
antiga e **não** é a referência.

**Estado de publicação:** o commit da seleção greedy (`e9f70e4`) está no GitHub
(`LuccasJose/mcp-smartenergy`, `main`); os três commits das verificações
(`2067dc9`, `9bbeb0e`, `ec61aca`) estão **locais**, aguardando decisão de push.

---

## 0. Antecedente — Seleção de checkpoint por avaliação greedy

**Problema.** O early stopping escolhia o checkpoint pela média móvel do custo
**durante o treino**, medido com ε-greedy ativo. Esse número não distingue
política boa de ruim: em 3 sementes × 100k episódios ele ficou cravado em
~R$74/dia enquanto a política **greedy** (a que de fato roda) oscilava entre
R$53 e R$89/dia. Era por isso que retreinar vinha **piorando** o resultado — o
critério sorteava.

**Correção.** `training.treinar` passou a avaliar a política greedy a cada
`eval_greedy_cada` episódios e restaurar o melhor checkpoint. Parâmetro
`dias_selecao` permite separar o conjunto de seleção do de reporte.

**Validação (holdout honesto — seleciona nos dias ímpares, reporta nos pares,
3 sementes):**

| critério | custo holdout |
|---|---|
| sem seleção (último episódio) | R$74,13/dia |
| seleção pelo custo de treino (antigo) | ~R$70,70/dia |
| **seleção greedy (novo)** | **R$56,15/dia** |

O número in-sample (selecionar e reportar nos mesmos 31 dias) dava R$52,69 —
~6% otimista. É o holdout (R$56,15) que deve ir para o TCC.

**Observação metodológica.** O ganho é grande **porque a política é instável**;
a seleção não conserta a instabilidade, ela a aproveita. A causa raiz continua
sendo a interação do hysteretic com a escala do reward (ver item 3).

---

## 1. Auditoria de restrições e valores contra a base v8

**O que foi feito.** Script `scripts/auditar_base.py` (reproduzível) que carrega
a base e compara CONFIG × `Cadastro_Cargas` × restrições HARD. Saída em
`relatos/auditoria_base_v8.md`.

**Resultado — conferem.**

| Parâmetro (CONFIG) | valor | base `Cons_Max` | veredito |
|---|---|---|---|
| `pivo_nominal_kw` | 8,0 | 8,000 | OK |
| `bomba_cap_nominal_kw` | 17,6 | 17,600 | OK |
| `secador_max_kw` | 2,4 | 2,367 | OK (arredondamento) |
| PCC / inversor FV / eólico | 65,8 / 50 / 10 | idem | OK |
| Pivô 8h, secador meta 20 kWh, bomba 8h/dia | — | idem | OK |

**Ressalva.** Os parâmetros da bateria (capacidade 24 kWh, SoC 15–95%,
η 0,92/0,95, throughput 48 kWh) **não têm contrapartida na base** — são
premissas de engenharia. Divergem da `.docx` (30 kWh, 20–100%, 0,894), que não
é a referência. Ficam documentados como premissa, não como erro.

**Conclusão.** A suspeita de "resultados diferentes" **não** vinha de valores
errados no CONFIG contra a base — vinha da física divergente que o MCP tinha
antes da junção (secador hardcoded, contrato de `step` distinto), já corrigida.

---

## 2. Igualdade de física entre pipeline e camada MCP

**O que foi feito.** Novo arquivo `tests/mcp/test_fisica_unificada.py` (4 testes)
que **trava** a unificação contra regressão:

- **Identidade de objetos:** `server.FazendaEnergyEnv is environment.FazendaEnergyEnv`,
  idem para `CONFIG`, `BOMBA_HORAS_ON`, `IQLSystem`.
- **Ausência de fork:** `smarty_energy.mcp.{config,environment,energy_env,agents}`
  não devem existir (import deve falhar).
- **Schema espelha o CONFIG:** `describe_schema()` reporta os mesmos
  `parametros_fisicos`, `secador_max_kw` etc. do CONFIG.
- **Comportamento idêntico:** uma sequência fixa de 24 ações produz o mesmo
  `historico` (custo, reward, consumo, SoC) no env do pacote e no do servidor.

**Resultado.** Confirmado que o MCP não tem física própria. Se alguém
reintroduzir um fork ou mudar um valor só de um lado, algum destes testes quebra.

---

## 3. Escala do reward (`reward_offset`)

**Problema.** ~80% dos passos têm reward negativo (o custo da energia domina).
Como as Q-tables partem de 0 e os valores verdadeiros são muito negativos, o
aprendizado principal é feito de TD negativos → governado pela taxa pessimista
`beta=0,01` (10× mais lenta). A magnitude das Q-values nunca estabiliza (|Q|
sobe de 10 → 110 ao longo de 100k episódios).

**O que foi feito.** Knob `reward_offset` no CONFIG, somado a todo passo no fim
do reward (`environment.py`). Como o episódio tem horizonte fixo (24 passos),
somar constante seria policy-preserving numa Q-table convergida.

**Medição (holdout, 8k ep, 3 sementes) — efeito NÃO monotônico:**

| offset | custo holdout | \|Q\| médio | vs offset 0 |
|---|---|---|---|
| 0 | R$60,04 | 8 | — |
| **60** | **R$56,81** | 107 | **−R$3,23 (melhora em 2/3)** |
| 160 | R$67,63 | 814 | +R$7,59 (piora em 3/3) |
| 200 | R$68,28 | 1340 | +R$8,23 (piora em 3/3) |

**Achado (contra-intuitivo).** Centrar a média perto de zero (offset ≈60)
ajuda ~5%; tornar **tudo** positivo (160/200) piora e estoura a escala das
Q-values (α passa a dominar, o hysteretic para de atuar). Ou seja, a intuição
de "deixar o reward positivo" está errada — o ponto é **centrar**, não deslocar.

**Decisão.** Default `reward_offset=0` (sem mudar runs existentes). Adotar ~60
exige re-treino + re-validação e mudaria o número oficial. **Não** altera o
custo em R$ (medido em `custo_r`, à parte do reward).

---

## 4. Valor do consumo (base → env → faturado)

**O que foi feito.** O mesmo `scripts/auditar_base.py` reporta o consumo por
máquina em três estágios.

**Resultado — o total bate 100%:**

| Máquina | demanda bruta | entregue pelo env | env/bruto |
|---|---|---|---|
| pivô | 69,14 | 64,00 | **93%** |
| bomba/captação | 135,64 | 140,80 | **104%** |
| sede | 62,17 | 61,00 | 98% |
| secador | 54,40 | 54,40 | 100% |
| silo | 4,62 | 4,62 | 100% |
| **TOTAL** | **325,97** | **324,82** | **100%** |

Faturado (`Resumo_Mensal`, FAZ-002): 10.105 kWh/mês = 325,97 kWh/dia. A demanda
bruta = 100% do faturado; o env entrega 99,6%.

**Achado.** Por máquina, o cronograma HARD distorce o perfil: o lock de 8h do
pivô não cobre todas as horas do perfil real (93%), e a bomba é forçada ao
`Cons_Max` nas horas agendadas (104%). As duas distorções ~se cancelam no total.
É consequência de projeto das restrições HARD, não erro de valor — decidir se o
realismo por-máquina importa para o TCC.

> Nota: o "consumo abaixo do padrão" que se via antes vinha da física do MCP
> pré-junção (secador hardcoded 2,2 kW, Secadora dentro do silo), já corrigida.

---

## 5. Continuidade da bateria (propagação do SoC)

**Problema.** O treino propagava o SoC entre dias (o dia seguinte começa com a
carga que sobrou), mas a avaliação oficial (`rodar_rl` e as demais `rodar_*` de
dia único) **reiniciava em 50%** todo dia. A política era avaliada sob dinâmica
diferente da que treinou.

**O que foi feito.** Wrappers de mês que encadeiam o SoC:
`rodar_sem_agente_mes`, `rodar_heuristico_mes`, `rodar_rl_mes`, `rodar_llm_mes`
(`evaluation.py`). `main.py`, `runs.resultados_rl` e `benchmark` passam por eles;
a seleção greedy do treino também propaga, alinhando seleção e reporte.

**Efeito no run canônico (100k, `2026-06-19_145038`):**

| protocolo | Sem agente | Heurístico | RL | economia RL | violações SoC |
|---|---|---|---|---|---|
| reset diário (antigo) | R$106,90 | R$103,35 | R$66,59 | 37,7% | 0,032/dia |
| **propagação (novo)** | R$106,90 | R$103,35 | **R$63,25** | **40,8%** | 0,032/dia |

Sob propagação a política fica **mais barata** e a economia sobe para 40,8%; o
SoC nunca cai abaixo de 15%.

**Impacto em teste.** O teste `test_rl_sem_violacoes_soc` exigia **exatamente
zero** violações — o que dependia do reset diário esconder dias iniciados com a
bateria baixa. Passou a `test_rl_seguranca_operacional_soc`, com um limite
tolerado (`SMARTY_MAX_VIOL_SOC`, default folgado para o agente rápido de teste;
o run canônico fica em ~0,03/dia). Os fixtures de teste agora usam propagação.

---

## Consistência MCP × pipeline (teste-chave)

Após todas as mudanças, sob propagação, no mesmo run e mesmos 31 dias:

- **Pipeline** (`resumo_mes`): IQL R$63,25/dia
- **MCP** (`compare_strategies`): IQL R$63,25/dia
- **|diferença| = R$0,0000 → CONSISTENTE**

Prova de que os dois mundos continuam batendo bit a bit — não sobrou CONFIG nem
física duplicada.

**Agora travado por teste.** Essa conferência era manual — se alguém quebrasse a
igualdade, nada avisaria. Virou `test_compare_strategies_bate_com_o_pipeline`
(`tests/mcp/test_fisica_unificada.py`), que compara as 4 métricas do resumo
(custo, rede, violações de SoC, reward) nas 3 estratégias, pelos dois caminhos
independentes — `IQLSystem.avaliar` com o cfg do servidor contra `rodar_*_mes`
com o CONFIG do pacote.

O teste semeia as Q-tables de propósito: com agentes zerados, `argmax` devolve
sempre a ação 0, a política fica degenerada em `(0,0,0)` e a bateria nunca
descarrega — nessa condição uma divergência de capacidade da bateria passava
despercebida. Semeado, ele pega: bateria 24→30 kWh só no MCP acusa R$0,85 de
diferença; bomba 17,6→20 kW acusa R$2,83.

---

## Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `scripts/auditar_base.py` | **novo** — auditoria itens 1 e 4 |
| `relatos/auditoria_base_v8.md` | **novo** — saída da auditoria |
| `tests/mcp/test_fisica_unificada.py` | **novo** — 4 testes do item 2 |
| `src/smarty_energy/config.py` | `reward_offset` (item 3) |
| `src/smarty_energy/environment.py` | aplica `reward_offset` no `step` |
| `src/smarty_energy/evaluation.py` | `soc_inicial` nas `rodar_*` + wrappers `*_mes` (item 5) |
| `src/smarty_energy/training.py` | seleção greedy propaga o SoC |
| `src/smarty_energy/runs.py`, `benchmark.py`, `main.py` | roteados pelos wrappers de mês |
| `src/smarty_energy/__init__.py` | exporta os wrappers `*_mes` |
| `tests/test_resultados.py`, `tests/mcp/test_env.py` | ajustados aos novos protocolos |

**Testes:** 116 (57 do pacote + 59 da camada MCP), todos verdes — inclusive sob
o orçamento real de treino (`SMARTY_TEST_EPISODIOS=100000`) e com o limite de
violação de SoC apertado 10× (`SMARTY_MAX_VIOL_SOC=0.05`): 116 passados em
7min06s, zero pulados.

> **Cuidado ao rodar a suíte.** O `dados_reais` do `tests/conftest.py` faz
> *skip* se a base não carregar, e a base vem do Google Sheets a cada sessão.
> Um rate limit (`HTTP 400`) já produziu um run "verde" com **35 testes pulados
> em silêncio e exit code 0** — tudo que toca a base real ficou sem ser testado.
> Para um resultado confiável, baixe a planilha uma vez e rode offline:
>
> ```powershell
> $env:SHEET_ID = ""
> $env:DATA_PATH = "caminho\para\base_v8.xlsx"
> pytest -q -rs        # -rs expõe qualquer skip
> ```

---

## Decisões em aberto (para o autor)

1. ~~**O número oficial mudou de R$66,59 para R$63,25/dia**~~ — **resolvido**.
   `README.md` e `docs/index.md` foram atualizados: economia 57,2% → **40,8%**,
   redução da rede 64,0% → **40,2%**, e o "zero violações" virou "PCC zero ·
   SoC 0,032 h/dia" (as três afirmações estavam erradas, não só a primeira).
   Ambos agora declaram o run e o protocolo (SoC propagado). **Os textos do
   próprio TCC continuam por conta do autor.**
2. **`reward_offset` fica em 0.** Adotar ~60 renderia ~5%, mas exige re-treino
   canônico + re-validação e muda o número oficial de novo. Recomenda-se decidir
   junto com um eventual re-treino, não isolado.
3. **Distorção por-máquina do consumo (item 4):** pivô 93% / bomba 104%. Decidir
   se o realismo por-máquina importa; o total já está correto.
4. **Push:** os três commits das verificações estão locais. Publicar quando
   aprovado.
