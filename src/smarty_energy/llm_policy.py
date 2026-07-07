"""
Política de controle baseada em LLM (braço "com MCP" do benchmark).

Substitui os três agentes Q-Learning por um LLM que, a cada passo horário,
decide as três ações de controle (bateria / cortes de carga / teto de consumo).

Desenho central
---------------
``PoliticaLLM`` expõe o **mesmo** método ``agir(est) -> (a_arm, a_cons, a_ger)``
que o loop de avaliação já usa, de modo que ``rodar_llm`` em evaluation.py é um
clone de ``rodar_rl`` trocando apenas o decisor — mantendo ambiente, dias,
reward e métricas idênticos (A/B controlado).

A política é desacoplada do *transporte*: recebe um ``decisor`` injetável
(callable ``est -> RespostaDecisor``). Isso permite três cenários sem mudar a
política:
  - ``decisor_stub``           : determinístico, offline, sem custo (testes);
  - ``criar_decisor_anthropic``: chamada direta à API (braço "LLM-direto");
  - decisor via MCP            : ver mcp_server.py (braço "LLM-via-MCP").

Toda decisão é instrumentada (latência, tokens, fallback) para alimentar o
Eixo 2 do benchmark (custo operacional). Respostas inválidas/erros acionam o
**fallback heurístico** e são contabilizadas — nunca quebram a simulação.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .agents import AgentesHeuristicos
from .config import CONFIG

# ──────────────────────────────────────────────────────────────
# Espaço de ações (fonte única da verdade — usada no schema das tools)
# ──────────────────────────────────────────────────────────────
ACOES_ARM = (0, 1, 2)              # 0=carregar 1=manter 2=descarregar
ACOES_CONS = tuple(range(8))       # bits: 1=pivo 2=bomba 4=secador (0..7)
ACOES_GER = (0, 1, 2)              # 0=conservador(20kW) 1=moderado(30kW) 2=liberal(40kW)


@dataclass
class RespostaDecisor:
    """Resultado bruto de um decisor para uma única decisão.

    ``acoes`` é None quando o decisor não conseguiu produzir ações válidas
    (erro de rede, timeout, JSON malformado) — nesse caso ``erro`` descreve o
    motivo e a política aciona o fallback.
    """
    acoes: tuple[int, int, int] | None
    tokens_in: int = 0
    tokens_out: int = 0
    erro: str | None = None
    raw: str = ""


@dataclass
class EventoDecisao:
    """Métrica operacional de uma decisão (Eixo 2 do benchmark)."""
    hora: int
    latencia_ms: float
    tokens_in: int
    tokens_out: int
    fallback: bool
    motivo: str | None
    acoes: tuple[int, int, int]


def acoes_validas(acoes) -> bool:
    """Valida que a tripla está dentro do espaço de ações do ambiente."""
    try:
        a_arm, a_cons, a_ger = acoes
    except (TypeError, ValueError):
        return False
    return (a_arm in ACOES_ARM and a_cons in ACOES_CONS and a_ger in ACOES_GER)


class PoliticaLLM:
    """Política de controle por LLM, plugável no harness de avaliação.

    Args:
        decisor  : callable ``est -> RespostaDecisor``.
        fallback : agentes de regras usados quando o LLM falha (default:
                   AgentesHeuristicos, os mesmos do braço "Heurístico").
        cfg      : configuração do ambiente.
    """

    def __init__(self, decisor, *, fallback: AgentesHeuristicos | None = None,
                 cfg: dict = CONFIG):
        self.decisor = decisor
        self.fallback = fallback or AgentesHeuristicos()
        self.cfg = cfg
        self.eventos: list[EventoDecisao] = []

    # -- decisão heurística de fallback (mesma lógica do braço Heurístico) --
    def _fallback(self, est: dict) -> tuple[int, int, int]:
        stress = self.fallback.stress_financeiro(est)
        return (
            self.fallback.armazenamento(est),
            self.fallback.consumo(est, stress),
            self.fallback.gerente(est, stress),
        )

    def agir(self, est: dict) -> tuple[int, int, int]:
        """Decide as 3 ações para o estado atual, registrando métricas.

        Nunca levanta exceção: erro/timeout/ação inválida → fallback contado.
        """
        t0 = time.perf_counter()
        resp: RespostaDecisor
        try:
            resp = self.decisor(est)
        except Exception as e:  # rede, timeout, SDK — tudo vira fallback
            resp = RespostaDecisor(acoes=None, erro=f"excecao:{type(e).__name__}:{e}")
        latencia_ms = (time.perf_counter() - t0) * 1000.0

        if resp.erro is None and acoes_validas(resp.acoes):
            acoes = tuple(int(x) for x in resp.acoes)
            fallback, motivo = False, None
        else:
            acoes = self._fallback(est)
            fallback = True
            motivo = resp.erro or f"acao_invalida:{resp.acoes!r}"

        self.eventos.append(EventoDecisao(
            hora=int(est["hora"]), latencia_ms=latencia_ms,
            tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
            fallback=fallback, motivo=motivo, acoes=acoes,
        ))
        return acoes

    # -- agregados para o relatório de trade-off --------------------------
    def resumo_operacional(self) -> dict:
        """Agrega os EventoDecisao em métricas do Eixo 2."""
        ev = self.eventos
        if not ev:
            return {}
        lat = sorted(e.latencia_ms for e in ev)
        n = len(lat)
        return {
            "n_decisoes"   : n,
            "latencia_ms_mediana": lat[n // 2],
            "latencia_ms_p95"    : lat[min(n - 1, int(0.95 * n))],
            "latencia_ms_media"  : sum(lat) / n,
            "tokens_in_total"    : sum(e.tokens_in for e in ev),
            "tokens_out_total"   : sum(e.tokens_out for e in ev),
            "n_fallback"         : sum(1 for e in ev if e.fallback),
            "taxa_fallback"      : sum(1 for e in ev if e.fallback) / n,
        }

    def reset_eventos(self) -> None:
        self.eventos = []


# ──────────────────────────────────────────────────────────────
# Decisores
# ──────────────────────────────────────────────────────────────

def decisor_stub(acoes: tuple[int, int, int] = (1, 0, 2)):
    """Decisor offline determinístico (testes/validação sem custo de API).

    Por padrão devolve a política "sem agente" (manter/nada/liberal). Útil para
    validar que o harness LLM é plugável sem nenhuma chamada de rede.
    """
    def _decidir(est: dict) -> RespostaDecisor:
        return RespostaDecisor(acoes=acoes, tokens_in=0, tokens_out=0)
    return _decidir


def decisor_heuristico_simulado():
    """Decisor que imita o heurístico — útil para checar o caminho 'válido'
    da política (sem fallback) de forma offline e determinística."""
    h = AgentesHeuristicos()

    def _decidir(est: dict) -> RespostaDecisor:
        stress = h.stress_financeiro(est)
        acoes = (h.armazenamento(est), h.consumo(est, stress), h.gerente(est, stress))
        return RespostaDecisor(acoes=acoes)
    return _decidir


# Ferramenta exposta ao LLM (tool-use). Reusada pelo decisor direto e pelo MCP.
TOOL_DECIDIR = {
    "name": "decidir_controle",
    "description": (
        "Define as três ações de controle de energia da fazenda para a hora "
        "atual. Objetivo: minimizar o custo de energia da rede respeitando o "
        "SOC mínimo da bateria e o teto de consumo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "a_arm": {"type": "integer", "enum": list(ACOES_ARM),
                      "description": "Bateria: 0=carregar, 1=manter, 2=descarregar"},
            "a_cons": {"type": "integer", "enum": list(ACOES_CONS),
                       "description": "Cortes (soma de bits): 1=pivô, 2=bomba, 4=secador; 0=nenhum"},
            "a_ger": {"type": "integer", "enum": list(ACOES_GER),
                      "description": "Teto de consumo: 0=20kW, 1=30kW, 2=40kW"},
        },
        "required": ["a_arm", "a_cons", "a_ger"],
    },
}

SYSTEM_PROMPT = (
    "Você é o controlador de energia de uma fazenda com geração solar/eólica, "
    "bateria de 24 kWh e tarifa horária (pico 18-21h custa ~60% mais caro). "
    "A cada hora você recebe o estado e deve escolher as três ações de controle "
    "para MINIMIZAR o custo de energia importada da rede, sem deixar o SOC da "
    "bateria abaixo de 15% e sem estourar o teto de consumo. Estratégia geral: "
    "carregar a bateria com excedente solar, descarregar no pico tarifário, e "
    "cortar cargas não essenciais quando a tarifa está alta. Responda SEMPRE "
    "chamando a ferramenta decidir_controle."
)


def _estado_para_texto(est: dict) -> str:
    """Serializa o estado contínuo (rico) para o prompt do LLM."""
    return (
        f"hora={est['hora']:02d}  "
        f"SOC_bateria={est['soc']:.1f}%  "
        f"solar={est['solar_kw']:.1f}kW  eolico={est['eolico_kw']:.1f}kW  "
        f"tarifa={est['tarifa']:.3f}R$/kWh  "
        f"estresse_financeiro={est['stress']:.0f}/100  "
        f"secador_acumulado={est['sec_ac']:.1f}/20kWh  "
        f"bomba_horas={est['bomba_h']}"
    )


def criar_decisor_anthropic(
    *,
    model: str = "claude-haiku-4-5-20251001",
    temperature: float = 0.0,
    usar_cache: bool = True,
    max_tokens: int = 256,
    timeout: float = 30.0,
):
    """Decisor que chama a API Anthropic com tool-use (braço 'LLM-direto').

    Import tardio do SDK: só falha se efetivamente usado sem `anthropic`
    instalado / `ANTHROPIC_API_KEY` configurada. O system prompt é marcado para
    **prompt caching** (``usar_cache``) — alavanca de custo medida no benchmark.

    O modelo é deliberadamente o Haiku (rápido/barato) por default: 744 decisões
    por mês tornam custo e latência relevantes. Troque por outro ``claude-*``
    conforme o experimento.
    """
    import anthropic  # import tardio — não exigido para o harness offline

    client = anthropic.Anthropic(timeout=timeout)
    system = [{"type": "text", "text": SYSTEM_PROMPT}]
    if usar_cache:
        system[0]["cache_control"] = {"type": "ephemeral"}

    def _decidir(est: dict) -> RespostaDecisor:
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                tools=[TOOL_DECIDIR],
                tool_choice={"type": "tool", "name": "decidir_controle"},
                messages=[{"role": "user", "content": _estado_para_texto(est)}],
            )
        except Exception as e:
            return RespostaDecisor(acoes=None, erro=f"api:{type(e).__name__}:{e}")

        usage = getattr(msg, "usage", None)
        tin = getattr(usage, "input_tokens", 0) if usage else 0
        tout = getattr(usage, "output_tokens", 0) if usage else 0

        bloco = next((b for b in msg.content if getattr(b, "type", "") == "tool_use"), None)
        if bloco is None:
            return RespostaDecisor(acoes=None, tokens_in=tin, tokens_out=tout,
                                   erro="sem_tool_use")
        args = bloco.input or {}
        try:
            acoes = (int(args["a_arm"]), int(args["a_cons"]), int(args["a_ger"]))
        except (KeyError, TypeError, ValueError):
            return RespostaDecisor(acoes=None, tokens_in=tin, tokens_out=tout,
                                   erro=f"args_invalidos:{args!r}")
        return RespostaDecisor(acoes=acoes, tokens_in=tin, tokens_out=tout,
                               raw=str(args))

    return _decidir
