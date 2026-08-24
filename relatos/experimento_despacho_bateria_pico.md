# Experimento - Despacho da Bateria no Pico

**Data:** 2026-08-23  
**Objetivo:** avaliar se o controle IQL passa a reservar e descarregar energia
da bateria preferencialmente no período tarifário de pico (18h-20h).

## Alterações avaliadas

1. Estado temporal com sete períodos: 0-5h, 6-11h, 12-15h, 16-17h,
   18-19h, 20h e 21-23h.
2. Ações de bateria: carregar, manter e descarga de 25 %, 50 % ou 100 % do
   déficit horário.
3. `bonus_descarga_pico=0.5` por kWh AC efetivamente entregue pela bateria
   durante o pico.
4. Diagnóstico de bloqueios: sem déficit, SOC mínimo e throughput esgotado.

As mudanças preservam os limites físicos de SOC, eficiência, throughput e PCC.
O modelo continua sem carregar a bateria usando energia importada da rede.

## Protocolo

- Dados: 31 dias de janeiro de 2025, Fazenda Buritis.
- Treino: Hysteretic IQL, 20 mil episódios por seed para comparação exploratória.
- Seleção: checkpoint greedy, usando o subconjunto held-out já definido no
  `IQLSystem`.
- Avaliação: política greedy, SOC propagado entre dias.
- Seeds: 11, 29 e 47.

## Resultado exploratório inicial (3 seeds, 20 mil episódios)

| Métrica média | Descarga parcial sem shaping | Com `bonus_descarga_pico=0.5` |
|---|---:|---:|
| Custo médio | R$ 64,62/dia | **R$ 64,35/dia** |
| Descarga no pico | 21,87 kWh/mês | **32,16 kWh/mês** |
| Descarga fora do pico | 261,55 kWh/mês | **243,47 kWh/mês** |

O bônus pequeno aumentou a descarga no pico em aproximadamente 47 % e reduziu
a descarga fora do pico em aproximadamente 7 %, sem aumento do custo médio na
amostra inicial de três seeds.

## Resultado reprodutível (5 seeds, 20 mil episódios)

Comando executado:

```bash
PYTHONPATH=src .venv/bin/python scripts/avaliar_despacho_bateria.py \
  --episodios 20000 --seeds 11 29 47 61 83
```

O arquivo completo está em
`outputs/avaliacao_despacho_bateria_multiseed.json`.

| Métrica | Média | Mediana | Desvio padrão |
|---|---:|---:|---:|
| Custo médio diário | R$ 64,56 | R$ 65,38 | R$ 1,77 |
| Rede média diária | 93,52 kWh | 94,67 kWh | 2,81 kWh |
| Descarga no pico | 38,20 kWh/mês | 38,07 kWh/mês | 14,54 kWh |
| Descarga fora do pico | 252,38 kWh/mês | 262,71 kWh/mês | 18,51 kWh |
| Parcela da descarga no pico | 13,03 % | 13,19 % | 4,52 p.p. |
| Pedidos de descarga efetivos | 22,84 % | 24,36 % | 7,00 p.p. |

**Leitura:** o shaping elevou a descarga no pico em relação ao experimento
sem shaping, mas a maior parte da descarga ainda ocorre fora do pico e a
variância entre seeds é alta. A configuração atual é uma melhoria de
instrumentação e direcionamento, não um resultado final conclusivo.

## Calibração do bônus de descarga no pico

As mesmas cinco seeds e 20 mil episódios foram avaliados para pesos adicionais.
Os arquivos completos são `outputs/avaliacao_despacho_bateria_bonus_1_0.json` e
`outputs/avaliacao_despacho_bateria_bonus_1_5.json`.

| `bonus_descarga_pico` | Custo mediano | Descarga pico mediana | Parcela no pico mediana | Dispersão do custo |
|---:|---:|---:|---:|---:|
| 0,5 | R$ 65,38/dia | 38,07 kWh/mês | 13,19 % | R$ 1,77 |
| 1,0 | R$ 64,43/dia | **45,31 kWh/mês** | **14,17 %** | **R$ 0,73** |
| 1,5 | **R$ 64,16/dia** | 34,47 kWh/mês | 12,09 % | R$ 1,77 |

**Decisão provisória:** manter `0,5` como default no `CONFIG`. O peso 1,0 é o
melhor candidato para um experimento confirmatório por combinar menor custo
mediano, maior descarga no pico e menor dispersão. O peso 1,5 não é promovido:
apesar de custo mediano menor, reduz o despacho no pico e mantém alta variância.

## Runs gerados

| Run | Configuração | Custo médio | Descarga no pico | Descarga fora do pico |
|---|---|---:|---:|---:|
| `2026-08-23_120207` | estado temporal, 3 ações originais | R$ 67,84/dia | 40,84 kWh/mês | 265,06 kWh/mês |
| `2026-08-23_120925` | estado temporal + descarga parcial | **R$ 62,56/dia** | 36,81 kWh/mês | 270,05 kWh/mês |
| `2026-08-23_122526` | estado temporal + parcial + shaping | R$ 65,61/dia | **42,93 kWh/mês** | **232,90 kWh/mês** |

Os runs canônicos são resultados de uma seed e não devem ser tratados como
resultado estatístico final. O run `2026-08-23_122526` tem o comportamento de
despacho mais alinhado ao objetivo; o run `2026-08-23_120925` teve o menor custo
na amostra de uma seed.

## KPIs publicados pelo MCP

A tool `get_battery_dispatch_stats` expõe:

- `descarga_pico_media_dia_kwh`;
- `pct_descarga_no_pico`;
- `taxa_descarga_efetiva_pct`;
- `soc_medio_apos_18h_pct` e `soc_medio_apos_20h_pct`;
- pedidos por nível de descarga e motivos de bloqueio.

Esses indicadores aparecem na página **Equipamentos** do dashboard MCP.

## Limitações e decisão

- Cinco seeds dão uma linha de base reprodutível, mas ainda há dispersão alta
  no despacho de pico. Um experimento de calibração do bônus deve comparar
  valores candidatos pelo mesmo protocolo antes de eleger uma configuração.
- Ainda ocorre descarga fora do pico, especialmente quando há déficit de carga.
  Isso pode ser economicamente racional no modelo e não deve ser proibido sem
  uma regra de negócio ou análise tarifária adicional.
- O próximo experimento recomendado é confirmar `bonus_descarga_pico=1,0` com
  mais seeds ou um holdout temporal, reportando mediana, dispersão e intervalos
  de confiança antes de substituir os resultados oficiais do TCC.