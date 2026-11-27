"""Interfaz web (Streamlit) de agent-forge: campo para la clave de OpenRouter, lista desplegable de
modelos gratuitos y el ciclo DISEÑAR -> VALIDAR -> PROBAR -> CORREGIR con aprobación humana final.
Ejecutar:  streamlit run app.py     (Streamlit Cloud: Main file path = app.py)"""
from __future__ import annotations
import json
import streamlit as st
from agent_forge.forge import forge
from agent_forge.llm import OpenRouterClient, AuthError, list_models
from agent_forge.render import render, output_path
from agent_forge.validator import errors, validate, ALLOWED_TOOLS

st.set_page_config(page_title="agent-forge", page_icon="🛠️", layout="wide")
st.title("🛠️ agent-forge — un agente que crea agentes")
st.caption("Diseña, valida, prueba y corrige un agente. Usted lo revisa y decide si lo descarga. "
           "Nada se guarda en el servidor.")


@st.cache_data(ttl=600, show_spinner="Consultando modelos gratuitos de OpenRouter…")
def free_models() -> list:
    return list_models(free_only=True)


with st.sidebar:
    st.header("OpenRouter")
    api_key = st.text_input("API key de OpenRouter", type="password", placeholder="sk-or-v1-…",
                            help="Cree una en https://openrouter.ai/keys. Solo se usa en esta sesión; no se guarda.")
    if st.button("🔄 Actualizar lista de modelos"):
        free_models.clear()
    try:
        models = free_models()
        st.success(f"{len(models)} modelos gratuitos disponibles")
    except RuntimeError as e:
        models = []
        st.error(f"No se pudo obtener la lista: {e}")
    chosen = st.multiselect(
        "Modelos gratuitos (en orden de preferencia)", models, default=models[:3],
        help="Si uno falla (límite, error, respuesta vacía) se pasa al siguiente. "
             "Si no elige ninguno se usan los gratuitos que OpenRouter liste.")
    max_free = st.slider("Máx. gratuitos si no elige ninguno", 1, 15, 8)
    st.header("Opciones")
    kind = st.radio("Tipo", ["subagent", "skill"], format_func=lambda k: "Subagente de Claude Code" if k == "subagent" else "Skill")
    rounds = st.slider("Rondas máximas de corrección", 0, 5, 2)
    do_tests = st.checkbox("Ejecutar pruebas (gasta más llamadas)", value=True)

goal = st.text_area("¿Qué debe hacer el agente?", height=120,
                    placeholder="Un agente que revise la redacción de resúmenes de tesis y marque frases ambiguas")

if st.button("Crear agente", type="primary", disabled=not goal.strip()):
    if not api_key.strip():
        st.error("Escriba su API key de OpenRouter en el panel lateral.")
    else:
        try:
            with st.status("Trabajando…", expanded=True) as status:
                def log(msg: str) -> None:
                    st.write(msg)
                client = OpenRouterClient(chosen or None, api_key=api_key.strip(), log=log, max_free=max_free)
                st.write("Modelos en uso: " + ", ".join(client.models))
                res = forge(goal.strip(), client, kind=kind, max_rounds=rounds, do_tests=do_tests, log=log)
                status.update(label="Listo", state="complete")
            st.session_state["res"], st.session_state["goal"] = res, goal.strip()
        except AuthError as e:
            st.error(f"Clave rechazada por OpenRouter: {e}")
        except (RuntimeError, ValueError) as e:
            st.error(str(e))

res = st.session_state.get("res")
if res:
    st.divider()
    if res.spec.kind == "subagent":
        invalid = [t for t in res.spec.tools if t not in ALLOWED_TOOLS]
        if invalid:
            st.info(f"El modelo pidió herramientas que no existen ({', '.join(invalid)}). "
                    "Elija abajo las herramientas correctas y el agente se vuelve a validar.")
        picked = st.multiselect("Herramientas del agente (mínimo privilegio)", sorted(ALLOWED_TOOLS),
                                default=[t for t in res.spec.tools if t in ALLOWED_TOOLS],
                                key=f"tools_{res.spec.name}_{id(res)}")
        res.spec.tools = picked
    res.issues = validate(res.spec)          # se revalida en vivo con lo que usted edite
    errs = errors(res.issues)
    if res.passed or not errs:
        st.success("APROBADO por validación y pruebas" if res.passed else "Sin errores de validación (revise las advertencias)")
    else:
        st.warning("No superó todas las comprobaciones: revíselo con cuidado antes de usarlo.")
    left, right = st.columns([3, 2])
    with left:
        text = render(res.spec)
        st.subheader(res.spec.name)
        st.code(text, language="markdown")
    with right:
        st.subheader("Validación")
        for i in res.issues:
            (st.error if i.level == "error" else st.warning)(i.msg)
        if not res.issues:
            st.info("Sin observaciones.")
        with st.expander("Rondas (auditoría)"):
            st.json(res.rounds)
    fname = output_path(res.spec, ".").as_posix().lstrip("./")
    st.markdown("**Aprobación humana:** si el agente le convence, descárguelo.")
    c1, c2 = st.columns(2)
    c1.download_button("✅ Aprobar y descargar", text, file_name=fname.split("/")[-1] if res.spec.kind == "subagent" else "SKILL.md",
                       disabled=bool(errs), help="Deshabilitado si hay errores de validación." if errs else None)
    c2.download_button("Informe (JSON)", json.dumps({"goal": st.session_state.get("goal"), "passed": res.passed,
                                                     "rounds": res.rounds}, ensure_ascii=False, indent=2),
                       file_name=f"{res.spec.name}.informe.json")
    if res.spec.kind == "skill":
        st.caption(f"Guárdelo en su proyecto como: {fname}")
    else:
        st.caption(f"Guárdelo en su proyecto como: {fname}  (carpeta .claude/agents/ de Claude Code)")
