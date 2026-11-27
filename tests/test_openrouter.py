import io
import json
import urllib.error
import pytest
from agent_forge.llm import OpenRouterClient


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_requiere_clave(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(model="x/y")


def test_lee_clave_y_modelo_del_entorno(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k123")
    monkeypatch.setenv("AGENT_FORGE_MODEL", "prov/modelo")
    c = OpenRouterClient()
    assert (c.api_key, c.model) == ("k123", "prov/modelo")


def test_peticion_y_respuesta(monkeypatch):
    seen = {}
    def fake_urlopen(req, timeout=None):
        seen["url"], seen["auth"], seen["body"] = req.full_url, req.get_header("Authorization"), json.loads(req.data)
        return FakeResp({"choices": [{"message": {"content": "hola"}}]})
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = OpenRouterClient(model="prov/modelo", api_key="k123").complete("SYS", "USR", max_tokens=50)
    assert out == "hola"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer k123"
    assert seen["body"] == {"model": "prov/modelo", "max_tokens": 50,
                            "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USR"}]}


def test_errores_http_y_respuesta_rara(monkeypatch):
    c = OpenRouterClient(model="p/m", api_key="k123")
    def http401(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))
    monkeypatch.setattr("urllib.request.urlopen", http401)
    with pytest.raises(RuntimeError, match="HTTP 401") as ei:
        c.complete("s", "u")
    assert "k123" not in str(ei.value)                      # la clave nunca aparece en los errores
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResp({"error": {"message": "sin saldo"}}))
    with pytest.raises(RuntimeError, match="sin saldo"):
        c.complete("s", "u")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResp({"choices": []}))
    with pytest.raises(RuntimeError, match="choices"):
        c.complete("s", "u")
