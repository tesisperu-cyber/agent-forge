"""Capa mínima de LLM. El resto del proyecto solo conoce complete(system, user) -> str,
así que se puede cambiar de proveedor o usar un cliente simulado en las pruebas."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from typing import Callable, Optional, Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str, max_tokens: int = 2500) -> str: ...


class AuthError(RuntimeError):
    """Clave inválida (HTTP 401): con otro modelo fallaría igual, así que NO se pasa al siguiente."""


def parse_models(value: str | list | None) -> list:
    """'a, b,c' -> ['a','b','c'] (sin vacíos ni repetidos, conservando el orden)."""
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    out: list = []
    for m in items:
        m = str(m).strip()
        if m and m not in out:
            out.append(m)
    return out


FREE = "free"   # palabra especial: se expande a los modelos gratuitos que OpenRouter lista en ese momento


def resolve_models(models: list, max_free: int = 8, log: Optional[Callable[[str], None]] = None) -> list:
    """Sustituye la palabra 'free' por los modelos gratuitos actuales de OpenRouter (hasta max_free, sin repetir
    los que usted ya escribió). 'recursie/flint,free' = primero ese modelo y luego los gratuitos."""
    if FREE not in models:
        return models
    explicit = [m for m in models if m != FREE]
    try:
        free = [m for m in list_models(free_only=True) if m not in explicit][:max_free]
    except RuntimeError as e:
        if not explicit:
            raise RuntimeError(f"{e}. Indique los modelos a mano: --model proveedor/modelo,otro/modelo") from e
        if log:
            log(f"  ⚠ no se pudo obtener la lista de gratuitos ({e}); se usan solo los modelos indicados")
        free = []
    out: list = []
    for m in models:
        for x in (free if m == FREE else [m]):
            if x not in out:
                out.append(x)
    if not out:
        raise RuntimeError("OpenRouter no devolvió modelos gratuitos; indíquelos a mano con --model")
    return out


class OpenRouterClient:
    """Cliente de OpenRouter (API compatible con OpenAI), solo con la biblioteca estándar: sin SDK.

    Clave: variable OPENROUTER_API_KEY.
    Modelos: --model o AGENT_FORGE_MODEL; uno o VARIOS separados por coma, en orden de preferencia
    ('proveedor/modelo', lista en https://openrouter.ai/models). La palabra especial 'free' se expande a los modelos
    gratuitos que OpenRouter lista en ese momento (también es lo que se usa si no indica ninguno). Si un modelo falla (límite de uso, no disponible,
    error del servidor, tiempo agotado, respuesta vacía) se pasa automáticamente al siguiente. El modelo que
    funcionó se mantiene para las llamadas siguientes. Ningún nombre de modelo va escrito en el código: los nombres cambian."""

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str | list | None = None, api_key: str | None = None, timeout: int = 120,
                 log: Optional[Callable[[str], None]] = None, max_free: int = 8):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta OPENROUTER_API_KEY (cree una clave en https://openrouter.ai/keys)")
        wanted = parse_models(model) or parse_models(os.getenv("AGENT_FORGE_MODEL")) or [FREE]   # por defecto: gratuitos
        self.models = resolve_models(wanted, max_free, log)
        self.timeout, self.log, self._i = timeout, log, 0

    @property
    def model(self) -> str:
        return self.models[self._i]

    @property
    def n_models(self) -> int:
        return len(self.models)

    def advance(self) -> bool:
        """Pasa al siguiente modelo (p. ej. cuando el actual devuelve algo inservible). False si solo hay uno."""
        if len(self.models) < 2:
            return False
        old = self.model
        self._i = (self._i + 1) % len(self.models)
        if self.log:
            self.log(f"  ⚠ respuesta inservible de {old}; cambiando a {self.model}")
        return True

    def _call(self, model: str, system: str, user: str, max_tokens: int) -> str:
        body = json.dumps({"model": model, "max_tokens": max_tokens,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode("utf-8")
        req = urllib.request.Request(self.URL, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.api_key}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            cls = AuthError if e.code == 401 else RuntimeError
            raise cls(f"OpenRouter respondió HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise RuntimeError(f"No se pudo conectar con OpenRouter: {e}") from e
        except ValueError as e:
            raise RuntimeError("OpenRouter devolvió una respuesta que no es JSON") from e
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"OpenRouter devolvió un error: {str(data['error'])[:300]}")
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError("Respuesta de OpenRouter sin choices[0].message.content") from e
        if not (text or "").strip():
            raise RuntimeError("respuesta vacía")
        return text

    def complete(self, system: str, user: str, max_tokens: int = 2500) -> str:
        n, failures = len(self.models), []
        for k in range(n):
            idx = (self._i + k) % n
            model = self.models[idx]
            try:
                text = self._call(model, system, user, max_tokens)
            except AuthError:
                raise
            except RuntimeError as e:
                failures.append(f"{model}: {e}")
                if self.log and k < n - 1:
                    self.log(f"  ⚠ {model} falló ({str(e)[:100]}); probando {self.models[(idx + 1) % n]}")
                continue
            self._i = idx          # el modelo que funcionó se queda como actual
            return text
        raise RuntimeError("Todos los modelos fallaron:\n  " + "\n  ".join(failures))


def _is_free(m: dict) -> bool:
    if str(m.get("id", "")).endswith(":free"):
        return True
    pr = m.get("pricing") or {}
    try:
        return float(pr.get("prompt", 1)) == 0 and float(pr.get("completion", 1)) == 0
    except (TypeError, ValueError):
        return False


def list_models(free_only: bool = True, timeout: int = 30) -> list:
    """Lista los ids de modelos de OpenRouter (por defecto solo los gratuitos). No requiere clave."""
    try:
        with urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/models"), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise RuntimeError(f"No se pudo obtener la lista de modelos: {e}") from e
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("La lista de modelos no tiene el formato esperado (data: [...])")
    return sorted(str(m["id"]) for m in items if isinstance(m, dict) and m.get("id") and (not free_only or _is_free(m)))


def extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON de la respuesta (tolera ```json ... ``` y texto alrededor)."""
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                if isinstance(obj, dict):
                    return obj
            except ValueError:
                continue
    raise ValueError("La respuesta no contiene un objeto JSON válido")
