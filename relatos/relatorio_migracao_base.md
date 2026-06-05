# Relatório — Migração da Base de Dados

**Data:** 21/05/2026
**Escopo:** Substituição da base antiga (`dados/base_antiga.xlsx`) pela base nova (`dados/base_nova.xlsx`).

## 1. Motivação

A base nova traz dados mais estruturados e completos da fazenda, com duas
fazendas distintas e cargas nomeadas por equipamento. O esquema é
**totalmente diferente** do anterior — não foi uma troca de arquivo, e sim a
reescrita do leitor de dados (`data_loader.py`).

## 2. Comparação de esquema

| Aspecto | base_antiga | base_nova |
|---|---|---|
| Geração | aba `Geracao`, separada por `ID_Fonte` (6=solar, 7=eólico) | aba `Geracao`, colunas `Solar_kW` / `Eólica_kW` |
| Cargas | aba `Cargas`, por `ID_equipamento` (6–9) | aba `Cargas`, coluna `Carga` com nome do equipamento |
| Tarifa | linha "Tarifa azul" (colunas 0–23) | aba `Tarifa` com curva horária (`Fora Ponta` / `Ponta`) |
| Fazendas | 1 única | **2** — `FAZ-001` (Pequena) e `FAZ-002` (Média) |
| Fonte | Google Sheets (download) | arquivo local `dados/base_nova.xlsx` |

## 3. Arquivos alterados

### `src/smarty_energy/config.py`
- `SHEET_ID` → `""` (a base nova é local; antes baixava o Google Sheets antigo).
- `DATA_PATH` → `dados/base_nova.xlsx`.
- Nova variável **`ID_FAZENDA`** (padrão `"FAZ-002"`), sobrescrevível via env var.

### `src/smarty_energy/data_loader.py`
Reescrito para o novo esquema, mantendo **inalterada** a saída esperada pelo
restante do sistema (colunas `hora, solar_kw, eolico_kw, pivo_kw, captacao_kw,
sede_kw, silo_kw, data`). Nenhum outro módulo precisou de ajuste.

### `CONTEXT.md`
Seção "Dados de Entrada" atualizada para refletir o novo esquema e o
mapeamento de cargas.

## 4. Seleção de fazenda

O ambiente é de fazenda única. A base nova tem duas:

- **`FAZ-002` (Fazenda São Pedro, Média)** — escolhida como padrão. Todos os
  equipamentos Ativos (Pivô 60 kW, Bomba_Aux 6 kW, Secadora 12 kW); compatível
  com a escala do `CONFIG` atual (bateria 24 kWh, PCC 65,8 kW).
- `FAZ-001` (Fazenda Boa Vista, Pequena) — `Bomba_Aux` e `Secadora` estão
  **Inativas** (consumo zero), o que esvaziaria a lógica de bomba/secador.

A escolha é controlada por `ID_FAZENDA` no `config.py`.

## 5. Mapeamento de cargas

A base nova tem 7 cargas por fazenda; o modelo opera com 4. Mapeamento aplicado
(decisão: aproveitar 100% da energia da base):

| Coluna do modelo | Carga(s) da base nova |
|---|---|
| `pivo_kw` | `Pivô` |
| `captacao_kw` | `Bomba_Aux` |
| `sede_kw` | `Escritório` + `Cozinha` + `Quarto` (Tipo `Sede`) |
| `silo_kw` | `Secadora` + `Quadro_Auto` (demais cargas agrícolas) |

## 6. Validação

- 31 dias carregados (Janeiro 2025), 8 colunas corretas.
- Episódio do ambiente executa sem erro.
- **Conservação de energia confirmada** — totais batem com a aba `Resumo_Mensal`
  da base para a `FAZ-002`:
  - Geração: solar 6679,98 + eólica 53,13 = **6733,11 kWh**
  - Consumo: pivô 16047,60 + captação 1606,38 + sede 1922,65 + silo 4644,71 =
    **24221,34 kWh**

## 7. Pontos de atenção

1. **`bomba_cap_nominal_kw` = 15,0** no `CONFIG`: o ambiente força a bomba a
   esse valor nas horas agendadas, mas o `Bomba_Aux` real da `FAZ-002` é
   ~5–6 kW. Recomenda-se revisar esse override para condizer com a base nova.
2. Trocar `ID_FAZENDA` para `FAZ-001` deixa bomba e secador sem dados reais.
3. `dados/base_antiga.xlsx` foi mantido na pasta (pode ser removido).

---

# Atualização — Migração para `modelo_gestao_energia_fazenda_v8.xlsx`

**Data:** 04/06/2026
**Escopo:** Substituição de `dados/base_nova.xlsx` pela base
`dados/modelo_gestao_energia_fazenda_v8.xlsx`.

## A. Mudança de esquema

A nova base é compatível em quase tudo (**Tarifa** e **Cargas** mantêm estrutura
e nomes). A única quebra é a aba **Geracao**, que passou de **formato largo**
(colunas `Solar_kW` / `Eólica_kW`) para **formato longo**: uma linha por gerador,
discriminada pela coluna `Tipo` (`Solar FV` / `Eólica`), com o valor em
`Energia_Gerada_kWh` (colunas: `Data_Hora, Hora, ID_Fazenda, ID_Gerador, Tipo,
Energia_Gerada_kWh`).

Abas novas disponíveis e ainda não consumidas pelo modelo: `Cadastro_Fazenda`,
`Cadastro_Cargas`, `Config_Geracao`, `Base_Irradiacao`, `Consumo_Fatura`,
`Resumo_Mensal`.

## B. Arquivos alterados

- **`config.py`**: `DATA_PATH` → `dados/modelo_gestao_energia_fazenda_v8.xlsx`.
- **`data_loader.py`**: leitura da geração filtra por `Tipo` (`Solar FV` /
  `Eólica`) sobre `Energia_Gerada_kWh`, em vez das antigas colunas
  `Solar_kW` / `Eólica_kW`. Saída (`solar_kw, eolico_kw, …`) inalterada.
- **`scripts/make_sample_data.py`**: passa a gerar a aba `Geracao` no formato
  longo e grava com o novo nome de arquivo.
- **`CONTEXT.md`**: seção "Dados de Entrada" atualizada.

## C. Validação

- 31 dias × 24h carregados sem erro.
- **Conservação de geração confirmada** contra a aba `Resumo_Mensal` da própria
  base (FAZ-002): solar 6680,0 + eólica 2072,8 = **8752,8 kWh**, idêntico ao
  `Geração_kWh` da Fazenda São Pedro.
- Testes (`tests/test_environment.py`) usam fixtures sintéticas e seguem passando.
