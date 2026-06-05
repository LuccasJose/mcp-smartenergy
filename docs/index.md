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
quatro cargas (pivô central, bomba de captação, sede administrativa e silo).
A tarifa é do tipo **Azul**, com ponta entre 18h–21h
(R$ 1,10/kWh contra R$ 0,68/kWh fora de ponta).

Três agentes independentes — cada um com sua própria Q-table — compartilham um
**reward cooperativo** e aprendem, em conjunto, a operar a bateria, cortar
cargas interruptíveis e definir o teto de consumo horário.

## Resultados finais

Após as otimizações de Hysteretic Q-Learning e o rebalanceamento de rewards:

| Métrica | Resultado |
|---|---|
| Economia no custo diário médio | **57,2 %** |
| Redução da dependência da rede | **64,0 %** |
| Violações de segurança (SOC e PCC) | **Zero** |

## Por onde começar

- [Instalação](instalacao.md) — preparar o ambiente Python e as dependências.
- [Execução](execucao.md) — rodar o pipeline completo e abrir o dashboard.
- [Arquitetura](arquitetura.md) — entender os três agentes e o reward cooperativo.
- [Componentes](componentes.md) — o que faz cada módulo de `src/smarty_energy/`.
- [Dados de entrada](dados.md) — a base Excel e o mapeamento de cargas/geração.
- [Configuração](configuracao.md) — hiperparâmetros e pesos do reward.
