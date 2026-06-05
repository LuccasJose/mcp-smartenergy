---
label: Arquitetura
icon: organization
order: 70
---

# Arquitetura Multi-Agentes

Três agentes independentes — cada um com sua própria Q-table — compartilham o
mesmo **reward cooperativo**.

| Agente | Responsabilidade | Ações |
|---|---|---|
| **Armazenamento** | Gestão da bateria | `0` = Carregar · `1` = Manter · `2` = Descarregar |
| **Consumo** | Corte de cargas interruptíveis | `0` = Nada · `1` = Corta pivô · `2` = Corta captação · `3` = Corta ambos |
| **Gerente de Carga** | Teto de consumo horário | `0` = Conservador (20 kW) · `1` = Moderado (30 kW) · `2` = Liberal (40 kW) |

## Espaço de estados (120 estados discretos)

Tupla `(bucket_hora, bucket_soc, bucket_solar, bucket_tarifa)`:

- `hora // 6` → 4 valores (madrugada / manhã / tarde / noite)
- `soc // 20` → 5 valores (0–20 % / 20–40 % / … / 80–100 %)
- **solar**: low (<5 kW) / med (5–15 kW) / high (>15 kW) → 3 valores
- **tarifa**: normal / pico → 2 valores

## Reward cooperativo

```text
reward = - w_custo * custo_rede
         - pen_soc * (SOC < 15%)
         - pen_teto * (consumo >= teto)
         - pen_producao * (captação cortada)
         + bonus_excedente * kWh_excedente
         + bonus_soc_ok * (30% < SOC < 80%)
```

## Hysteretic Q-Learning

Para lidar com a **não-estacionariedade** típica de sistemas multi-agente, o
aprendizado usa duas taxas:

- **Taxa otimista (`alpha` = 0.1)** — aprende rápido quando o resultado supera o
  esperado.
- **Taxa pessimista (`beta` = 0.01)** — esquece devagar bons resultados quando
  ocorrem erros de coordenação.

## Baseline heurístico

Para comparação, há agentes baseados em regras com um **índice de estresse
financeiro** (0–100) calculado a partir da tarifa atual e do nível da bateria.
O estresse determina cortes de carga e teto de consumo via limiares fixos
(`if/else`).
