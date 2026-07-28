# Auditoria de fidelidade à base v8

Fazenda: **FAZ-002** · Fonte: base v8 (SHEET_ID=1rBTaMm3…)

Gerado por `scripts/auditar_base.py`. A base v8 é a fonte da verdade.

## Item 1a — Nominais de carga (CONFIG × base)

| Parâmetro (CONFIG) | valor | base Cons_Max | veredito |
|---|---|---|---|
| pivo_nominal_kw | 8.0 | 8.000 | OK |
| bomba_cap_nominal_kw | 17.6 | 17.600 | OK |
| secador_max_kw | 2.4 | 2.367 | OK |

## Item 1b — Parâmetros de engenharia (sem dado na base)

A base não fixa capacidade/eficiência/SoC da bateria; são premissas.

| Parâmetro | valor CONFIG | origem |
|---|---|---|
| bateria_cap_kwh | 24.0 | premissa de engenharia |
| soc_min_pct | 15.0 | premissa de engenharia |
| soc_max_pct | 95.0 | premissa de engenharia |
| eficiencia_carga | 0.92 | premissa de engenharia |
| eficiencia_descarga | 0.95 | premissa de engenharia |
| bat_throughput_max_kwh | 48.0 | premissa de engenharia |

## Item 1c — Restrições HARD e limites (CONFIG × base/spec)

| Restrição | CONFIG | referência | veredito |
|---|---|---|---|
| PCC (kW) | 65.8 | 65.8 | OK |
| Inversor FV (kW) | 50.0 | 50.0 | OK |
| Eólico nominal (kW) | 10.0 | 10.0 | OK |
| Pivô horas/dia | 8 | 8 | OK |
| Secador meta (kWh) | 20.0 | 20.0 | OK |
| Bomba cronograma | [3, 4, 9, 10, 15, 16, 21, 22] | 8h/dia fora do pico | OK |
| Tetos gerente (kW) | {0: 20.0, 1: 30.0, 2: 40.0} | — | informativo |

## Item 4 — Valor do consumo por máquina (kWh/dia, média dos 31 dias)

| Máquina | demanda bruta | entregue pelo env | env/bruto |
|---|---|---|---|
| pivo | 69.14 | 64.00 | 93% |
| bomba/captacao | 135.64 | 140.80 | 104% |
| sede | 62.17 | 61.00 | 98% |
| secador | 54.40 | 54.40 | 100% |
| silo | 4.62 | 4.62 | 100% |
| **TOTAL** | **325.97** | **324.82** | **100%** |

**Faturado (Resumo_Mensal, FAZ-002):** 10105 kWh/mês = 325.97 kWh/dia

- demanda bruta / faturado = 100.0%
- entregue pelo env / faturado = 99.6%

> Nota: o env aplica `max(base_hora, nominal)` no pivô durante o lock de 8h e na bomba nas horas agendadas. A coluna `env/bruto` acima mostra se esse override infla ou reduz o consumo de cada máquina frente ao perfil horário da base.

## Conclusões

- **Item 1:** os três nominais de carga do CONFIG batem com a base (`Cons_Max`); as restrições HARD e os limites de rede também. Os parâmetros da bateria (capacidade, SoC, η, throughput) não têm contrapartida na base — são premissas de engenharia, não erros.
- **Item 4:** o consumo total entregue = 100% da demanda bruta e 100% do faturado — **bate**. Por máquina, o cronograma HARD distorce o perfil: pivô 93% (lock de 8h não cobre todas as horas do perfil real) e bomba 104% (forçada ao Cons_Max nas horas agendadas). As duas distorções ~se cancelam no total. É consequência de projeto das restrições HARD, não erro de valor — decidir se o realismo por-máquina importa para o TCC.
