---
label: Arquitetura
icon: organization
order: 70
---

# Arquitetura Multi-Agentes

Esta é a visão técnica. A [visão de domínio](regras-dominio.md) descreve as
regras sem exigir leitura de Python; o [plano](reorganizacao.md) registra a
matriz regra/código/teste e as lacunas. O piloto de bateria, estados/ações e
continuidade foi conferido contra o código em 20/09/2026.

## Dependências de software

Os contratos A-DEP-001 a A-DEP-004 são verificações estáticas de imports,
não regras de operação energética. Estão em
`pyproject.toml`, executados pelo Import Linter 2.15 e pela
CI (`.github/workflows/qualidade-kit.yml`). Decisão: ADR-004 no [plano](reorganizacao.md).

| ID | Origem | Destinos proibidos, inclusive por caminhos indiretos |
|---|---|---|
| A-DEP-001 | Motor: config, battery, data_loader, agents, environment, training, evaluation, metrics, runs | MCP, dashboards, visualização, política LLM e benchmark |
| A-DEP-002 | Estado MCP, tracker e persistência de experimentos | Servidor MCP |
| A-DEP-003 | Backend MCP: servidor, estado, tracker e experimentos | Dashboard/juiz MCP, dashboards offline, visualização, política LLM, servidor do benchmark e benchmark |
| A-DEP-004 | Dashboard MCP (incluindo páginas) e judge_core | Motor, servidor MCP, ServerState, tracker e persistência de experimentos |

O servidor pode importar o estado e o motor; o estado pode referenciar
componentes do motor e tracker. O cliente usa ferramentas MCP, não objetos
da análise ativa. Não há restrição nova entre agentes, ambiente e treino:
seus ciclos internos existentes não foram refatorados neste lote.

As listas exatas em TOML são a fonte executável. Módulos novos fora das listas
precisam ser classificados em revisão; descendentes dos pacotes listados são
incluídos. Nenhum import foi ignorado como exceção, e caminhos indiretos não
foram liberados. Os testes introduzem violações diretas e indiretas em cópias
temporárias, inclusive em uma página do dashboard, e exigem falha do contrato.

Limites: não cobre imports dinâmicos, fluxos por objetos/dados, dependências
externas ou a execução implícita dos inicializadores ancestrais pelo Python.
O inicializador raiz ainda reexporta motor e visualização; isso não é prova
de isolamento de runtime. Diretórios novos sem marcador de pacote podem ser
omitidos pelo analisador: manter `__init__.py` e verificar descoberta ao criar
subpacotes. Os marcadores do dashboard/páginas não contêm imports nem lógica.
Veja [como executar](kit-agentes.md); o grafo Graphify continua complementar,
não substitui os contratos nem seus testes.

## Agentes cooperativos

Três agentes independentes — cada um com sua própria Q-table — compartilham o
mesmo **reward cooperativo**. É a mesma arquitetura nos dois modos de uso: o
pipeline offline e o [servidor MCP](mcp.md) importam o mesmo
`FazendaEnergyEnv` e os mesmos agentes.

| Agente | Responsabilidade | Ações |
|---|---|---|
| **Armazenamento** | Gestão da bateria | `0` = carregar excedente · `1` = manter · `2`/`3`/`4` = descarregar 25/50/100% do déficit · `5` = excedente e rede elegível |
| **Consumo** | Início do ciclo do pivô | bitmask (`0`…`7`): bit `1` participa do início do pivô; bits `2` e `4` são ignorados por bomba e secador, que seguem cronogramas |
| **Gerente de Carga** | Teto de consumo horário | `0` = Conservador (20 kW) · `1` = Moderado (30 kW) · `2` = Liberal (40 kW) |

## Espaço de estados (3780 estados discretos)

Tupla `(bucket_hora, bucket_soc, bucket_solar, bucket_stress, meta_secador, bucket_bomba)`:

| Variável | Buckets |
|---|---|
| período energético | 7 (0-5h / 6-11h / 12-15h / 16-17h / 18-19h / 20h / 21-23h) |
| `soc // 10` | 10 (0-10 % / 10-20 % / … / 90-100 %) |
| **solar** | 3 (<5 kW / 5 ≤ solar < 15 kW / ≥15 kW) |
| **stress** | 3 (<30 / 30 ≤ stress < 70 / ≥70 — calculado pelo `AgenteFinanceiro`) |
| **meta secador** | 2 (atingiu a meta diária de 20 kWh?) |
| **bomba** | 3 (<3h / 3-5h / ≥6h operadas) |

Total combinatório: 7 × 10 × 3 × 3 × 2 × 3 = **3780**
(`environment.ESPACO_ESTADOS_TOTAL`). É um teto — parte das combinações é
fisicamente inalcançável, então a cobertura medida contra ele é conservadora.

!!!warning Compatibilidade de runs
Q-tables treinadas com outra codificação temporal não podem ser recarregadas:
a versão é gravada no `meta.json` de cada run e validada no carregamento. Após
mudar a discretização, retreine e versiona um novo run antes de comparar
resultados.
!!!

## Restrições HARD

Aplicadas pelo ambiente, independentemente da ação escolhida:

| Restrição | Regra |
|---|---|
| **R-PIVO** | 8h consecutivas e uma única ativação por dia; durante o lock opera em 8 kW |
| **R-BOMBA** | cronograma fixo nas horas 3-4, 9-10, 15-16 e 21-22 (17,6 kW) — a ação do agente é ignorada |
| **R-SECADOR** | segue a potência horária da base, ignorando o bit de corte; meta de 20 kWh com penalidade terminal se não atingida, sem rescue ativo |
| **R-SEDE** | consumo clampado em ±20 % do ideal; eco-mode (−20 %) com stress ≥ 70 |
| **R-PCC** | importação/exportação ≤ 65,8 kW, mutuamente exclusivas |
| **R-BAT** | throughput diário compartilhado ≤ 30 kWh DC, η carga 0,92 / η descarga 0,95 |

## Contratos do piloto

### Bateria: R-BAT-001, R-BAT-002 e R-BAT-003

BatteryModel (`src/smarty_energy/battery.py`) mantém SoC e throughput; o
ambiente decide a energia solicitada e a origem. As entradas pressupõem
configuração física válida e valores finitos; não há validação completa de
configuração ou clamp do argumento de `reset`.

Para um passo de uma hora, com energia DC atual `E`, espaço até o SoC máximo
`H` e throughput restante `T`:

```text
carga_dc = min(max(0, disponivel_ac) * eficiencia_carga, H, T)
carga_ac = carga_dc / eficiencia_carga
descarga_dc = min(max(0, deficit_ac) * fracao / eficiencia_descarga,
                  E - energia_soc_minimo, T)
descarga_ac = descarga_dc * eficiencia_descarga
```

Bloqueios por ausência de energia/déficit, SoC ou throughput antecedem essas
fórmulas. O throughput acumula `carga_dc + descarga_dc`, não a energia AC.
`reset(soc_inicial)` preserva o valor informado e zera throughput; sem argumento,
usa o SoC inicial configurado. O reset do ambiente também zera seus contadores
diários, histórico, locks e pico de importação.

`BatteryFlow` é imutável. Na carga, `input_kwh` é AC e `stored_kwh` é DC;
na descarga, `input_kwh` e `stored_kwh` representam DC retirada, enquanto
`delivered_kwh` é AC entregue. Os nomes não têm a mesma interpretação física
nas duas operações. `source` identifica a origem da carga; `blocked_reason`
explica bloqueios. Os [valores padrão](configuracao.md) não são recalibrados aqui.

### Estados e ações: R-EST-001 e R-ACO-001

A ordem dos seis buckets é parte do contrato. O SoC usa
`min(int(soc / 10), 9)`: 100% permanece no bucket 9. A meta do secador usa
`>= secador_meta_kwh`; os limiares de bomba são 3 e 6 horas. A versão atual é
`STATE_ENCODING_VERSION = 2`. A dimensão sozinha não identifica a semântica.

O catálogo de ações tem dimensões `(6, 8, 3)`. `FRACOES_DESCARGA` associa
`2: 0.25`, `3: 0.50`, `4: 1.0`. Para a ação 5, o ambiente tenta carga com
excedente primeiro; solicita energia da rede somente quando
`tarifa < tarifa_referencia_arbitragem * eficiencia_carga * eficiencia_descarga`.
A igualdade bloqueia a parcela da rede. Os testes do piloto exercitam o limite
e seus vizinhos representáveis (`numpy.nextafter`), além da prioridade do
excedente quando o throughput restante é pequeno. Bloquear a parcela da rede
por tarifa não impede a carga com excedente. Essa verificação não certifica
a conservação do balanço quando o PCC é atingido.

### Continuidade e runs: R-SOC-001 e R-RUN-001

`evaluation._rodar_mes` começa no SoC padrão e encadeia o último `soc` de cada
histórico não vazio, na ordem recebida. Com propagação desligada, passa `None`
ao executor diário. `training.treinar` também encadeia SoC, inclusive ao voltar
ao primeiro dia da lista. Não confundir essa continuidade com persistência de
todos os estados operacionais/financeiros: novos ambientes são criados por dia.

As funções públicas `rodar_sem_agente_mes`, `rodar_heuristico_mes`,
`rodar_rl_mes` e `rodar_llm_mes` propagam SoC por padrão e preservam a ordem dos
dias, a tarifa e o decisor fornecidos. `propagar_soc=False` reinicia cada dia
no padrão. Os testes verificam o encaminhamento nas quatro funções e dois
dias completos nos caminhos RL/LLM com decisores fixos de teste. O caminho RL
usa `explorando=False`; o caminho LLM entrega o estado descritivo à política.
Nenhuma chamada a provedor é feita nesses testes.

`runs.verificar_compatibilidade` rejeita versão de estados divergente e chaves
com dimensão/faixa incompatíveis. Configuração ausente ou diferenças nos
parâmetros físicos verificados geram avisos. Essa validação não certifica todos
os parâmetros, a semântica de ações, o protocolo ou a comparabilidade de runs.

### Persistência: R-RUN-002

`runs.salvar_run` grava três Q-tables, `training_history.pkl` e `meta.json`,
e atualiza `latest.txt`. O roundtrip em diretório temporário verifica valores
das tabelas, número de ações, epsilon, contagem de updates, histórico e cópia
da configuração fornecida. Estados ainda não visitados continuam recebendo
vetores zerados. Não se afirma que RNG, tracker e todo o estado de treino sejam
restaurados, nem que o salvamento seja transacional.

`AgenteQL.load` rejeita `n_acoes` divergente quando presente no pickle.
`carregar_run` aplica o carregamento nos agentes antes da checagem final de
estados; uma exceção pode deixar agentes parcialmente modificados. Preservar
estado em qualquer falha exige outro contrato e implementação, ainda pendentes.
Pickle executa desserialização de objetos Python: carregar somente artefatos
confiáveis, não arquivos arbitrários enviados por clientes.

Os [contratos de dados](dados.md) e da [fronteira MCP](mcp.md) complementam o
piloto e têm evidências na [matriz de rastreabilidade](reorganizacao.md).

## Reward cooperativo

O esquema abaixo é conceitual e não enumera todos os termos atuais. A auditoria
completa do reward (incluindo custos econômicos, reserva e offset) é uma etapa
separada do [plano](reorganizacao.md); consulte `FazendaEnergyEnv.step` para o
cálculo vigente. Não usar este resumo como fórmula para reproduzir resultados.

```text
reward = - w_custo        * custo_rede
         - w_estresse     * (stress / 10)
         - pen_soc        * (SOC < 15%)
         - pen_teto       * (consumo >= teto)
         - pen_pcc        * (PCC violado)
         - pen_producao   * kWh_cortado
         - pen_secador_meta  (se a meta diária não foi atingida)
         - pen_pivo_pico     (pivô ligado em pico tarifário)
         - pen_secador_pico  (secador ligado em pico tarifário)
         + bonus_pivo_solar     (pivô operando com sol ≥ 15 kW)
         + bonus_sec_excedente  (secador com excedente ≥ 5 kW)
         + w_bonus_carga  * kWh carregados com excedente
         + bonus_excedente * kWh_excedente * tarifa
         + bonus_soc_ok    * (30% < SOC < 80%)
         + bonus_descarga_pico * kWh AC descarregados no pico
```

Os pesos estão em [Configuração](configuracao.md) e podem ser ajustados em
runtime pela tool `configure_reward_weights`.

## Hysteretic Q-Learning

R-TRE-001: o loop `training.treinar` executa o horizonte configurado. Com seleção greedy
habilitada, avalia checkpoints periódicos e restaura as Q-tables do menor custo
avaliado ao final; não interrompe antecipadamente os episódios. O teste
`test_treino_completa_horizonte_e_restaura_checkpoint`, em `tests/test_training.py`,
exercita três episódios e custos de avaliação controlados. Não comprova
convergência ou superioridade da política.

Para lidar com a **não-estacionariedade** típica de sistemas multi-agente, o
aprendizado usa duas taxas:

- **Taxa otimista (`alpha` = 0.1)** — aprende rápido quando o resultado supera o
  esperado.
- **Taxa pessimista (`beta` = 0.01)** — esquece devagar bons resultados quando
  ocorrem erros de coordenação.

O SOC da bateria **propaga entre episódios**: o dia seguinte começa com a carga
deixada pelo anterior, simulando continuidade real.

## Baselines

- **Heurístico (C1)** — regras fixas com um **índice de estresse financeiro**
  (0–100) derivado da tarifa e do nível da bateria; o estresse determina cortes
  de carga e teto de consumo via limiares `if/else`.
- **Sem agente (C0)** — baseline definido no modelo: bateria em manter, teto
  liberal e início do pivô às 16h, com bomba e secador seguindo seus cronogramas.
  Não é evidência, por si só, de como uma fazenda real opera.
