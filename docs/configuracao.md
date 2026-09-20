---
label: Configuração
icon: gear
order: 40
---

# Configuração

Todos os parâmetros vivem em `src/smarty_energy/config.py`.

## Hiperparâmetros de treino

| Parâmetro | Descrição |
|---|---|
| `n_episodios` | Dias simulados no treinamento |
| `alpha` | Taxa de aprendizado (otimista) |
| `gamma` | Fator de desconto futuro |
| `epsilon_inicial` → `epsilon_final` | Exploração ε-greedy (com decaimento) |
| `epsilon_decay` | Decaimento de ε por episódio |
| `beta` | Taxa de aprendizado pessimista (Hysteretic) |

!!!info Treinos curtos
`epsilon_decay` é calibrado para os 100.000 episódios do pipeline. Para
horizontes menores use `config.ajustar_decay(cfg, n_episodios)`, que recalcula
o decaimento para que ε chegue perto de `epsilon_final` no fim do treino —
é o que o servidor MCP faz automaticamente em `train_agents`.
!!!

## Bateria

| Parâmetro | Valor | Descrição |
|---|---|---|
| `bateria_cap_kwh` | 24.0 | Capacidade da bateria |
| `soc_inicial_pct` | 50.0 | SOC inicial |
| `soc_min_pct` | 15.0 | Limite de descarga; abaixo disso o SOC é crítico |
| `soc_max_pct` | 95.0 | SOC máximo (para de carregar) |
| `eficiencia_carga` | 0.92 | η de carga |
| `eficiencia_descarga` | 0.95 | η de descarga |
| `potencia_max_carga_rede_kw` | 24.0 | Solicitação máxima de carga pela rede no passo de 1 h |
| `tarifa_referencia_arbitragem` | 1.10 | Referência tarifária para elegibilidade da carga pela rede |

As ações de armazenamento são `0` (carregar com excedente), `1` (manter) e
`2`/`3`/`4` para descarregar 25 %, 50 % ou 100 % do déficit horário; `5` tenta
excedente e depois rede elegível. SoC, eficiência e throughput são aplicados
pela bateria; o PCC é aplicado pelo ambiente ao balanço da rede. Isso não
substitui uma verificação conjunta de conservação ao atingir o PCC.
Veja os [contratos técnicos](arquitetura.md) e as [regras de domínio](regras-dominio.md).

## Pesos do reward cooperativo

O custo financeiro é o **sinal dominante** da recompensa, evitando que os
agentes manipulem o SOC da bateria em detrimento da economia real.

| Componente | Peso | Papel |
|---|---|---|
| `w_custo` | 8.0 | Custo diário — sinal dominante |
| `pen_soc` | 12.0 | Barreira de segurança do SOC |
| `pen_teto` | 8.0 | Estouro do teto de consumo |
| `pen_producao` | 5.0 | Captação cortada |
| `bonus_excedente` | 0.5 | Incentivo à exportação de excedente |
| `bonus_soc_ok` | 1.0 | SOC em faixa saudável |
| `bonus_descarga_pico` | 3.0 | Bônus por kWh AC descarregado no pico |

O conjunto de pesos exposto pelo servidor pode ser alterado em runtime pela tool
`configure_reward_weights` do [servidor MCP](mcp.md) — as restrições físicas
(PCC, SOC, capacidade da bateria) permanecem imutáveis.

## Limites operacionais

| Parâmetro | Valor | Descrição |
|---|---|---|
| `pcc_max_kw` | 65.8 | Limite do ponto de conexão (import/export) |
| `inversor_fv_max_kw` | 50.0 | Teto do inversor fotovoltaico |
| `eolico_nominal_kw` | 10.0 | Potência nominal do aerogerador |
| `bat_throughput_max_kwh` | 30.0 | Energia DC diária movimentada, somando carga e descarga; não é contagem de ciclos |
| `pivo_nominal_kw` | 8.0 | Potência do pivô durante o lock de 8h |
| `bomba_cap_nominal_kw` | 17.6 | Potência da bomba na hora agendada |
| `secador_max_kw` | 2.4 | Parâmetro legado; o passo atual segue a potência horária da base, sem rescue ativo |
| `secador_meta_kwh` | 20.0 | Meta diária de energia do secador |

## Tetos do Gerente de Carga

```python
TETOS_KW = {0: 20.0, 1: 30.0, 2: 40.0}  # conservador / moderado / liberal
```

!!!note
Esta página resume os parâmetros mais relevantes. Consulte o `config.py` para a
lista completa, incluindo penalidades operacionais e shaping por máquina.
!!!
