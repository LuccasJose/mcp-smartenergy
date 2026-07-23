---
label: Dados de entrada
icon: database
order: 50
---

# Dados de entrada

A fonte é uma planilha Excel local
(`dados/modelo_gestao_energia_fazenda_v8.xlsx`) com duas fazendas
(`FAZ-001`, `FAZ-002`). A fazenda usada é definida por `ID_FAZENDA` no
[`config.py`](configuracao.md) (padrão `FAZ-002`).

!!!info Fonte alternativa
Se a variável `SHEET_ID` estiver definida, o `data_loader` baixa a planilha de
um Google Sheets com o **mesmo esquema** em vez de ler o arquivo local.
!!!

## Abas relevantes

- **Tarifa** — curva horária única em R$/kWh (`Fora Ponta` / `Ponta`), 24 valores.
- **Geracao** — formato **longo**: uma linha por gerador, com `ID_Gerador`,
  `Tipo` (`Solar FV` / `Eólica`) e o valor em `Energia_Gerada_kWh`, por
  fazenda/dia/hora.
- **Cargas** — consumo por equipamento nomeado (`Carga`, `Tipo`, `Consumo_kWh`),
  por fazenda/dia/hora.

A base traz ainda abas de cadastro e apoio (`Cadastro_Fazenda`,
`Cadastro_Cargas`, `Config_Geracao`, `Base_Irradiacao`, `Consumo_Fatura`,
`Resumo_Mensal`) que **não** são consumidas pelo modelo atual.

## Mapeamento de cargas (base → modelo)

A base traz 7 cargas por fazenda; o modelo opera com 5:

| Coluna do modelo | Carga(s) da base |
|---|---|
| `pivo_kw` | `Pivô` |
| `captacao_kw` | `Bomba_Aux` |
| `sede_kw` | `Escritório` + `Cozinha` + `Quarto` (Tipo = `Sede`) |
| `secador_kw` | `Secadora` (carga agrícola controlada pelo agente) |
| `silo_kw` | `Quadro_Auto` (fundo fixo, sempre on) |

!!!warning O secador é uma carga própria
`Secadora` **não** entra em `silo_kw`: ela é controlada pelo agente de consumo
(bit 2) e tem meta diária de 20 kWh. Q-tables treinadas antes dessa separação
não são comparáveis com as atuais.
!!!

## Saída do `data_loader`

`carregar_dados()` devolve:

- **`dias`** — lista de DataFrames (um por dia) com as colunas
  `hora, solar_kw, eolico_kw, pivo_kw, captacao_kw, sede_kw, secador_kw, silo_kw, data`.
- **`tarifa_24`** — vetor `(24,)` com a tarifa em R$/kWh por hora.

`descrever_base(dias, tarifa_24)` complementa com os metadados descritivos
(nº de dias, range de datas, tarifa mín/máx, horas de pico) usados pela tool
`get_dataset_info` do [servidor MCP](mcp.md).

!!!success Conservação de energia
A geração mensal somada da `FAZ-002` (solar 6680,0 + eólica 2072,8 =
**8752,8 kWh**) confere exatamente com a aba `Resumo_Mensal` da própria planilha.
!!!
