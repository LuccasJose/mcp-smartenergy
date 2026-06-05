import io
import urllib.request

import numpy as np
import pandas as pd

from .config import SHEET_ID, DATA_PATH, ID_FAZENDA

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


def carregar_dados(path: str | None = None) -> tuple[list[pd.DataFrame], np.ndarray]:
    """Carrega dados de geração, consumo e tarifa da base nova.

    Prioridade da fonte:
        1. Google Sheets (se SHEET_ID configurado)
        2. Arquivo local (path ou DATA_PATH)

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
