import numpy as np
import pandas as pd


def carregar_dados(path: str) -> tuple[list[pd.DataFrame], np.ndarray]:
    """Carrega dados de geração, consumo e tarifa do arquivo Excel.

    Retorna:
        dias      — lista de DataFrames, um por dia do mês, com colunas:
                    hora, solar_kw, eolico_kw, pivo_kw, captacao_kw,
                    sede_kw, silo_kw, data
        tarifa_24 — array (24,) com a tarifa em R$/kWh por hora
    """
    xl = pd.read_excel(path, sheet_name=None)

    # Tarifa azul (pico 18h–21h)
    t_row = xl["Tarifa"][xl["Tarifa"]["Tipo_Tarifa"] == "Tarifa azul"].iloc[0]
    tarifa_24 = np.array([float(t_row[h]) for h in range(24)])

    # Geração: fonte 6 = solar, 7 = eólico
    ger = xl["Geracao"].copy()
    ger["Data"] = pd.to_datetime(ger["Data"])

    # Cargas: 6 = pivô, 7 = captação, 8 = sede, 9 = silo
    car = xl["Cargas"].copy()
    car["Data"] = pd.to_datetime(car["Data"])

    dias = []
    for data in sorted(ger["Data"].unique()):
        g = ger[ger["Data"] == data]
        c = car[car["Data"] == data]

        solar    = g[g["ID_Fonte"] == 6].set_index("Hora")["Energia_Gerada_kWh"]
        eolico   = g[g["ID_Fonte"] == 7].set_index("Hora")["Energia_Gerada_kWh"]
        pivo     = c[c["ID_equipamento"] == 6].set_index("Hora")["Energia_Consumida_kWh"]
        captacao = c[c["ID_equipamento"] == 7].set_index("Hora")["Energia_Consumida_kWh"]
        sede     = c[c["ID_equipamento"] == 8].set_index("Hora")["Energia_Consumida_kWh"]
        silo     = c[c["ID_equipamento"] == 9].set_index("Hora")["Energia_Consumida_kWh"]

        dia = pd.DataFrame({"hora": range(24)})
        dia["solar_kw"]    = dia["hora"].map(solar).fillna(0.0)
        dia["eolico_kw"]   = dia["hora"].map(eolico).fillna(0.0)
        dia["pivo_kw"]     = dia["hora"].map(pivo).fillna(0.0)
        dia["captacao_kw"] = dia["hora"].map(captacao).fillna(0.0)
        dia["sede_kw"]     = dia["hora"].map(sede).fillna(0.0)
        dia["silo_kw"]     = dia["hora"].map(silo).fillna(0.0)
        dia["data"]        = data
        dias.append(dia)

    return dias, tarifa_24
