"""Página Fazendas FEMS — criar fazendas, gerar datasets e trocar a fazenda ativa.

Integra o backend FEMS (FastAPI + Postgres, repo Smart_Energy_Data/fems) ao
fluxo do dashboard: a fazenda é criada na API do FEMS, o dataset Parquet é
gerado pela CLI oficial do fems (`gerar_dataset.py --completo`) e o servidor
MCP é apontado para a pasta nova via tool `switch_dataset`.

Pré-requisito para criar/listar fazendas: API FEMS no ar
    cd Smart_Energy_Data/fems && uv run uvicorn fems.main:app --port 8010
(configurável por env FEMS_API_URL). Trocar para um dataset JÁ GERADO não
precisa da API.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import (
    MCPServerError,
    require_setup,
    switch_dataset,
)

FEMS_API_URL = os.getenv("FEMS_API_URL", "http://localhost:8010")
FEMS_REPO = Path(os.getenv("FEMS_REPO",
                           str(_SRC.parent.parent / "Smart_Energy_Data" / "fems")))

st.title("Fazendas FEMS")
st.caption(
    "Crie fazendas simuladas no FEMS, gere o dataset e aponte o servidor para "
    "ela — para treinar e comparar modelos em fazendas diferentes."
)
with st.expander("Cadastro, geração de dados e ativação da base"):
    st.markdown("""
**Cadastro FEMS** descreve a fazenda e os perfis usados pelo gerador. Cadastrar
não gera os Parquet e não altera a política do MCP. A criação depende da API
FEMS; geração depende do repositório e do ambiente de execução do FEMS.

**Porte** associa os identificadores de geração solar e eólica pequena, média
ou grande. **Área (ha)** é um atributo do cadastro, não o número de amostras.
Irrigação e sede informam grupos de cargas ao gerador. Esses campos não alteram
automaticamente os limites físicos do motor SmartEnergy; compatibilidade deve
ser conferida antes de comparar modelos de fazendas diferentes.

**Seed FEMS** controla a geração da série simulada. É diferente da seed de
treinamento, que controla a exploração dos agentes, e da seed de divisão, que
controla os conjuntos. Trocar a seed FEMS pode trocar os próprios dados.
Um calendário completo não comprova medições reais nem representatividade da fazenda.

**Dataset** é a pasta dos Parquet já gerados. **ID da fazenda** filtra os
registros internos e pode ser diferente do nome da pasta. **Mês 1 a 12** recorta
esse mês; **0** preserva todos os meses disponíveis, inclusive de vários anos
se estiverem na pasta. Não há filtro de ano nessa ativação.

**Ativação no MCP** substitui a base ativa e reinicia políticas, snapshots,
traces e comparações da análise legada. Runs salvos em disco são preservados.
Planos de divisões já criados mantêm seus snapshots isolados; não passam a usar
automaticamente a nova fazenda. Ativação não equivale a criar treino/validação/teste.
""")

if not require_setup():
    st.stop()


def _api_get(path: str):
    with httpx.Client(base_url=FEMS_API_URL, timeout=10) as c:
        r = c.get(path)
        r.raise_for_status()
        return r.json()


def _api_post(path: str, payload: dict):
    with httpx.Client(base_url=FEMS_API_URL, timeout=30) as c:
        r = c.post(path, json=payload)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        return r.json()


try:
    fazendas = _api_get("/v1/fazendas")
    api_ok = True
except Exception as e:  # noqa: BLE001 — API fora do ar é estado esperado
    fazendas, api_ok = [], False
    st.warning(
        f"API FEMS inacessível em {FEMS_API_URL} — criar/listar fazendas está "
        "desabilitado. Suba com: `cd Smart_Energy_Data/fems && uv run uvicorn "
        f"fems.main:app --port 8010`. Detalhe: {type(e).__name__}"
    )

# ── 1. Fazendas cadastradas ────────────────────────────────────────────────

st.header("1. Fazendas cadastradas no FEMS")
if api_ok:
    if fazendas:
        st.dataframe(
            [{"id": f["id"], "nome": f["nome"], "porte": f["tipo"],
              "irrigação": f["tem_irrigacao"], "solar": f["id_solar"],
              "eólica": f["id_eolica"], "ano": f["ano"], "seed": f["seed"]}
             for f in fazendas],
            use_container_width=True,
        )
    else:
        st.info("Nenhuma fazenda cadastrada ainda — crie uma abaixo.")

    with st.expander("Criar nova fazenda"):
        with st.form("nova_fazenda"):
            c1, c2 = st.columns(2)
            fid = c1.text_input("ID", placeholder="FAZ-003",
                                help="Identificador do cadastro, enviado à API e usado depois para selecionar a fazenda nos Parquet.")
            nome = c2.text_input("Nome", placeholder="Fazenda Nova",
                                 help="Nome descritivo da fazenda. Não substitui seu identificador interno.")
            c3, c4, c5 = st.columns(3)
            porte = c3.selectbox(
                "Porte", ["Pequena", "Média", "Grande"], index=1,
                help="Define o tipo da fazenda e os perfis SOL-/EOL- PEQ, MED ou GRD enviados ao FEMS.",
            )
            tamanho = c4.number_input(
                "Tamanho (ha)", 10, 10000, 320,
                help="Área da fazenda em hectares, registrada no FEMS; não configura diretamente a bateria do motor.",
            )
            ano = c5.number_input(
                "Ano da série", 2020, 2035, 2025,
                help="Ano solicitado ao gerador. Um ano comum tem 8.760 horas e um bissexto 8.784; confira a cobertura gerada.",
            )
            _SUFIXO = {"Pequena": "PEQ", "Média": "MED", "Grande": "GRD"}
            c6, c7, c8 = st.columns(3)
            seed = c6.number_input(
                "Seed (reprodutibilidade)", 0, 2**31 - 1, 20250101,
                help="Seed de geração dos dados, não de treino. Reprodução depende também da configuração e versão do FEMS.",
            )
            tem_irrigacao = c7.checkbox(
                "Irrigação (pivô/bomba/secador)", value=True,
                help="Envia tem_irrigacao ao FEMS. A presença e os perfis das cargas são definidos pelo gerador.",
            )
            sede_completa = c8.checkbox(
                "Sede (escritório+cozinha+quarto)", value=True,
                help="Habilita ou desabilita conjuntamente os três campos de cadastro da sede.",
            )

            if st.form_submit_button("Criar fazenda", type="primary",
                                      help="Grava um novo cadastro na API FEMS. Não gera dados nem ativa a fazenda no MCP."):
                if not fid.strip() or not nome.strip():
                    st.error("Preencha ID e nome.")
                else:
                    payload = {
                        "id": fid.strip(), "nome": nome.strip(),
                        "tamanho_ha": int(tamanho), "tipo": porte,
                        "tem_escritorio": sede_completa, "tem_cozinha": sede_completa,
                        "tem_quarto": sede_completa, "tem_irrigacao": tem_irrigacao,
                        "id_solar": f"SOL-{_SUFIXO[porte]}",
                        "id_eolica": f"EOL-{_SUFIXO[porte]}",
                        "id_bateria": "BAT-001",
                        "tarifa": "AZUL_HOROSSAZONAL",
                        "seed": int(seed), "ano": int(ano),
                    }
                    try:
                        _api_post("/v1/fazendas", payload)
                        st.success(f"Fazenda {fid} criada. Gere o dataset abaixo.")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Falha ao criar: {e}")

# ── 2. Gerar dataset ───────────────────────────────────────────────────────

st.header("2. Gerar dataset da fazenda")
st.caption(
    "Série horária em Parquet a partir do cadastro FEMS: 8.760 horas em um ano comum "
    "ou 8.784 em um bissexto, se a geração cobrir todo o calendário."
)

if api_ok and fazendas:
    faz_ids = [f["id"] for f in fazendas]
    fid_gerar = st.selectbox("Fazenda", faz_ids,
                            help="Cadastro enviado ao gerador. Usa ano, seed e perfis registrados no FEMS; não troca a base ativa.")
    out_dir = FEMS_REPO / "out" / fid_gerar.lower().replace("-", "_")
    st.caption(f"Saída: {out_dir}")

    if st.button("Gerar dataset", type="primary",
                  help="Executa a CLI do FEMS e escreve arquivos na pasta de saída exibida. "
                       "Pode levar minutos; o tratamento de arquivos existentes depende do gerador externo."):
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        cmd = [uv, "run", "python", "scripts/gerar_dataset.py",
               "--fazenda-id", fid_gerar, "--output", str(out_dir), "--completo"]
        with st.spinner(f"Gerando dataset de {fid_gerar}..."):
            proc = subprocess.run(cmd, cwd=FEMS_REPO, capture_output=True,
                                  text=True, timeout=600)
        if proc.returncode == 0:
            st.success(f"Dataset gerado em {out_dir}")
            st.code(proc.stdout[-800:] or "(sem saída)")
        else:
            st.error("Falha ao gerar o dataset:")
            st.code((proc.stderr or proc.stdout)[-1200:])
else:
    st.info("Com a API FEMS no ar e uma fazenda cadastrada, gere o dataset aqui.")

# ── 3. Trocar a fazenda ativa do servidor ──────────────────────────────────

st.header("3. Usar uma fazenda no servidor MCP")
st.caption(
    "Aponta o servidor para um dataset já gerado. ATENÇÃO: é um reset completo "
    "— políticas treinadas e comparações são descartadas (salve um modelo antes, "
    "se quiser voltar). Modelos salvos não são afetados."
)

# Datasets disponíveis: os gerados no repo fems + o versionado no próprio MCP.
_candidatos: list[Path] = []
_out = FEMS_REPO / "out"
if _out.is_dir():
    _candidatos += [d for d in sorted(_out.iterdir())
                    if (d / "consumo.parquet").exists()]
_versionado = _SRC.parent / "dados" / "fems_faz_002"
if (_versionado / "consumo.parquet").exists():
    _candidatos.append(_versionado)

if not _candidatos:
    st.info("Nenhum dataset encontrado — gere um na etapa 2.")
else:
    escolha_ds = st.selectbox("Dataset", [str(d) for d in _candidatos],
                              help="Pasta descoberta no ambiente do dashboard. O servidor MCP também precisa acessar "
                                   "esse caminho; selecionar a pasta ainda não ativa a base.")
    c1, c2, c3 = st.columns([2, 1, 1])
    id_no_dataset = c1.text_input(
        "ID da fazenda no dataset", value="",
        placeholder="vazio = FAZ-002 (default do config)",
        help="O id_fazenda gravado dentro dos parquets (o ID usado ao criar).",
    )
    mes = c2.number_input("Mês (0 = ano inteiro)", 0, 12, 1,
                           help="1 seleciona janeiro, 12 dezembro; 0 carrega todos os meses presentes. "
                                "Se houver vários anos, o filtro por mês não os separa.")
    if c3.button("Ativar fazenda", type="primary", use_container_width=True,
                  help="Troca o dataset compartilhado no MCP e descarta o estado ativo de treino/avaliação legado. "
                       "Não apaga os runs salvos nem altera planos de divisões já criados."):
        try:
            res = switch_dataset(escolha_ds, id_fazenda=id_no_dataset.strip(),
                                 mes=int(mes))
            if "erro" in res:
                st.error(res["erro"])
            else:
                st.success(
                    f"Fazenda ativa: {res['id_fazenda']} — {res['n_dias']} dias "
                    f"({res['data_inicio']} → {res['data_fim']}). Estado zerado: "
                    "treine em **Executar análise** ou carregue um modelo desta fazenda."
                )
        except MCPServerError as e:
            st.error(str(e))
