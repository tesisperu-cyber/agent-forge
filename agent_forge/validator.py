"""Validación DETERMINISTA (sin IA) del agente generado. Es la red de seguridad: lo que el LLM invente
no pasa a disco si rompe estas reglas. Ajuste las constantes a su versión de Claude Code."""
from __future__ import annotations
import re
from dataclasses import dataclass
from .spec import AgentSpec, KINDS

# Herramientas que se aceptan en 'tools'. VERIFIQUE esta lista con la documentación de su versión de Claude Code.
ALLOWED_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "Bash", "Glob", "Grep",
                 "WebFetch", "WebSearch", "TodoWrite", "NotebookEdit"}
# Herramientas que modifican el sistema: no se prohíben, pero generan advertencia para revisión humana.
RISKY_TOOLS = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"}
KNOWN_MODELS = {"sonnet", "opus", "haiku", "inherit"}

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


@dataclass
class Issue:
    level: str   # "error" bloquea; "warning" solo avisa
    msg: str


def validate(spec: AgentSpec) -> list[Issue]:
    out: list[Issue] = []
    err = lambda m: out.append(Issue("error", m))
    warn = lambda m: out.append(Issue("warning", m))

    if spec.kind not in KINDS:
        err(f"kind inválido: {spec.kind!r} (use {', '.join(KINDS)})")
    if not NAME_RE.match(spec.name or ""):
        err("name debe ser minúsculas, números y guiones (3-40 caracteres), empezando por letra")
    if not (20 <= len(spec.description) <= 500):
        err(f"description debe tener 20-500 caracteres (tiene {len(spec.description)}); diga CUÁNDO usarlo")
    if not (150 <= len(spec.system_prompt) <= 12000):
        err(f"system_prompt debe tener 150-12000 caracteres (tiene {len(spec.system_prompt)})")
    # En una skill 'tools' no se escribe en el archivo: solo se valida en subagentes.
    bad = [t for t in spec.tools if t not in ALLOWED_TOOLS] if spec.kind == "subagent" else []
    if bad:
        err(f"herramientas no permitidas: {', '.join(bad)}")
    risky = [t for t in spec.tools if t in RISKY_TOOLS] if spec.kind == "subagent" else []
    if risky:
        warn(f"el agente puede modificar el sistema ({', '.join(risky)}): revíselo antes de usarlo")
    if spec.model and spec.model not in KNOWN_MODELS:
        warn(f"model {spec.model!r} no está en {sorted(KNOWN_MODELS)}; confirme que su versión lo acepta")
    for label, text in (("description", spec.description), ("system_prompt", spec.system_prompt)):
        if SECRET_RE.search(text):
            err(f"posible secreto/clave dentro de {label}")
    if not spec.tests:
        warn("sin casos de prueba: no se podrá verificar el agente automáticamente")
    for i, t in enumerate(spec.tests, 1):
        if not t.input.strip() or not t.criteria:
            warn(f"caso de prueba {i} incompleto (necesita input y criterios)")
    return out


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == "error"]
