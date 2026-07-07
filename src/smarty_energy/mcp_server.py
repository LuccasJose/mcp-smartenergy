"""
Servidor MCP que expõe o ambiente de energia como ferramentas (braço
"LLM-via-MCP" do benchmark).

Por que existe
--------------
No benchmark de trade-offs queremos separar duas coisas:
  - a contribuição do *raciocínio do LLM* na qualidade da decisão, e
  - o *overhead do protocolo MCP* (transporte) no custo operacional.

O braço "LLM-direto" (``llm_policy.criar_decisor_anthropic``) chama a API com
tool-use, sem MCP. Este módulo expõe as MESMAS ações como tools de um servidor
MCP, de modo que a diferença de latência entre os dois braços isola o custo do
protocolo:  overhead_MCP ≈ latência(via-MCP) − latência(direto).

Ferramentas expostas
---------------------
  - ``estado_atual()``  : devolve o estado contínuo da hora corrente (read-only).
  - ``decidir_controle(a_arm, a_cons, a_ger)`` : registra as 3 ações de controle,
    com schema enum restringindo ao espaço de ações válido (1ª defesa contra
    ação inválida). Reusa ``llm_policy.TOOL_DECIDIR`` como contrato.

Execução
--------
Requer o SDK ``mcp`` (``pip install mcp``). Não é importado pelo harness offline
— este módulo só é carregado para o braço que mede o overhead do protocolo.

    python -m smarty_energy.mcp_server      # inicia o servidor (stdio)

O estado é injetado por ``definir_estado(est)`` a cada passo da simulação (o
loop em Python continua no controle dos 24 timesteps); o LLM, como cliente MCP,
lê ``estado_atual`` e responde ``decidir_controle``.
"""

from __future__ import annotations

from .llm_policy import ACOES_ARM, ACOES_CONS, ACOES_GER

# Estado compartilhado entre o loop de simulação e as tools do servidor.
# O loop chama ``definir_estado`` antes de pedir a decisão ao LLM.
_ESTADO_ATUAL: dict = {}
_ULTIMA_DECISAO: dict = {}


def definir_estado(est: dict) -> None:
    """Publica o estado da hora corrente para a tool ``estado_atual``."""
    global _ESTADO_ATUAL
    _ESTADO_ATUAL = dict(est)


def ultima_decisao() -> dict | None:
    """Devolve a última decisão registrada pelo LLM via ``decidir_controle``."""
    return dict(_ULTIMA_DECISAO) if _ULTIMA_DECISAO else None


def _registrar_decisao(a_arm: int, a_cons: int, a_ger: int) -> dict:
    """Valida e registra uma decisão (compartilhado pela tool MCP)."""
    if a_arm not in ACOES_ARM or a_cons not in ACOES_CONS or a_ger not in ACOES_GER:
        raise ValueError(
            f"ação fora do espaço válido: a_arm∈{ACOES_ARM}, "
            f"a_cons∈0..7, a_ger∈{ACOES_GER}; recebido ({a_arm},{a_cons},{a_ger})"
        )
    global _ULTIMA_DECISAO
    _ULTIMA_DECISAO = {"a_arm": int(a_arm), "a_cons": int(a_cons), "a_ger": int(a_ger)}
    return _ULTIMA_DECISAO


def construir_servidor():
    """Constrói o servidor FastMCP com as duas tools (import tardio do SDK)."""
    from mcp.server.fastmcp import FastMCP  # requer `pip install mcp`

    mcp = FastMCP("smart-energy")

    @mcp.tool()
    def estado_atual() -> dict:
        """Estado contínuo da hora corrente: SOC, geração, tarifa, estresse, etc."""
        return _ESTADO_ATUAL

    @mcp.tool()
    def decidir_controle(a_arm: int, a_cons: int, a_ger: int) -> dict:
        """Define as 3 ações de controle de energia para a hora atual.

        a_arm  : bateria  — 0=carregar, 1=manter, 2=descarregar
        a_cons : cortes   — soma de bits 1=pivô, 2=bomba, 4=secador (0=nenhum)
        a_ger  : teto kW  — 0=20, 1=30, 2=40
        """
        return _registrar_decisao(a_arm, a_cons, a_ger)

    return mcp


if __name__ == "__main__":
    construir_servidor().run()
