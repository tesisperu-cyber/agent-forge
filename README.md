# agent-forge — un agente que crea agentes

Casi todos los tutoriales enseñan a **una persona** a escribir un agente a mano. Este proyecto prueba otra idea:
darle a un agente el **método** para diseñar, comprobar y corregir otros agentes, con una persona que da el visto bueno final.

> Un agente que solo "escribe un prompt" no es un creador de agentes: es un generador de texto.
> Lo que lo hace fiable es el **ciclo con comprobaciones**.

## Cómo funciona

```
 objetivo en lenguaje natural
          │
          ▼
   1. DISEÑAR   → el LLM propone nombre, descripción, prompt, herramientas y 3 casos de prueba
          │
          ▼
   2. VALIDAR   → reglas deterministas (sin IA): nombre válido, herramientas permitidas, sin secretos, longitudes
          │
          ▼
   3. PROBAR    → ejecuta el agente nuevo con cada caso y otro LLM lo juzga contra los criterios
          │
          ├── fallos ──► 4. CORREGIR (reescribe el prompt con los problemas) ──► vuelve a 2 (máx. N rondas)
          ▼
   5. APROBACIÓN HUMANA → usted lee el archivo final y decide si se guarda
          │
          ▼
   agents/<nombre>.md   (subagente de Claude Code)   o   skills/<nombre>/SKILL.md
```

Decisiones de diseño:
- **Mínimo privilegio:** el meta-agente pide solo las herramientas imprescindibles; las que modifican el sistema (`Bash`, `Write`, `Edit`…) generan advertencia.
- **Validación fuera del LLM:** lo que el modelo invente no llega a disco si rompe las reglas de `validator.py`.
- **Nada se guarda sin su visto bueno** (salvo `--yes`). Tampoco se sobrescribe un archivo existente sin `--force`.
- **Cada ejecución deja un informe** (`<nombre>.informe.json`) con las rondas, errores y pruebas falladas.

## Interfaz web (Streamlit)
```bash
pip install -r requirements.txt
streamlit run app.py
```
Panel lateral: campo **API key de OpenRouter** (no se guarda) y lista desplegable con **todos los modelos gratuitos**
del momento (se consulta a OpenRouter; botón para actualizar). Los que elija se usan en cadena: si uno falla, pasa al siguiente.
Para publicarlo en Streamlit Cloud: repositorio en GitHub, *Main file path* = `app.py`.

## Uso

```bash
pip install -r requirements.txt
python -m pytest -q                      # pruebas offline, sin API
```

**Sin API (solo validar y generar desde un spec que usted escribió):**
```bash
python -m agent_forge render examples/revisor_apa.json --out generated
```

**Con API (el meta-agente diseña el agente), usando solo una clave de [OpenRouter](https://openrouter.ai/keys):**
```bash
export OPENROUTER_API_KEY="su-clave"                # PowerShell:  $env:OPENROUTER_API_KEY="su-clave"
python -m agent_forge new "Un agente que revise la redacción de resúmenes de tesis y marque frases ambiguas"
python -m agent_forge new "Una skill para redactar planteamientos del problema" --kind skill --rounds 3
```
**No hace falta escribir ningún modelo.** Si no indica ninguno, el programa pide a OpenRouter la lista de modelos
**gratuitos** del momento y los usa en cadena (hasta 8; cambie el tope con `--max-free`). Ningún nombre de modelo está
escrito en el código, porque los nombres cambian.

**Si un modelo falla, pasa al siguiente.** Cuando el actual da error de límite o de servidor (429, 404, 500, 402…), se agota
el tiempo, responde vacío o devuelve algo que no es JSON, el programa cambia al siguiente y se queda con el que funcione.
Si la clave es inválida (401) se detiene al instante. Si fallan todos, el error lista el motivo de cada uno.

**Poner sus modelos preferidos primero.** Use la palabra `free` como comodín para "los gratuitos":
```bash
python -m agent_forge new "tu objetivo" --model proveedor/modelo-favorito,free        # su modelo primero, luego los gratuitos
python -m agent_forge new "tu objetivo" --model modelo-1,modelo-2,modelo-3             # solo esos, en ese orden
export AGENT_FORGE_MODEL="proveedor/modelo-favorito,free"                               # lo mismo, por variable de entorno
python -m agent_forge models                                                            # ver qué gratuitos hay hoy (--all: todos)
```
Los gratuitos se ordenan alfabéticamente (no hay una calidad conocida detrás del orden): ponga primero los que prefiera.
Los modelos gratuitos suelen tener límites bajos y a veces siguen mal las instrucciones; si el ciclo falla con todos,
use `--no-tests` o añada uno de pago al final de la lista.

Opciones: `--no-tests` (solo valida; gasta menos), `--out`, `--rounds`, `--force`, `--yes`.

Para usar un subagente generado en Claude Code, copie `generated/agents/<nombre>.md` a `.claude/agents/` de su proyecto.

## Estructura
```
agent_forge/
  spec.py        plano del agente (AgentSpec)
  prompts.py     prompts del meta-agente (texto editable)
  llm.py         cliente OpenRouter (sin SDK, solo biblioteca estándar) + extractor de JSON
  forge.py       el bucle diseñar → validar → probar → corregir
  validator.py   reglas deterministas
  render.py      escribe el .md / SKILL.md
  cli.py         comandos new / render
examples/        spec de ejemplo (hecho a mano) y su salida renderizada
tests/           38 pruebas con un LLM y un HTTP simulados
```

## Estado honesto
| Componente | Estado |
|---|---|
| Validador, renderizado, bucle de corrección (con LLM simulado), CLI `render` | **Probado** (38 pruebas offline) |
| Cliente OpenRouter (`new`) y cadena de modelos de respaldo | Probado solo con respuestas HTTP **simuladas** (petición, errores, cambio de modelo, clave oculta); **no probado en vivo**: verifíquelo con su clave |
| Comando `models` y la palabra `free` | Formato de la respuesta de OpenRouter tomado de su documentación pública, **sin verificar en vivo** |
| Lista `ALLOWED_TOOLS` y valores de `model` | **Verifique** con la documentación de su versión de Claude Code |
| Calidad de los agentes generados | Depende del modelo y de los criterios de prueba; **revise siempre el resultado** |

El juez de pruebas es otro LLM: puede equivocarse. Es una ayuda, no una garantía.

## Ideas para ampliar
- Que el meta-agente lea ejemplos de agentes buenos ya aprobados y los use como guía.
- Un modo "mejorar" que reciba un agente existente y sus fallos reales.
- Generar el agente como programa Python (no solo como subagente/skill).
- Acumular las pruebas falladas como conjunto de regresión.

## Licencia
MIT (puede cambiarla en `LICENSE`).
