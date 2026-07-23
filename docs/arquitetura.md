---
label: Arquitetura
icon: organization
order: 70
---

# Arquitetura Multi-Agentes

Três agentes independentes — cada um com sua própria Q-table — compartilham o
mesmo **reward cooperativo**. É a mesma arquitetura nos dois modos de uso: o
pipeline offline e o [servidor MCP](mcp.md) importam o mesmo
`FazendaEnergyEnv` e os mesmos agentes.

| Agente | Responsabilidade | Ações |
|---|---|---|
| **Armazenamento** | Gestão da bateria | `0` = Carregar · `1` = Manter · `2` = Descarregar |
| **Consumo** | Corte de cargas interruptíveis | bitmask de 3 bits: `1` = corta pivô · `2` = corta bomba · `4` = corta secador (`0`…`7`) |
| **Gerente de Carga** | Teto de consumo horário | `0` = Conservador (20 kW) · `1` = Moderado (30 kW) · `2` = Liberal (40 kW) |

## Espaço de estados (2160 estados discretos)

Tupla `(bucket_hora, bucket_soc, bucket_solar, bucket_stress, meta_secador, bucket_bomba)`:

| Variável | Buckets |
|---|---|
| `hora // 6` | 4 (0-5h / 6-11h / 12-17h / 18-23h) |
| `soc // 10` | 10 (0-10 % / 10-20 % / … / 90-100 %) |
| **solar** | 3 (<5 kW / 5-15 kW / >15 kW) |
| **stress** | 3 (<30 / 30-70 / >70 — calculado pelo `AgenteFinanceiro`) |
| **meta secador** | 2 (atingiu a meta diária de 20 kWh?) |
| **bomba** | 3 (<3h / 3-5h / ≥6h operadas) |

Total combinatório: 4 × 10 × 3 × 3 × 2 × 3 = **2160**
(`environment.ESPACO_ESTADOS_TOTAL`). É um teto — parte das combinações é
fisicamente inalcançável, então a cobertura medida contra ele é conservadora.

## Restrições HARD

Aplicadas pelo ambiente, independentemente da ação escolhida:

| Restrição | Regra |
|---|---|
| **R-PIVO** | 8h consecutivas e uma única ativação por dia; durante o lock opera em 8 kW |
| **R-BOMBA** | cronograma fixo nas horas 3-4, 9-10, 15-16 e 21-22 (17,6 kW) — a ação do agente é ignorada |
| **R-SECADOR** | potência real da base; meta diária de 20 kWh com *rescue* tardio a 2,4 kW |
| **R-SEDE** | consumo clampado em ±20 % do ideal; eco-mode (−20 %) com stress ≥ 70 |
| **R-PCC** | importação/exportação ≤ 65,8 kW, mutuamente exclusivas |
| **R-BAT** | throughput diário ≤ 48 kWh, η carga 0,92 / η descarga 0,95 |

## Reward cooperativo

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
```

Os pesos estão em [Configuração](configuracao.md) e podem ser ajustados em
runtime pela tool `configure_reward_weights`.

## Hysteretic Q-Learning

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
- **Sem agente (C0)** — a fazenda "como está hoje": bateria em manter, nenhuma
  carga cortada, teto liberal.
