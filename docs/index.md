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

## Resultados experimentais atuais

A arquitetura atual usa sete períodos temporais, descarga parcial de bateria e
incentivo leve para descarga efetiva no pico. Em cinco seeds de 20 mil
episódios, com SoC propagado nos 31 dias da base v8:

| Métrica | Média | Mediana | Desvio padrão |
|---|---:|---:|---:|
| Custo médio diário | R$ 64,56 | R$ 65,38 | R$ 1,77 |
| Energia importada por dia | 93,52 kWh | 94,67 kWh | 2,81 kWh |
| Descarga no pico | 38,20 kWh/mês | 38,07 kWh/mês | 14,54 kWh |
| Parcela da descarga no pico | 13,03 % | 13,19 % | 4,52 p.p. |

As restrições de PCC e SoC foram respeitadas nas cinco avaliações. A variância
entre seeds ainda é relevante, por isso o número oficial do TCC deve ser
atualizado somente após a confirmação do protocolo experimental. Consulte
`relatos/experimento_despacho_bateria_pico.md` para runs, parâmetros e dados
reproduzíveis.

> O run histórico `2026-06-19_145038` (R$ 63,25/dia) usava uma codificação de
> estado e ações de bateria anterior e não é comparável diretamente ao modelo
> atual.

## Por onde começar

- [Instalação](instalacao.md) — preparar o ambiente Python e as dependências.
- [Execução](execucao.md) — rodar o pipeline completo e abrir o dashboard.
- [Execução do MCP](execucao-mcp.md) — subir o servidor e o dashboard Streamlit.
- [Arquitetura](arquitetura.md) — os três agentes, o estado e o reward cooperativo.
- [Servidor MCP](mcp.md) — catálogo de ferramentas e o loop LLM-as-a-judge.
- [Componentes](componentes.md) — o que faz cada módulo de `src/smarty_energy/`.
- [Dados de entrada](dados.md) — a base Excel e o mapeamento de cargas/geração.
- [Configuração](configuracao.md) — hiperparâmetros e pesos do reward.
