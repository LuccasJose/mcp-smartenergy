---
label: Execução
icon: rocket
order: 80
---

# Execução

## Pipeline completo

```bash
python main.py                 # treina um novo run e abre o dashboard
python main.py --replot        # reabre o run mais recente sem treinar
python main.py --run <run_id>  # reabre um run específico
python main.py --web           # dashboard web (Dash) em localhost:8050
```

O sistema treina os agentes e, ao final, abre o **dashboard** automaticamente.

## O que o pipeline faz

1. Carrega os dados da base (31 dias × 24 h).
2. Instancia os três agentes Q-Learning.
3. Treina por N episódios (cada episódio = 1 dia × 24 timesteps), com early
   stopping: ao final, restaura as Q-tables do melhor checkpoint observado.
4. Gera as curvas de aprendizado (reward e custo por episódio).
5. Avalia **sem agente vs. heurístico vs. RL** em todos os 31 dias do mês.
6. Plota o comparativo do dia com a maior diferença de custo.
7. Analisa três cenários: dia mais nublado, mais ensolarado e de maior consumo
   relativo.
8. Imprime o relatório final com as métricas comparativas.

## Saídas

Os artefatos são gravados em `outputs/`:

- `outputs/runs/<run_id>/` — cada treino versionado: Q-tables, histórico e
  `meta.json` com o CONFIG completo usado. `latest.txt` aponta para o mais
  recente, que é o padrão de `--replot` e dos dashboards.
- `outputs/plots/` — gráficos (curvas de aprendizado, comparativos, cenários).
- `outputs/models/` — layout legado, importado como run "legado" na 1ª execução.

!!!tip Runs compartilhados com o MCP
O [servidor MCP](mcp.md) lê e escreve nesse mesmo `outputs/runs/`
(`load_qtables` / `save_qtables`) — um treino longo daqui pode ser avaliado
por um LLM-juiz sem retreinar.
!!!

!!!tip Treino x teste rápido
O número de episódios é controlado por `n_episodios` em
[`config.py`](configuracao.md). Reduza-o para validações rápidas e aumente-o
para o treino final.
!!!
