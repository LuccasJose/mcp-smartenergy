"""Avalia a estabilidade do despacho da bateria em múltiplas seeds.

Uso:
    PYTHONPATH=src .venv/bin/python scripts/avaliar_despacho_bateria.py
    PYTHONPATH=src .venv/bin/python scripts/avaliar_despacho_bateria.py \
        --episodios 20000 --seeds 11 29 47 61 83

O script não persiste Q-tables nem altera o CONFIG. Ele treina uma política
independente por seed, avalia em modo greedy com SOC propagado e salva um JSON
reproduzível em ``outputs/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smarty_energy.agents import avaliar_politica, construir_agentes
from smarty_energy.config import CONFIG, FRACOES_DESCARGA, OUTPUT_DIR, ajustar_decay
from smarty_energy.data_loader import carregar_dados
from smarty_energy.environment import FazendaEnergyEnv
from smarty_energy.mcp.tracker import MetricsTracker
from smarty_energy.training import treinar


def _resumo(valores: list[float]) -> dict:
    dados = np.asarray(valores, dtype=float)
    return {
        "media": round(float(np.mean(dados)), 4),
        "mediana": round(float(np.median(dados)), 4),
        "desvio_padrao": round(float(np.std(dados)), 4),
        "min": round(float(np.min(dados)), 4),
        "max": round(float(np.max(dados)), 4),
    }


def executar_seed(seed: int, dias, tarifa, n_episodios: int,
                  bonus_descarga_pico: float) -> dict:
    np.random.seed(seed)
    cfg = ajustar_decay(CONFIG, n_episodios)
    cfg["bonus_descarga_pico"] = bonus_descarga_pico
    agentes = construir_agentes(cfg)
    hist = treinar(dias, tarifa, agentes, cfg, log=lambda _msg: None)
    tracker = MetricsTracker()

    resultado = avaliar_politica(
        lambda env, est: tuple(
            agentes[nome].agir(env.discretizar(est), explorando=False)
            for nome in ("armazenamento", "consumo", "gerente")
        ),
        dias,
        tarifa,
        cfg=cfg,
        env_cls=FazendaEnergyEnv,
        n_dias=len(dias),
        tracker=tracker,
        tracker_key="multi_seed",
        propagar_soc=True,
    )
    bateria = tracker.get_battery_dispatch_stats("multi_seed")
    return {
        "seed": seed,
        "best_ep": hist["best_ep"],
        "best_custo_med_rs_dia": round(float(hist["best_custo_med"]), 4),
        "custo_medio_dia_rs": round(resultado["custo_medio_dia_rs"], 4),
        "rede_media_dia_kwh": round(resultado["rede_media_dia_kwh"], 4),
        "violacoes_soc_media_h_dia": round(resultado["violacoes_soc_media_h_dia"], 4),
        "descarga_pico_kwh": round(bateria["descarga_pico_kwh"], 4),
        "descarga_fora_pico_kwh": round(bateria["descarga_fora_pico_kwh"], 4),
        "pct_descarga_no_pico": bateria["pct_descarga_no_pico"],
        "taxa_descarga_efetiva_pct": bateria["taxa_descarga_efetiva_pct"],
        "soc_medio_apos_18h_pct": bateria["soc_medio_apos_18h_pct"],
        "soc_medio_apos_20h_pct": bateria["soc_medio_apos_20h_pct"],
        "bloqueios_descarga": bateria["bloqueios_descarga"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia despacho de bateria em múltiplas seeds.")
    parser.add_argument("--episodios", type=int, default=20_000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 29, 47, 61, 83])
    parser.add_argument("--bonus-descarga-pico", type=float, default=CONFIG["bonus_descarga_pico"])
    parser.add_argument(
        "--saida",
        type=Path,
        default=OUTPUT_DIR / "avaliacao_despacho_bateria_multiseed.json",
    )
    args = parser.parse_args()
    if args.episodios < 1:
        parser.error("--episodios deve ser >= 1")
    if args.bonus_descarga_pico < 0:
        parser.error("--bonus-descarga-pico deve ser >= 0")

    dias, tarifa = carregar_dados()
    resultados = []
    for seed in args.seeds:
        resultado = executar_seed(seed, dias, tarifa, args.episodios,
                      args.bonus_descarga_pico)
        resultados.append(resultado)
        print(
            f"seed={seed}  custo=R${resultado['custo_medio_dia_rs']:.2f}/dia  "
            f"descarga_pico={resultado['descarga_pico_kwh']:.2f} kWh  "
            f"pico={resultado['pct_descarga_no_pico']:.1f}%"
        )

    metricas = (
        "custo_medio_dia_rs", "rede_media_dia_kwh", "descarga_pico_kwh",
        "descarga_fora_pico_kwh", "pct_descarga_no_pico",
        "taxa_descarga_efetiva_pct",
    )
    payload = {
        "n_episodios": args.episodios,
        "seeds": args.seeds,
        "n_dias_avaliados": len(dias),
        "config": {
            "bonus_descarga_pico": args.bonus_descarga_pico,
            "fracoes_descarga": FRACOES_DESCARGA,
            "soc_propagado": True,
        },
        "resultados_por_seed": resultados,
        "resumo": {metrica: _resumo([r[metrica] for r in resultados]) for metrica in metricas},
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nResultado salvo em: {args.saida}")
    for metrica, resumo in payload["resumo"].items():
        print(f"{metrica}: mediana={resumo['mediana']:.4f}  dp={resumo['desvio_padrao']:.4f}")


if __name__ == "__main__":
    main()