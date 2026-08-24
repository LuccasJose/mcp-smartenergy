import io
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SHEET_ID, DATA_PATH, ID_FAZENDA, FEMS_DATASET_DIR, FEMS_MES

_EXPORT_URL = "https://docs.google.com/spreadsheets/d/{}/export?format=xlsx"

# ── Mapeamento das cargas da base → colunas do ambiente ───────────────
# A base traz 7 cargas nomeadas por fazenda; o modelo opera com 5:
# pivô, captação, secador (controlado pelo agente), silo (fundo fixo) e sede.
_CARGA_PIVO     = "Pivô"
_CARGA_CAPTACAO = "Bomba_Aux"      # bomba auxiliar = captação
_CARGA_SECADOR  = "Secadora"       # carga agrícola controlada pelo agente
_CARGA_SILO     = "Quadro_Auto"    # carga agrícola de fundo (sempre on, ~0.15 kW)
_TIPO_SEDE      = "Sede"           # Escritório + Cozinha + Quarto

# ── Mapeamento dos geradores (aba Geracao em formato longo) ───────────
# Cada gerador é uma linha por fazenda/hora, discriminada pela coluna Tipo.
_GER_SOLAR  = "Solar FV"
_GER_EOLICA = "Eólica"


def _baixar_excel_drive(sheet_id: str) -> dict[str, pd.DataFrame]:
    """Baixa a planilha do Google Sheets e retorna todas as abas."""
    url = _EXPORT_URL.format(sheet_id)
    print(f"  Baixando planilha do Google Drive...")
    dados = urllib.request.urlopen(url).read()
    return pd.read_excel(io.BytesIO(dados), sheet_name=None)


def _carregar_fems(dataset_dir: str, mes: int = FEMS_MES,
                   id_fazenda: str = ID_FAZENDA) -> tuple[list[pd.DataFrame], np.ndarray]:
    """Carrega um dataset Parquet gerado pelo FEMS (gerar_dataset.py --completo).

    Espera no diretório: consumo.parquet (por carga × hora), geracao.parquet
    (por gerador × hora) e consumo_fatura.parquet (tarifa horária). As cargas
    do FEMS usam os MESMOS nomes da base v8 (Pivô, Bomba_Aux, Secadora,
    Quadro_Auto e tipo Sede); os geradores diferem só no rótulo do tipo
    (solar_fv/eolica em vez de "Solar FV"/"Eólica").

    mes=1..12 recorta um mês (paridade com a base v8 de 31 dias);
    mes=0 usa o ano inteiro.
    """
    d = Path(dataset_dir)
    print(f"  Carregando dataset FEMS de {d}...")
    car = pd.read_parquet(d / "consumo.parquet")
    ger = pd.read_parquet(d / "geracao.parquet")
    fat = pd.read_parquet(d / "consumo_fatura.parquet")

    car = car[car["id_fazenda"] == id_fazenda].copy()
    ger = ger[ger["id_fazenda"] == id_fazenda].copy()
    if car.empty or ger.empty:
        raise ValueError(f"Sem dados para a fazenda {id_fazenda!r} no dataset FEMS.")

    if mes:
        car = car[car["mes"] == mes]
        ger = ger[ger["mes"] == mes]

    # Tarifa: curva horária fixa — primeira ocorrência de cada hora na fatura.
    tarifa_24 = (fat.sort_values("data_hora").groupby("hora")["tarifa_rs"]
                 .first().sort_index().to_numpy(dtype=float))

    car["data"] = car["data_hora"].dt.normalize()
    ger["data"] = ger["data_hora"].dt.normalize()

    dias = []
    for data in sorted(ger["data"].unique()):
        g = ger[ger["data"] == data]
        c = car[car["data"] == data]

        solar    = g[g["tipo"] == "solar_fv"].set_index("hora")["energia_kwh"]
        eolico   = g[g["tipo"] == "eolica"].set_index("hora")["energia_kwh"]
        pivo     = c[c["carga"] == _CARGA_PIVO].set_index("hora")["consumo_kwh"]
        captacao = c[c["carga"] == _CARGA_CAPTACAO].set_index("hora")["consumo_kwh"]
        secador  = c[c["carga"] == _CARGA_SECADOR].set_index("hora")["consumo_kwh"]
        silo     = c[c["carga"] == _CARGA_SILO].set_index("hora")["consumo_kwh"]
        sede     = (c[c["tipo"] == _TIPO_SEDE]
                    .groupby("hora")["consumo_kwh"].sum())

        dia = pd.DataFrame({"hora": range(24)})
        dia["solar_kw"]    = dia["hora"].map(solar).fillna(0.0)
        dia["eolico_kw"]   = dia["hora"].map(eolico).fillna(0.0)
        dia["pivo_kw"]     = dia["hora"].map(pivo).fillna(0.0)
        dia["captacao_kw"] = dia["hora"].map(captacao).fillna(0.0)
        dia["sede_kw"]     = dia["hora"].map(sede).fillna(0.0)
        dia["secador_kw"]  = dia["hora"].map(secador).fillna(0.0)
        dia["silo_kw"]     = dia["hora"].map(silo).fillna(0.0)
        dia["data"]        = data
        dias.append(dia)

    print(f"  {len(dias)} dias carregados do FEMS (fazenda {id_fazenda}).")
    return dias, tarifa_24


def carregar_dados(path: str | None = None) -> tuple[list[pd.DataFrame], np.ndarray]:
    """Carrega dados de geração, consumo e tarifa da base nova.

    Prioridade da fonte:
        1. Dataset Parquet do FEMS (se FEMS_DATASET_DIR configurado)
        2. Google Sheets (se SHEET_ID configurado)
        3. Arquivo local (path ou DATA_PATH)

    A base contém duas fazendas (FAZ-001, FAZ-002); a fazenda usada
    é definida por ID_FAZENDA no config.

    Mapeamento de cargas (base → modelo):
        pivo_kw      ← Pivô
        captacao_kw  ← Bomba_Aux
        sede_kw      ← Escritório + Cozinha + Quarto (Tipo = "Sede")
        secador_kw   ← Secadora (carga agrícola controlada pelo agente)
        silo_kw      ← Quadro_Auto (fundo fixo, sempre on)

    Retorna:
        dias      — lista de DataFrames, um por dia do mês, com colunas:
                    hora, solar_kw, eolico_kw, pivo_kw, captacao_kw,
                    sede_kw, secador_kw, silo_kw, data
        tarifa_24 — array (24,) com a tarifa em R$/kWh por hora
    """
    if FEMS_DATASET_DIR:
        return _carregar_fems(FEMS_DATASET_DIR)
    if SHEET_ID:
        xl = _baixar_excel_drive(SHEET_ID)
    else:
        xl = pd.read_excel(path or DATA_PATH, sheet_name=None)

    # ── Tarifa: curva horária única (Fora Ponta / Ponta) ──────────
    tar = xl["Tarifa"].copy()
    tar["_h"] = tar["Hora"].astype(str).str.slice(0, 2).astype(int)
    tar = tar.sort_values("_h")
    tarifa_24 = tar["Energia_R$/kWh"].to_numpy(dtype=float)

    # ── Geração: formato longo (uma linha por gerador) ────────────
    ger = xl["Geracao"].copy()
    ger = ger[ger["ID_Fazenda"] == ID_FAZENDA].copy()
    ger["data"] = pd.to_datetime(ger["Data_Hora"]).dt.normalize()

    # ── Cargas: nomeadas por equipamento ──────────────────────────
    car = xl["Cargas"].copy()
    car = car[car["ID_Fazenda"] == ID_FAZENDA].copy()
    car["data"] = pd.to_datetime(car["Data_Hora"]).dt.normalize()

    if ger.empty or car.empty:
        raise ValueError(f"Sem dados para a fazenda {ID_FAZENDA!r} na base.")

    dias = []
    for data in sorted(ger["data"].unique()):
        g = ger[ger["data"] == data]
        c = car[car["data"] == data]

        solar    = g[g["Tipo"] == _GER_SOLAR].set_index("Hora")["Energia_Gerada_kWh"]
        eolico   = g[g["Tipo"] == _GER_EOLICA].set_index("Hora")["Energia_Gerada_kWh"]
        pivo     = c[c["Carga"] == _CARGA_PIVO].set_index("Hora")["Consumo_kWh"]
        captacao = c[c["Carga"] == _CARGA_CAPTACAO].set_index("Hora")["Consumo_kWh"]
        secador  = c[c["Carga"] == _CARGA_SECADOR].set_index("Hora")["Consumo_kWh"]
        silo     = c[c["Carga"] == _CARGA_SILO].set_index("Hora")["Consumo_kWh"]
        sede     = (c[c["Tipo"] == _TIPO_SEDE]
                    .groupby("Hora")["Consumo_kWh"].sum())

        dia = pd.DataFrame({"hora": range(24)})
        dia["solar_kw"]    = dia["hora"].map(solar).fillna(0.0)
        dia["eolico_kw"]   = dia["hora"].map(eolico).fillna(0.0)
        dia["pivo_kw"]     = dia["hora"].map(pivo).fillna(0.0)
        dia["captacao_kw"] = dia["hora"].map(captacao).fillna(0.0)
        dia["sede_kw"]     = dia["hora"].map(sede).fillna(0.0)
        dia["secador_kw"]  = dia["hora"].map(secador).fillna(0.0)
        dia["silo_kw"]     = dia["hora"].map(silo).fillna(0.0)
        dia["data"]        = data
        dias.append(dia)

    return dias, tarifa_24


def descrever_base(dias: list[pd.DataFrame], tarifa_24: np.ndarray,
                   id_fazenda: str = ID_FAZENDA) -> dict:
    """Metadados descritivos da base carregada (tool MCP `get_dataset_info`).

    Separado de `carregar_dados` para não mudar a assinatura usada pelo
    pipeline; o servidor chama as duas em sequência no startup.
    """
    return {
        "n_dias": len(dias),
        "id_fazenda": id_fazenda,
        "data_inicio": str(dias[0]["data"].iloc[0])[:10] if dias else None,
        "data_fim":    str(dias[-1]["data"].iloc[0])[:10] if dias else None,
        "tarifa_min_rs_kwh": float(tarifa_24.min()),
        "tarifa_max_rs_kwh": float(tarifa_24.max()),
        "horas_pico": [int(h) for h in range(len(tarifa_24)) if tarifa_24[h] > 0.9],
        "fonte": (f"FEMS ({FEMS_DATASET_DIR})" if FEMS_DATASET_DIR
                  else "Google Sheets" if SHEET_ID else str(DATA_PATH)),
    }
