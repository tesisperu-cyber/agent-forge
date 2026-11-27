"""Convierte un AgentSpec en el archivo final: subagente de Claude Code (.md) o skill (SKILL.md)."""
from __future__ import annotations
import json
from pathlib import Path
from .spec import AgentSpec

_YAML_SPECIAL_START = set("\"'[]{}>|*&!%@`#-?:,")


def _yaml_scalar(text: str) -> str:
    one_line = " ".join(text.split())
    if ":" in one_line or "#" in one_line or (one_line and one_line[0] in _YAML_SPECIAL_START):
        return json.dumps(one_line, ensure_ascii=False)
    return one_line


def render(spec: AgentSpec) -> str:
    lines = ["---", f"name: {spec.name}", f"description: {_yaml_scalar(spec.description)}"]
    if spec.kind == "subagent":
        if spec.tools:
            lines.append(f"tools: {', '.join(spec.tools)}")
        if spec.model:
            lines.append(f"model: {spec.model}")
    lines += ["---", "", spec.system_prompt.strip(), ""]
    return "\n".join(lines)


def output_path(spec: AgentSpec, out_dir: str | Path) -> Path:
    base = Path(out_dir)
    return base / "skills" / spec.name / "SKILL.md" if spec.kind == "skill" else base / "agents" / f"{spec.name}.md"


def write(spec: AgentSpec, out_dir: str | Path, force: bool = False) -> Path:
    p = output_path(spec, out_dir)
    if p.exists() and not force:
        raise FileExistsError(f"{p} ya existe (use --force para sobrescribir)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(spec), encoding="utf-8")
    return p
