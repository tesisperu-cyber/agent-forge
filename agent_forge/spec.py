"""Especificación de un agente: es el 'plano' que diseña el meta-agente y que luego se renderiza a archivo."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

KINDS = ("subagent", "skill")


@dataclass
class TestCase:
    input: str
    criteria: list = field(default_factory=list)   # criterios verificables que debe cumplir la respuesta


@dataclass
class AgentSpec:
    name: str
    description: str          # CUÁNDO usar este agente (1-3 frases); es lo que lee quien decide delegarle trabajo
    system_prompt: str        # cuerpo: instrucciones del agente
    kind: str = "subagent"
    tools: list = field(default_factory=list)
    model: Optional[str] = None
    tests: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any], kind: str | None = None) -> "AgentSpec":
        tests = [TestCase(input=str(t.get("input", "")), criteria=[str(c) for c in (t.get("criteria") or [])])
                 for t in (d.get("tests") or []) if isinstance(t, dict)]
        tools = d.get("tools") or []
        if isinstance(tools, str):
            tools = [x.strip() for x in tools.split(",") if x.strip()]
        return cls(
            name=str(d.get("name", "")).strip(),
            description=" ".join(str(d.get("description", "")).split()),
            system_prompt=str(d.get("system_prompt", "")).strip(),
            kind=kind or d.get("kind") or "subagent",
            tools=[str(t).strip() for t in tools],
            model=(d.get("model") or None),
            tests=tests,
        )

    def to_dict(self) -> dict:
        return asdict(self)
