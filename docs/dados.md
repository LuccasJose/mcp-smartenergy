---
label: Dados de entrada
icon: database
order: 50
---

# Dados de entrada

A prioridade de `carregar_dados` é: FEMS Parquet quando `FEMS_DATASET_DIR`
está configurado; Google Sheets quando `SHEET_ID` está configurado; Excel
local por `path` ou `DATA_PATH` somente quando as duas fontes anteriores estão
desativadas. A fazenda padrão é definida por `ID_FAZENDA` (padrão `FAZ-002`).

!!!info R-DAD-001: seleção explícita
Um caminho Excel passado à função não sobrepõe FEMS ou Sheets configurados.
Falhas da fonte escolhida são propagadas; não há fallback automático para
outra base. Os testes substituem leitores externos, sem executar downloads.
!!!

## Dataset FEMS

O diretório deve conter `consumo.parquet`, `geracao.parquet` e
`consumo_fatura.parquet`. `_carregar_fems` filtra cargas e geração pela fazenda;
`mes=1..12` seleciona o mês e `mes=0` usa todos. Dias são ordenados pela data da
geração e normalizados em 24 horas. Os rótulos de geração são `solar_fv` e `eolica`.
Cargas usam os nomes do mapeamento abaixo; as cargas do tipo Sede são somadas.

O loader preenche lacunas horárias de carga/geração com zero. Isso é um
comportamento observado, não comprovação de qualidade de dados. A tarifa usa
a primeira ocorrência por hora na fatura ordenada, sem filtrá-la por fazenda
ou mês. Revisar essa suposição antes de usar tarifas distintas por fazenda.
Ausência de dados da fazenda falha, mas validação completa de esquema, horas,
valores e mês vazio ainda não é um contrato certificado pelos testes.

## Abas legadas Excel/Sheets

A planilha v8 contém duas fazendas (`FAZ-001`, `FAZ-002`); Sheets usa o mesmo
esquema. As abas relevantes são:

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
| `secador_kw` | `Secadora` (potência horária da base; bit de corte ignorado no ambiente atual) |
| `silo_kw` | `Quadro_Auto` (fundo fixo, sempre on) |

!!!warning O secador é uma carga própria
`Secadora` **não** entra em `silo_kw`: segue a potência da base e tem meta
diária de 20 kWh. O ambiente atual ignora o bit 2. Q-tables anteriores à separação
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

`descrever_base` deriva o rótulo da fonte das configurações globais, não de
uma identidade imutável do conteúdo carregado. O MCP ajusta esse rótulo ao
trocar o dataset. Isso não equivale a rastreamento completo de proveniência.

## Evidência do piloto

`tests/test_data_loader_fems.py` usa Parquet
temporário com duas fazendas e janeiro/fevereiro sintéticos. Verifica mapeamento,
recorte de mês, tarifa, metadados e prioridade das fontes sem fallback.
Não executa a leitura real de Sheets/Excel nem a suíte de integridade da base
privada. Veja a [visão de domínio](regras-dominio.md) e o [plano](reorganizacao.md).

!!!note Registro histórico da planilha v8
A geração mensal somada da `FAZ-002` (solar 6680,0 + eólica 2072,8 =
**8752,8 kWh**) foi documentada como correspondente à aba `Resumo_Mensal`.
Esse resultado não foi revalidado nesta reorganização e não descreve o FEMS.
!!!
