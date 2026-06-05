import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dados"
OUT.mkdir(exist_ok=True)
# Fixture sintética (2 dias) — nome propositalmente distinto da base real
# (modelo_gestao_energia_fazenda_v8.xlsx) para nunca sobrescrevê-la.
# Para usá-la: DATA_PATH=dados/sample_base.xlsx
PATH = OUT / "sample_base.xlsx"

# Create tarifa sheet
horas = [f"{h:02d}:00" for h in range(24)]
tarifa = pd.DataFrame({
    "Hora": horas,
    "Energia_R$/kWh": np.linspace(0.5, 0.9, 24)
})

# Create geracao sheet for two days (formato longo: uma linha por gerador)
rows = []
for day in ["2025-01-01", "2025-01-02"]:
    for h in range(24):
        base = {
            "ID_Fazenda": "FAZ-002",
            "Data_Hora": f"{day} {h:02d}:00:00",
            "Hora": h,
        }
        rows.append({**base, "ID_Gerador": "SOL-MED", "Tipo": "Solar FV",
                     "Energia_Gerada_kWh": max(0, 10 * np.sin((h-6)/24*2*np.pi))})
        rows.append({**base, "ID_Gerador": "EOL-MED", "Tipo": "Eólica",
                     "Energia_Gerada_kWh": 2.0 if h%6==0 else 0.5})
ger = pd.DataFrame(rows)

# Create cargas sheet
rows = []
for day in ["2025-01-01", "2025-01-02"]:
    for h in range(24):
        base = {
            "ID_Fazenda": "FAZ-002",
            "Data_Hora": f"{day} {h:02d}:00:00",
            "Hora": h,
        }
        # Pivô
        rows.append({**base, "Carga": "Pivô", "Tipo": "Irrigacao", "Consumo_kWh": 3.0 if 4<=h<12 else 0.0})
        # Bomba_Aux
        rows.append({**base, "Carga": "Bomba_Aux", "Tipo": "Bomba", "Consumo_kWh": 1.5 if h in (6,7,12,13) else 0.0})
        # Secadora
        rows.append({**base, "Carga": "Secadora", "Tipo": "Secador", "Consumo_kWh": 0.8 if h%8==0 else 0.0})
        # Quadro_Auto
        rows.append({**base, "Carga": "Quadro_Auto", "Tipo": "Quadro", "Consumo_kWh": 0.6 if h%12==0 else 0.0})
        # Sede (office)
        rows.append({**base, "Carga": "Luzes", "Tipo": "Sede", "Consumo_kWh": 0.3 if 8<=h<18 else 0.1})

car = pd.DataFrame(rows)

with pd.ExcelWriter(PATH) as writer:
    tarifa.to_excel(writer, sheet_name="Tarifa", index=False)
    ger.to_excel(writer, sheet_name="Geracao", index=False)
    car.to_excel(writer, sheet_name="Cargas", index=False)

print(f"Wrote sample data to {PATH}")
