---
label: Início
icon: home
order: 100
---

# SmartEnergy MAS

Sistema **Multi-Agentes (MAS)** com **Q-Learning Cooperativo (Hysteretic IQL)**
para minimizar custos energéticos de uma fazenda de grãos.

!!!success Contexto
Trabalho de Conclusão de Curso (TCC) desenvolvido com **dados reais da Fazenda
Buritis** (Luziânia, GO), referentes a **Janeiro de 2025**.
!!!

## Visão geral

A fazenda possui geração distribuída (solar + eólica), uma bateria de 24 kWh e
cinco cargas (pivô central, bomba de captação, secador, sede administrativa e
silo). A tarifa é do tipo **Azul**, com ponta entre 18h–21h
(R$ 1,10/kWh contra R$ 0,68/kWh fora de ponta).

Três agentes independentes — cada um com sua própria Q-table — compartilham um
**reward cooperativo** e aprendem, em conjunto, a operar a bateria, cortar
cargas interruptíveis e definir o teto de consumo horário.

## Dois modos de uso

O mesmo motor atende duas frentes, com uma só fonte de verdade para física,
config e dados:

| | Pipeline offline | Servidor MCP |
|---|---|---|
| Comando | `python main.py` | `python server.py` |
| Para quê | Treinar, avaliar e analisar | Expor ~25 ferramentas a um LLM-juiz |
| Interface | Tkinter ou Dash (`--web`) | Streamlit (cliente MCP) |

Os dois compartilham `outputs/runs/`, então um treino longo feito no pipeline
pode ser carregado pelo servidor e vice-versa.

## Resultados finais

Run canônico (`outputs/runs/2026-06-19_145038`, 100 mil episódios), avaliado nos
31 dias da base v8 com o SoC da bateria propagado entre dias:

| Métrica | Resultado |
|---|---|
| Custo médio diário (RL) | **R$ 63,25** |
| Economia no custo diário médio | **40,8 %** |
| Redução da dependência da rede | **40,2 %** |
| Violações de PCC | **Zero** |
| Violações de SOC | 0,032 h/dia |

Referências do mesmo protocolo: sem agente R$ 106,90/dia e heurístico
R$ 103,35/dia.

## Por onde começar

- [Instalação](instalacao.md) — preparar o ambiente Python e as dependências.
- [Execução](execucao.md) — rodar o pipeline completo e abrir o dashboard.
- [Execução do MCP](execucao-mcp.md) — subir o servidor e o dashboard Streamlit.
- [Arquitetura](arquitetura.md) — os três agentes, o estado e o reward cooperativo.
- [Servidor MCP](mcp.md) — catálogo de ferramentas e o loop LLM-as-a-judge.
- [Componentes](componentes.md) — o que faz cada módulo de `src/smarty_energy/`.
- [Dados de entrada](dados.md) — a base Excel e o mapeamento de cargas/geração.
- [Configuração](configuracao.md) — hiperparâmetros e pesos do reward.
