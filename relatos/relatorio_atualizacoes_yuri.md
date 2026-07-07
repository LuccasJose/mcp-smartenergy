# Relatório de atualizações — commit do Yuri

> **Commit:** `abf0778` — *"Adiciona suite de testes de validacao (unidade, restricoes rigidas e resultados)"*
> **Autor:** YuriRes ([yuriresende48@gmail.com](mailto:yuriresende48@gmail.com)) · **03/07/2026**
> **Integração:** `main` avançou por *fast-forward* (`0d06cad → abf0778`).
> **Volume:** 11 arquivos · **+679 / −123** linhas.
> **Validação:** `pytest -m "not slow"` → **36 passed, 1 deselected**.

---

## 1. Sumário executivo

O commit entrega **duas frentes** que, apesar de virem juntas, resolvem problemas diferentes:

| Frente | O quê | Por quê importa |
|---|---|---|
| **A. Suíte de testes** | ~37 testes cobrindo dados, restrições físicas e resultados do RL | Rede de segurança: prova que o agente respeita as regras e entrega os números alegados no TCC |
| **B. Custo real no dashboard** | Nova métrica de custo por máquina (rateio da fatura paga) | BI mais honesto: mostra a economia **real**, não só a teórica (kWh × tarifa) |

Ambas foram integradas sem quebrar o trabalho em andamento (benchmark RL×LLM via MCP), que permanece como alterações locais não commitadas.

---

## 2. Como a integração foi feita

1. **`git fetch`** trouxe o commit do Yuri como `origin/main`.
2. As alterações locais em andamento (`evaluation.py` e a função nova `plot_tradeoff_mcp` em `visualization.py`) foram **guardadas com `git stash`**.
3. **`git merge --ff-only origin/main`** avançou o `main` limpo até `abf0778`.
4. **`git stash pop`** reaplicou o trabalho local **sem conflito** — o merge 3-way juntou as mudanças do Yuri (meio do `visualization.py`) com a função local (fim do arquivo).
5. Verificações: compilação OK, `import smarty_energy.dashboard_web` resolve, e as duas funções coexistem (`_custo_real_por_maquina` do Yuri + `plot_tradeoff_mcp` local).

> **Bônus:** os testes reescritos do ambiente corrigem 2 falhas antigas — `discretizar` agora esperando **tupla de 6** e as **chaves atuais do CONFIG** (ex. `bomba_on_max`).

---

## 3. Frente A — Suíte de testes de validação

### 3.1 Arquitetura (`tests/conftest.py`)

O `conftest` centraliza as fixtures e garante testes **determinísticos e offline**:

- **`_semente_determinista`** (`autouse`): fixa `np.random.seed(42)` antes de cada teste.
- **`_isola_outputs`** (`autouse`, sessão): redireciona a escrita de artefatos do treino para um diretório temporário — **não sobrescreve** o `outputs/models/` do treino real do usuário.
- **Dados reais** (`dados_reais`/`dias_reais`/`tarifa_real`, escopo de sessão): carregam a base oficial uma única vez; fazem **`skip`** automático se a base estiver indisponível (sem rede/arquivo), evitando falha em CI.
- **Dados sintéticos** (`dia_fake`, `tarifa_fake`, `env`): dia controlado (geração/consumo constantes) e tarifa com pico das 18h–20h, para testes de unidade.
- **Treino configurável** (`treinar_agentes`, `agentes_treinados`): treino curto e determinístico. Nº de episódios via env var **`SMARTY_TEST_EPISODIOS`** (padrão **800**); o decaimento de ε é reescalado para o treino curto ainda convergir.

### 3.2 As três camadas de teste

#### `tests/test_data_loader.py` — a base é sã (8 testes)
Valida a base real antes de qualquer conclusão: 31 dias, 24h por dia, colunas presentes, sem nulos/negativos, tarifa no formato certo com **pico > fora-pico**, geração solar **zero de madrugada** e datas de janeiro/2025.

#### `tests/test_constraints.py` — restrições rígidas (12 testes)
A ideia central: uma restrição só é *rígida* se valer para **qualquer política**. Por isso cada teste roda sobre **os 31 dias × 3 políticas** (heurística, aleatória e "manter"):

| Restrição | Verifica |
|---|---|
| R-SOC | `0 ≤ SoC ≤ 100 %` |
| R-PCC | importação/exportação ≤ `pcc_max_kw`, **sem simultaneidade** |
| R-BALANÇO | `geração + bateria + rede = consumo` (fechamento energético) |
| R-TETO | consumo ≤ teto escolhido pelo gerente |
| R-THROUGHPUT | energia movimentada na bateria ≤ limite diário |
| R-BOMBA | bomba ligada **exatamente** no cronograma fixo |
| R-PIVÔ | irrigação em **0 ou 8 h consecutivas** (1 ativação/dia) |
| R-SECADOR | meta diária de energia do secador atingida |
| R-SEDE | consumo da sede dentro de **±20 %** do ideal |

#### `tests/test_resultados.py` — o RL entrega (5 testes)
Treina os agentes e compara **RL × Sem-Agente × Heurístico** em todos os dias, checando as alegações do TCC:

- **Zero violações de SoC** (segurança operacional) — assert estrito `viol == 0`.
- **Economia de custo** vs sem-agente (limiar configurável via `SMARTY_MIN_ECONOMIA_PCT`).
- **Redução da dependência da rede** (kWh importados).
- **Custo finito e positivo**.
- **Reprodutibilidade** (`@pytest.mark.slow`): mesma semente → mesmo custo (`rel=1e-9`).

#### `tests/test_environment.py` — unidade (12 testes, reescrito)
Reset/step/episódio, `discretizar` → tupla de 6, SoC nunca ultrapassa limites, agente (ação válida, greedy pós-treino, decaimento de ε, save/load), heurística com ações válidas e chaves de `CONFIG`/`TETOS_KW`.

### 3.3 Como rodar

```bash
# Rápido (~800 episódios de treino, ~7s) — exclui o teste lento
pytest -m "not slow" -q

# Completo/fiel ao TCC (treino longo + reprodutibilidade)
# PowerShell:
$env:SMARTY_TEST_EPISODIOS = "100000"; $env:SMARTY_MIN_ECONOMIA_PCT = "40"
pytest -q
```

**Resultado atual:** `36 passed, 1 deselected in ~7s`.

---

## 4. Frente B — "Custo real" no dashboard

### 4.1 O problema
Até então o dashboard mostrava só o **custo teórico** por máquina (`kWh × tarifa`), que ignora o desconto de bateria/solar. Isso superestima o gasto e não reflete a fatura efetivamente paga.

### 4.2 A solução — `_custo_real_por_maquina` (`visualization.py`)
A cada hora, o custo efetivo da rede (`custo_r`, já líquido de bateria/solar) é **rateado** entre as máquinas na proporção do consumo daquela hora. Propriedade-chave: **a soma bate exatamente com a fatura total** da estratégia — permitindo comparar onde cada estratégia gasta de fato.

### 4.3 O que mudou na interface

**Tabela de KPIs por máquina** (web `dash_table` e matplotlib):
- **+** coluna **"Custo real R$"**
- **−** coluna **"kWh pico"** (removida)
- **Δ$ vs Heur** → **"Δ$ real vs Heur"** (comparação passa a usar o custo real)

**Gráfico "Custo por máquina × estratégia"** (`_fig_visao_geral`):
- A pilha agora soma o **custo real** (rateio da fatura), não o teórico.
- **Removidos** os marcadores diamante de "fatura real" — ficaram redundantes, pois a própria pilha já soma a fatura.
- A anotação de topo passa a exibir o total = fatura real.

> **Decisão registrada:** a tabela enriquecida do Yuri foi **mantida** (havia um pedido anterior de removê-la; optou-se por preservar o trabalho novo).

---

## 5. Roteiro de apresentação

### Slide 1 — Abertura (15s)
> "Integrei o commit do Yuri ao `main` e validei. São duas entregas: uma **suíte de testes de validação** e um **refinamento de custo** no dashboard."

### Slide 2 — Por que testes? (30s)
> "O projeto faz alegações fortes — o agente respeita restrições físicas e economiza. Antes, isso era verificado no olho. Agora são ~37 testes automatizados em três camadas: **a base é sã**, **as restrições são rígidas** e **o RL entrega os números**."
- Mostrar terminal: `pytest -m "not slow" -q` → **36 passed**.

### Slide 3 — Destaque: restrições rígidas (30s)
> "O truque aqui é rodar cada restrição sob **três políticas diferentes**, inclusive uma **aleatória**. Se nem o caos viola a regra, ela é realmente rígida — SoC, PCC, balanço energético, cronograma da bomba, pivô 0-ou-8h, meta do secador."

### Slide 4 — Destaque: resultados do TCC (20s)
> "Os testes de integração travam as alegações do trabalho: **zero violações de SoC**, **economia vs sem-agente** e **menos rede**. Com semente fixa, o resultado é **reprodutível**."

### Slide 5 — Custo real no BI (30s)
> "No dashboard, o custo por máquina era só **teórico**. Agora temos o **custo real** — a fatura paga, rateada por máquina. A soma bate com a conta de luz."
- Abrir aba **"Visão Geral Operacional"** → apontar coluna teórico vs real.

### Slide 6 — Fechamento (15s)
> "Resultado: mais **confiança** (testes provam as regras) e mais **clareza** no BI (economia real). Tudo integrado sem quebrar o trabalho em andamento do benchmark RL×LLM."

---

## 6. Pendências / observações

- **Teste `slow`** (reprodutibilidade) não foi executado nesta rodada — rode com `pytest -m slow` quando quiser.
- **`pytest` foi instalado** no `.venv` para rodar a suíte (não estava presente).
- **Trabalho local não commitado** (benchmark RL×LLM: `benchmark.py`, `llm_policy.py`, `mcp_server.py`, `plot_tradeoff_mcp`) permanece intacto e fora do commit do Yuri.
