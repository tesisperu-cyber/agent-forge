"""El bucle del meta-agente:  DISEÑAR -> VALIDAR -> PROBAR -> CORREGIR (máx. N rondas) -> (aprobación humana en la CLI)."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Callable
from . import prompts
from .llm import LLMClient, extract_json
from .spec import AgentSpec
from .validator import validate, errors, Issue


@dataclass
class ForgeResult:
    spec: AgentSpec
    passed: bool
    issues: list = field(default_factory=list)   # Issue de la última validación
    rounds: list = field(default_factory=list)   # historial por ronda (para auditoría)


def _ask_json(client: LLMClient, system: str, user: str, retries: int | None = None) -> dict:
    """Pide JSON. Si la respuesta no lo es, cambia al siguiente modelo (si el cliente tiene cadena de respaldo) y reintenta."""
    if retries is None:
        retries = max(1, getattr(client, "n_models", 1) - 1)
    last = None
    for _ in range(retries + 1):
        raw = client.complete(system, user)
        try:
            return extract_json(raw)
        except ValueError as e:
            last = e
            advance = getattr(client, "advance", None)
            if callable(advance):
                advance()
            user = user + "\n\nTu respuesta anterior no era JSON válido. Responde SOLO con el objeto JSON."
    raise ValueError(f"El modelo no devolvió JSON válido: {last}")


def design(client: LLMClient, goal: str, kind: str) -> AgentSpec:
    data = _ask_json(client, prompts.DESIGN_SYSTEM, f"Tipo de agente: {kind}\nObjetivo:\n{goal}")
    return AgentSpec.from_dict(data, kind=kind)


def run_tests(client: LLMClient, spec: AgentSpec) -> list[dict]:
    """Ejecuta cada caso contra el agente (su system_prompt) y lo juzga con otra llamada. Devuelve los fallos."""
    failures = []
    for t in spec.tests:
        if not t.input.strip() or not t.criteria:
            continue
        answer = client.complete(spec.system_prompt, t.input)
        verdict = _ask_json(client, prompts.JUDGE_SYSTEM,
                            f"TAREA:\n{t.input}\n\nCRITERIOS:\n- " + "\n- ".join(t.criteria) + f"\n\nRESPUESTA:\n{answer}")
        if not verdict.get("passed"):
            failures.append({"input": t.input, "reasons": verdict.get("reasons") or ["sin motivo"], "answer": answer[:600]})
    return failures


def refine(client: LLMClient, spec: AgentSpec, problems: list[str]) -> AgentSpec:
    data = _ask_json(client, prompts.REFINE_SYSTEM,
                     "DISEÑO ACTUAL:\n" + json.dumps({"description": spec.description, "system_prompt": spec.system_prompt},
                                                      ensure_ascii=False) + "\n\nPROBLEMAS:\n- " + "\n- ".join(problems))
    if data.get("description"):
        spec.description = " ".join(str(data["description"]).split())
    if data.get("system_prompt"):
        spec.system_prompt = str(data["system_prompt"]).strip()
    return spec


def forge(goal: str, client: LLMClient, kind: str = "subagent", max_rounds: int = 2,
          do_tests: bool = True, log: Callable[[str], None] = lambda s: None) -> ForgeResult:
    log("Diseñando el agente…")
    spec = design(client, goal, kind)
    rounds: list = []
    issues: list[Issue] = []
    for n in range(max_rounds + 1):
        issues = validate(spec)
        errs = errors(issues)
        failures = [] if errs or not do_tests else run_tests(client, spec)
        rounds.append({"round": n, "errors": [i.msg for i in errs],
                       "test_failures": [{"input": f["input"], "reasons": f["reasons"]} for f in failures]})
        log(f"Ronda {n}: {len(errs)} error(es) de validación, {len(failures)} prueba(s) fallida(s)")
        if not errs and not failures:
            return ForgeResult(spec, True, issues, rounds)
        if n == max_rounds:
            break
        problems = [i.msg for i in errs] + [f"Prueba fallida ({f['input'][:80]}): " + "; ".join(f["reasons"]) for f in failures]
        spec = refine(client, spec, problems)
    return ForgeResult(spec, False, issues, rounds)
