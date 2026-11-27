from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .render import render, write, output_path
from .spec import AgentSpec
from .validator import validate, errors


def _show_issues(issues) -> None:
    for i in issues:
        print(f"  [{i.level}] {i.msg}")


def cmd_new(a) -> int:
    from .llm import OpenRouterClient
    from .forge import forge
    client = OpenRouterClient(a.model, log=print, max_free=a.max_free)
    print("Modelos (en orden de preferencia):", ", ".join(client.models))
    res = forge(a.goal, client, kind=a.kind, max_rounds=a.rounds, do_tests=not a.no_tests, log=print)
    print("\n" + "=" * 60 + "\n" + render(res.spec) + "=" * 60)
    _show_issues(res.issues)
    print("Estado:", "APROBADO por validación y pruebas" if res.passed else "NO superó todas las comprobaciones")
    if not a.yes:   # compuerta humana: nada se guarda sin su visto bueno
        if input("¿Guardar este agente? [s/N] ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
            print("No se guardó nada.")
            return 1
    if errors(res.issues):
        print("Hay errores de validación: no se guarda.")
        return 2
    p = write(res.spec, a.out, force=a.force)
    (p.parent / f"{res.spec.name}.informe.json").write_text(
        json.dumps({"goal": a.goal, "passed": res.passed, "rounds": res.rounds}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Guardado:", p)
    return 0


def cmd_models(a) -> int:
    from .llm import list_models
    ids = list_models(free_only=not a.all)
    print("\n".join(ids))
    print(f"\n{len(ids)} modelo(s). Úselos así:  --model id1,id2,id3   (en orden de preferencia)")
    return 0


def cmd_render(a) -> int:
    spec = AgentSpec.from_dict(json.loads(Path(a.spec).read_text(encoding="utf-8")), kind=a.kind)
    issues = validate(spec)
    _show_issues(issues)
    if errors(issues):
        return 2
    print("Guardado:", write(spec, a.out, force=a.force))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent_forge", description="Un agente que crea agentes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="diseña, valida, prueba y guarda un agente a partir de un objetivo (requiere OPENROUTER_API_KEY)")
    p.add_argument("goal", help="qué debe hacer el agente, en lenguaje natural")
    p.add_argument("--kind", choices=["subagent", "skill"], default="subagent")
    p.add_argument("--out", default="generated")
    p.add_argument("--rounds", type=int, default=2, help="rondas máximas de corrección")
    p.add_argument("--no-tests", action="store_true", help="solo validar, sin ejecutar pruebas (gasta menos)")
    p.add_argument("--model", default=None, help="uno o varios modelos separados por coma; si uno falla pasa al siguiente. La palabra 'free' = gratuitos de OpenRouter (es el valor por defecto). Ej.: modelo/preferido,free")
    p.add_argument("--max-free", type=int, default=8, help="máximo de modelos gratuitos a usar al expandir 'free' (por defecto 8)")
    p.add_argument("--yes", action="store_true", help="guardar sin preguntar (no recomendado)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("models", help="lista los modelos gratuitos de OpenRouter (--all: todos)")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_models)
    p = sub.add_parser("render", help="valida y genera el archivo desde un spec.json, SIN IA ni API")
    p.add_argument("spec")
    p.add_argument("--kind", choices=["subagent", "skill"], default=None)
    p.add_argument("--out", default="generated")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_render)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (FileExistsError, RuntimeError, ValueError) as e:   # errores esperados: mensaje claro, sin traceback
        print("ERROR:", e)
        return 3


if __name__ == "__main__":
    sys.exit(main())
