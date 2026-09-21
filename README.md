# SmartEnergy MAS — Gestão Energética com Multi-Agentes

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

Sistema Multi-Agentes (MAS) com Q-Learning Cooperativo (Hysteretic IQL) focado na minimização de custos energéticos em uma fazenda de grãos.

> Contexto: Trabalho de Conclusão de Curso (TCC) desenvolvido com dados reais da Fazenda Buritis (Luziânia, GO) referentes a Janeiro de 2025.

Este repositório é a junção de dois projetos que evoluíram em paralelo:
o **motor de RL** (`Smart_Energy`) e a **camada MCP** (`mcp-smartenergy`).
Os dois históricos Git estão preservados aqui. Hoje há **uma só fonte da
verdade** para física, config e dados — a camada MCP consome o pacote em vez
de manter um fork.

---

## Dois modos de uso

Para entender e modificar o codigo com Copilot, consulte o
[guia de desenvolvimento com IA e Graphify](docs/desenvolvimento-ia.md).
O mapa estrutural e atualizado localmente por hooks do Git, sem indexar dados da fazenda.

| | Pipeline offline | Servidor MCP |
|---|---|---|
| Comando | `python main.py` | `python server.py` |
| Para quê | Treinar, avaliar e analisar (TCC, gráficos, relatórios) | Expor o sistema como ~25 ferramentas para um LLM-juiz |
| Interface | Dashboard Tkinter (default) ou Dash/Plotly (`--web`) | Dashboard Streamlit (cliente MCP) |
| Estado | `outputs/runs/<run_id>/` versionado | Processo único que detém dataset, Q-tables e tracker |

Os dois compartilham `outputs/runs/`: um run treinado pelo `main.py` é
carregável pelo servidor (`load_qtables`) e vice-versa (`save_qtables`).

---

## Como executar

```bash
python -m venv .venv
.venv\Scripts\activate        # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

Crie um `.env` na raiz com a planilha da base (ou deixe vazio para usar o
Excel local em `dados/`):

```
SHEET_ID=<id da planilha do Google Sheets>
```

### Pipeline offline

```bash
python main.py                 # treina um novo run e abre o dashboard
python main.py --replot        # reabre o run mais recente sem treinar
python main.py --run <run_id>  # reabre um run específico
python main.py --web           # dashboard web (Dash) em localhost:8050
```

### Servidor MCP + dashboard Streamlit

```bash
# terminal 1 — servidor (fica rodando; detém dataset, Q-tables e tracker)
python server.py

# terminal 2 — dashboard cliente
python -m streamlit run src/smarty_energy/mcp/dashboard/app.py
```

O catálogo de ferramentas e o loop LLM-as-a-judge estão em
[docs/mcp.md](docs/mcp.md); o passo a passo de instalação e inicialização do
servidor, em [docs/execucao-mcp.md](docs/execucao-mcp.md).

---

## Resultados históricos

O modelo atual usa sete períodos temporais, três níveis de descarga parcial e
um bônus pequeno para energia de bateria efetivamente entregue no pico. Os
resultados abaixo usam cinco seeds, 20 mil episódios, política greedy e SoC
propagado nos 31 dias da base v8:

| Métrica | Média | Mediana | Desvio padrão |
|---|---:|---:|---:|
| Custo médio diário | R$ 64,56 | R$ 65,38 | R$ 1,77 |
| Energia importada por dia | 93,52 kWh | 94,67 kWh | 2,81 kWh |
| Descarga no pico | 38,20 kWh/mês | 38,07 kWh/mês | 14,54 kWh |
| Parcela da descarga no pico | 13,03 % | 13,19 % | 4,52 p.p. |

O resumo histórico é acompanhado pelo
[artefato de avaliação multiseed](outputs/avaliacao_despacho_bateria_multiseed.json).
Esses resultados não foram reexecutados na limpeza documental e não representam
a validação dos novos [protocolos de divisão](docs/divisoes-dataset.md).
O relato original foi removido da árvore ativa, com recuperação no histórico
Git anterior à limpeza e no backup local. Para resultados atuais, registrar
dados, configuração, seeds e períodos de treino/validação/teste em cada run.

> Referência histórica: o run `2026-06-19_145038` obteve R$ 63,25/dia sob a
> codificação antiga. Ele não é comparável diretamente à arquitetura atual e
> não pode ser recarregado após a mudança de estado e ações da bateria.

### Otimizações aplicadas

**1. Hysteretic Q-Learning** — para a não-estacionariedade de sistemas multi-agente:
a taxa otimista (`alpha=0.1`) aprende rápido quando o resultado supera o esperado;
a pessimista (`beta=0.01`) esquece devagar bons resultados diante de erros de coordenação.

**2. Rebalanceamento do reward** — o custo financeiro passou a ser o sinal dominante,
evitando que os agentes manipulem o SOC da bateria em detrimento da economia real.

| Componente | Peso | Impacto |
| :--- | :--- | :--- |
| Custo diário | 8.0 | Sinal dominante |
| Bateria (SOC) | 12.0 | Barreira de segurança |
| Excedente solar | 0.5 | Incentivo à exportação |
| Descarga no pico | 0.5 | Reforço por kWh AC entregue no pico |

---

## Estrutura do projeto

```text
tcc-darvinposselt/
├── main.py                 # pipeline: dados → treino → avaliação → dashboard
├── server.py               # entry do servidor MCP
├── src/smarty_energy/
│   ├── config.py           # hiperparâmetros, pesos do reward, limites físicos
│   ├── data_loader.py      # FEMS ou base v8 → DataFrames diários
│   ├── environment.py      # FazendaEnergyEnv — simulador e restrições HARD
│   ├── agents/             # API publica; Q-learning, regras, avaliacao e IQLSystem
│   ├── training.py         # horizonte completo e seleção de checkpoint
│   ├── evaluation.py       # execução por dia, métricas mensais, cenários
│   ├── metrics.py          # métricas primárias do plano de testes (4.1/4.2)
│   ├── runs.py             # versionamento de treinos em outputs/runs/
│   ├── benchmark.py        # RL × LLM: qualidade da decisão vs custo operacional
│   ├── llm_policy.py       # política de controle por LLM (tool-use)
│   ├── visualization.py    # figuras do pipeline
│   ├── dashboard.py        # dashboard Tkinter
│   ├── dashboard_web.py    # dashboard web (Dash/Plotly)
│   └── mcp/
│       ├── server.py       # 45 ferramentas MCP (LLM-as-a-judge)
│       ├── tracker.py      # métricas por passo/episódio do servidor
│       └── dashboard/      # cliente Streamlit (Overview, Aprendizado, Trace)
├── tests/                  # suíte do pacote (+ tests/mcp/ para a camada MCP)
├── docs/                   # documentação Retype
├── outputs/                # runs, modelos e gráficos gerados
└── documentos/             # documentos do TCC (.docx)
```

---

## Testes

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -q       # tudo
PYTHONPATH=src .venv/bin/python -m pytest tests/mcp -q   # só a camada MCP
```

A suíte do pacote cobre balanço energético, restrições HARD, convergência e
comparação estatística pareada (T1–T3 do plano de testes); a da camada MCP
cobre as ferramentas do servidor e o tracker, com fixtures sintéticas.

---

## Documentação

A documentação fica em `docs/` e é construída com o
[**Retype**](https://retype.com), que transforma Markdown em um site estático
com busca, navegação lateral e tema claro/escuro.

| Página | Conteúdo |
| :--- | :--- |
| **Início** | Visão geral do projeto e resultados finais |
| **Instalação** | Pré-requisitos, ambiente virtual e variáveis de ambiente |
| **Execução** | Pipeline `python main.py` e artefatos gerados |
| **Arquitetura** | Os três agentes, espaço de estados, reward e Hysteretic Q-Learning |
| **Componentes** | Papel de cada módulo de `src/smarty_energy/` |
| **Dados de entrada** | Base Excel, abas e mapeamento de cargas/geração |
| **Configuração** | Hiperparâmetros e pesos do reward |
| **Servidor MCP** | Catálogo das ferramentas e loop LLM-as-a-judge |
| **Execução do MCP** | Instalação e inicialização do servidor + dashboard |

```bash
cd docs
npm install            # instala o retypeapp (dev dependency)
npm run docs:dev       # abre o site e recarrega ao editar
npm run docs:build     # gera o site estático em docs/site/
```

> Antes de publicar, ajuste o campo `url` em `docs/retype.json` para o domínio
> real (ex.: GitHub Pages) — o `retype build` exige esse campo.
