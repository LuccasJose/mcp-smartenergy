# Walkthrough — Otimização do SmartEnergy MAS

## Resumo

Duas otimizações foram aplicadas ao sistema multi-agente SmartEnergy para melhorar a redução de custo energético na fazenda. O resultado foi uma **economia de 57.2% no custo diário** e **64% menos uso da rede elétrica** em relação ao baseline heurístico.

---

## Alteração 1: Hysteretic Q-Learning

### Problema
O IQL (Independent Q-Learning) padrão sofre de **não-estacionariedade**: cada agente vê o ambiente mudando porque os outros agentes estão aprendendo ao mesmo tempo. Isso causa oscilação nos Q-values e coordenação frágil.

### Solução
Implementar **duas taxas de aprendizado** no método `aprender()` do agente:
- **α = 0.1** para TD-errors positivos (resultado melhor que esperado → aprende rápido)
- **β = 0.01** para TD-errors negativos (resultado pior que esperado → esquece devagar)

Isso torna os agentes **otimistas sobre coordenação** — eles mantêm memória dos bons resultados conjuntos mesmo quando um parceiro comete um erro pontual.

### Arquivo modificado

#### [agents.py](./Smart_Energy/src/smarty_energy/agents.py)

```diff
 class AgenteQL:
     def __init__(self, n_acoes, nome, cfg=CONFIG):
         self.epsilon   = cfg["epsilon_inicial"]
         self.alpha     = cfg["alpha"]
+        self.beta      = cfg.get("beta", 0.01)  # taxa de aprendizado pessimista (Hysteretic)
         self.gamma     = cfg["gamma"]
         ...

     def aprender(self, s, a, r, s2, done):
         q_atual = self.q_table[s][a]
         q_alvo  = r if done else r + self.gamma * np.max(self.q_table[s2])
-        self.q_table[s][a] += self.alpha * (q_alvo - q_atual)
+        td_error = q_alvo - q_atual
+        lr = self.alpha if td_error >= 0 else self.beta
+        self.q_table[s][a] += lr * td_error
         self.n_updates += 1
```

### Referência acadêmica
> Matignon, L., Laurent, G. J., & Le Fort-Piat, N. (2007). *Hysteretic Q-Learning: an algorithm for decentralized reinforcement learning in cooperative multi-agent teams.* IEEE/RSJ International Conference on Intelligent Robots and Systems.

---

## Alteração 2: Rebalanceamento dos pesos do reward

### Problema
Os agentes aprendiam a evitar violações (SOC, PCC, teto) mas **não reduziam o custo energético**, porque:

| Componente | Peso anterior | Potencial diário | Problema |
|---|---|---|---|
| `bonus_soc_ok` | +5.0/h | **+120 pts/dia** | Fácil de ganhar, domina o reward |
| `pen_soc` | -30.0/h | **-720 pts/dia** | Agentes evitam isso antes de tudo |
| `w_custo × custo` | 1.5 × ~R$40 | **-60 pts/dia** | Irrelevante comparado às penalidades |

O custo pesava apenas **~60 pontos no dia**, enquanto manter SOC saudável valia **+120 pontos**. O agente ganhava mais "ficando parado" do que reduzindo custo.

### Solução
Rebalancear os pesos para que o **custo seja o sinal dominante**:

### Arquivo modificado

#### [config.py](./Smart_Energy/src/smarty_energy/config.py)

```diff
-    # Pesos do reward cooperativo
-    "w_custo": 1.5,
-    "w_estresse": 1.0,
-    "pen_soc": 30.0,
-    "pen_teto": 15.0,
-    "pen_producao": 10.0,
-    "pen_pcc": 20.0,
-    "bonus_excedente": 0.2,
-    "bonus_soc_ok": 5.0,
-    "pen_pivo_quebra": 25.0,
-    "pen_bomba_ciclo": 15.0,
-    "pen_secador_meta": 40.0,
-    "pen_sede_desvio": 10.0,
+    # Pesos do reward cooperativo (rebalanceados — custo como sinal dominante)
+    "w_custo": 8.0,             # ↑ custo diário agora pesa ~320 pts
+    "w_estresse": 0.5,          # ↓ reduzido para não competir com custo
+    "pen_soc": 15.0,            # ↓ forte, mas não esmaga o sinal de custo
+    "pen_teto": 8.0,            # ↓ idem
+    "pen_producao": 5.0,        # ↓
+    "pen_pcc": 10.0,            # ↓
+    "bonus_excedente": 0.5,     # ↑ mais incentivo para exportar energia
+    "bonus_soc_ok": 1.0,        # ↓ evita "gamificação" do SOC
+    "pen_pivo_quebra": 12.0,    # ↓
+    "pen_bomba_ciclo": 8.0,     # ↓
+    "pen_secador_meta": 20.0,   # ↓
+    "pen_sede_desvio": 5.0,     # ↓
```

### Novo balanço de sinais

| Componente | Peso novo | Potencial diário | Proporção |
|---|---|---|---|
| **`w_custo × custo`** | **8.0 × ~R$40** | **~320 pts/dia** | **Dominante** ✅ |
| `bonus_soc_ok` | 1.0/h | ~24 pts/dia | Auxiliar |
| `pen_soc` | 15.0/h | ~360 pts/dia | Barreira de segurança |
| `bonus_excedente` | 0.5 × tarifa | Variável | Incentivo extra |

---

## Resultados

### Curvas de Aprendizado

![Curvas de aprendizado mostrando reward subindo e custo caindo ao longo dos 20.000 episódios](./outputs/plots/curva_aprendizado.png)

- Custo médio caiu de **R$41.22** (primeiros 50 ep.) para **R$22.01** (últimos 50 ep.) — **redução de 46.6%** durante treinamento

### Avaliação Mensal (31 dias — Janeiro 2025)

| Métrica | Heurístico | RL | Variação |
|---|---:|---:|---:|
| **Custo (R$/dia)** | R$ 49.79 | R$ 21.32 | **-57.2%** |
| **kWh da rede / dia** | 69.01 | 24.83 | **-64.0%** |
| Violações SOC / dia | 0.00 | 0.00 | — |
| Reward médio / dia | -528.11 | -179.27 | +66.1% |

### Comparativo no Melhor Dia (28/01/2025)

![Comparativo Heurístico vs RL no dia 28/01/2025, mostrando 64.8% de economia](./outputs/plots/comparativo_dia.png)

- Heurístico: R$ 82.71 → RL: R$ 29.14 (**-64.8%**)
- O RL aprendeu a carregar a bateria durante o horário solar e descarregar no pico tarifário

### Cenários

![Análise por cenário: Nublado, Ensolarado e Alto Consumo](./outputs/plots/cenarios.png)

| Cenário | Custo Heurístico | Custo RL | Economia |
|---|---:|---:|---:|
| Nublado (16/01) | R$ 86.39 | R$ 51.91 | **-39.9%** |
| Ensolarado (11/01) | R$ 41.53 | R$ 3.02 | **-92.7%** |
| Alto Consumo (16/01) | R$ 86.39 | R$ 51.91 | **-39.9%** |

> [!TIP]
> O cenário ensolarado mostra o maior ganho (-92.7%) porque o RL aproveita melhor o excedente solar — carregando a bateria estrategicamente e exportando energia.

---

## Verificação

- ✅ Treinamento completou 20.000 episódios sem erros
- ✅ Zero violações de SOC no RL (mesma segurança que o heurístico)
- ✅ 80 estados visitados por cada agente (espaço bem coberto)
- ✅ 480.000 updates de Q-table por agente
- ✅ Q-tables salvas em `outputs/models/`
- ✅ Plots gerados em `outputs/plots/`
