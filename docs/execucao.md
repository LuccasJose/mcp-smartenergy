---
label: Execução
icon: rocket
order: 80
---

# Execução

## Pipeline completo

```bash
python main.py
```

O sistema treina os agentes e, ao final, abre o **dashboard** automaticamente.

## O que o pipeline faz

1. Carrega os dados do Excel (31 dias × 24 h).
2. Instancia os três agentes Q-Learning.
3. Treina por N episódios (cada episódio = 1 dia aleatório × 24 timesteps).
4. Gera as curvas de aprendizado (reward e custo por episódio).
5. Avalia **RL vs. heurístico** em todos os 31 dias do mês.
6. Plota o comparativo do dia com a maior diferença de custo.
7. Analisa três cenários: dia mais nublado, mais ensolarado e de maior consumo
   relativo.
8. Imprime o relatório final com as métricas comparativas.

## Saídas

Os artefatos são gravados em `outputs/`:

- `outputs/plots/` — gráficos (curvas de aprendizado, comparativos, cenários).
- `outputs/models/` — Q-tables treinadas (`.pkl`).

!!!tip Treino x teste rápido
O número de episódios é controlado por `n_episodios` em
[`config.py`](configuracao.md). Reduza-o para validações rápidas e aumente-o
para o treino final.
!!!
