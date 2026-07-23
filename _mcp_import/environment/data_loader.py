"""
Carga de dados da fazenda — espelha smarty_energy/data_loader.py.

Sempre baixa do Google Sheets (público) no startup. Retorna lista de
DataFrames diários e o vetor de tarifa horária.
"""

import io
import urllib.request

import numpy as np
import pandas as pd

from config import SHEET_ID, ID_FAZENDA

_EXPORT_URL = "https://docs.google.com/spreadsheets/d/{}/export?format=xlsx"

# Mapeamento da base nova → colunas do ambiente
_CARGA_PIVO     = "Pivô"
_CARGA_CAPTACAO = "Bomba_Aux"
_CARGAS_SILO    = ("Secadora", "Quadro_Auto")
_TIPO_SEDE      = "Sede"


def _baixar_excel_drive(sheet_id: str) -> dict[str, pd.DataFrame]:
    url = _EXPORT_URL.format(sheet_id)
    dados = urllib.request.urlopen(url, timeout=30).read()
    return pd.read_excel(io.BytesIO(dados), sheet_name=None)


def carregar_dados(
    sheet_id: str = SHEET_ID,
    id_fazenda: str = ID_FAZENDA,
) -> tuple[list[pd.DataFrame], np.ndarray, dict]:
    """Baixa a planilha pública e devolve dias e tarifa.

    Returns:
        (dias, tarifa_24, meta)
            dias     — lista de DataFrames, um por dia, colunas:
                        hora, solar_kw, eolico_kw, pivo_kw, captacao_kw,
                        sede_kw, silo_kw, data
            tarifa_24 — array (24,) com R$/kWh por hora
            meta     — dict com informações descritivas (n_dias, fazenda, data_inicio, ...)
    """
    xl = _baixar_excel_drive(sheet_id)

    # Tarifa horária
    tar = xl["Tarifa"].copy()
    tar["_h"] = tar["Hora"].astype(str).str.slice(0, 2).astype(int)
    tar = tar.sort_values("_h")
    tarifa_24 = tar["Energia_R$/kWh"].to_numpy(dtype=float)

    # Geração da fazenda alvo
    ger = xl["Geracao"].copy()
    ger = ger[ger["ID_Fazenda"] == id_fazenda].copy()
    ger["data"] = pd.to_datetime(ger["Data_Hora"]).dt.normalize()

    # Cargas da fazenda alvo
    car = xl["Cargas"].copy()
    car = car[car["ID_Fazenda"] == id_fazenda].copy()
    car["data"] = pd.to_datetime(car["Data_Hora"]).dt.normalize()

    if ger.empty or car.empty:
        raise ValueError(f"Sem dados para a fazenda {id_fazenda!r} na base.")

    dias = []
    for data in sorted(ger["data"].unique()):
        g = ger[ger["data"] == data]
        c = car[car["data"] == data]

        solar    = g.set_index("Hora")["Solar_kW"]
        eolico   = g.set_index("Hora")["Eólica_kW"]
        pivo     = c[c["Carga"] == _CARGA_PIVO].set_index("Hora")["Consumo_kWh"]
        captacao = c[c["Carga"] == _CARGA_CAPTACAO].set_index("Hora")["Consumo_kWh"]
        silo     = (c[c["Carga"].isin(_CARGAS_SILO)]
                    .groupby("Hora")["Consumo_kWh"].sum())
        sede     = (c[c["Tipo"] == _TIPO_SEDE]
                    .groupby("Hora")["Consumo_kWh"].sum())

        dia = pd.DataFrame({"hora": range(24)})
        dia["solar_kw"]    = dia["hora"].map(solar).fillna(0.0)
        dia["eolico_kw"]   = dia["hora"].map(eolico).fillna(0.0)
        dia["pivo_kw"]     = dia["hora"].map(pivo).fillna(0.0)
        dia["captacao_kw"] = dia["hora"].map(captacao).fillna(0.0)
        dia["sede_kw"]     = dia["hora"].map(sede).fillna(0.0)
        dia["silo_kw"]     = dia["hora"].map(silo).fillna(0.0)
        dia["data"]        = data
        dias.append(dia)

    meta = {
        "n_dias": len(dias),
        "id_fazenda": id_fazenda,
        "data_inicio": str(dias[0]["data"].iloc[0])[:10],
        "data_fim":    str(dias[-1]["data"].iloc[0])[:10],
        "tarifa_min_rs_kwh": float(tarifa_24.min()),
        "tarifa_max_rs_kwh": float(tarifa_24.max()),
        "horas_pico": [int(h) for h in range(24) if tarifa_24[h] > 0.9],
    }
    return dias, tarifa_24, meta
