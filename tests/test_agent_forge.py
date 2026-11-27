import json
import pytest
from agent_forge import prompts
from agent_forge.forge import forge
from agent_forge.llm import extract_json
from agent_forge.render import render, write
from agent_forge.spec import AgentSpec
from agent_forge.validator import validate, errors

LONG = "Eres un agente de prueba. " * 12  # > 150 caracteres


def good(**kw):
    d = dict(name="agente-demo", description="Úsalo cuando el usuario pida resumir textos cortos en 3 viñetas.",
             system_prompt=LONG, tools=["Read"], tests=[{"input": "resume esto", "criteria": ["3 viñetas"]}])
    d.update(kw)
    return AgentSpec.from_dict(d)


def test_valido_ok():
    assert errors(validate(good())) == []


@pytest.mark.parametrize("kw,frag", [
    (dict(name="Mal Nombre"), "name"),
    (dict(description="corta"), "description"),
    (dict(system_prompt="corto"), "system_prompt"),
    (dict(tools=["Hackear"]), "herramientas no permitidas"),
    (dict(system_prompt=LONG + " sk-abcdefghijklmnopqrstuv"), "secreto"),
])
def test_validador_rechaza(kw, frag):
    assert any(frag in e.msg for e in errors(validate(good(**kw))))


def test_herramienta_riesgosa_solo_avisa():
    iss = validate(good(tools=["Bash"]))
    assert not errors(iss) and any("modificar" in i.msg for i in iss)


def test_render_subagente_y_skill(tmp_path):
    s = good(model="sonnet")
    txt = render(s)
    assert txt.startswith("---\nname: agente-demo\n") and "tools: Read" in txt and "model: sonnet" in txt
    s.kind = "skill"
    assert "tools:" not in render(s)
    assert write(s, tmp_path).as_posix().endswith("skills/agente-demo/SKILL.md")
    with pytest.raises(FileExistsError):
        write(s, tmp_path)


def test_descripcion_con_dos_puntos_se_entrecomilla():
    assert 'description: "Úsalo: cuando' in render(good(description="Úsalo: cuando el usuario pida resúmenes cortos."))


def test_extract_json_tolera_texto_y_fences():
    assert extract_json('Claro:\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("sin json")


class Fake:
    """LLM simulado: enruta según el prompt de sistema. 'agent_outputs' = respuestas sucesivas del agente probado."""
    def __init__(self, design_spec, agent_outputs, verdicts, refined=None):
        self.design_spec, self.agent_outputs, self.verdicts, self.refined = design_spec, list(agent_outputs), list(verdicts), refined
        self.calls = []

    def complete(self, system, user, max_tokens=2500):
        if system is prompts.DESIGN_SYSTEM:
            self.calls.append("design"); return json.dumps(self.design_spec)
        if system is prompts.JUDGE_SYSTEM:
            self.calls.append("judge"); return json.dumps(self.verdicts.pop(0))
        if system is prompts.REFINE_SYSTEM:
            self.calls.append("refine"); return json.dumps(self.refined)
        self.calls.append("agent"); return self.agent_outputs.pop(0)


def spec_dict(**kw):
    return good(**kw).to_dict()


def test_bucle_pasa_a_la_primera():
    f = Fake(spec_dict(), ["- a\n- b\n- c"], [{"passed": True, "reasons": []}])
    r = forge("resumir", f, max_rounds=2)
    assert r.passed and f.calls == ["design", "agent", "judge"]


def test_bucle_corrige_tras_prueba_fallida():
    f = Fake(spec_dict(), ["malo", "- a\n- b\n- c"],
             [{"passed": False, "reasons": ["no hay 3 viñetas"]}, {"passed": True, "reasons": []}],
             refined={"description": "Úsalo cuando se pidan resúmenes en 3 viñetas.", "system_prompt": LONG + " Responde siempre con 3 viñetas."})
    r = forge("resumir", f, max_rounds=2)
    assert r.passed and "3 viñetas" in r.spec.system_prompt
    assert f.calls == ["design", "agent", "judge", "refine", "agent", "judge"]
    assert len(r.rounds) == 2 and r.rounds[0]["test_failures"]


def test_bucle_se_detiene_en_max_rondas():
    f = Fake(spec_dict(), ["x", "x"], [{"passed": False, "reasons": ["no"]}] * 2,
             refined={"description": "Úsalo cuando se pidan resúmenes en 3 viñetas.", "system_prompt": LONG})
    r = forge("resumir", f, max_rounds=1)
    assert not r.passed and f.calls.count("refine") == 1


def test_error_de_validacion_se_corrige_sin_gastar_pruebas():
    bad = spec_dict(name="MAL")
    f = Fake(bad, ["- a\n- b\n- c"], [{"passed": True, "reasons": []}],
             refined={"description": "Úsalo cuando se pidan resúmenes en 3 viñetas.", "system_prompt": LONG})
    r = forge("resumir", f, max_rounds=2)
    assert not r.passed and r.rounds[0]["errors"] and "agent" not in f.calls[:2]
