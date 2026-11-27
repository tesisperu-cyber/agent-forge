import io
import json
import urllib.error
import pytest
from agent_forge.forge import _ask_json
from agent_forge.llm import OpenRouterClient, parse_models, list_models


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def ok(text="hola"):
    return FakeResp({"choices": [{"message": {"content": text}}]})


def http(req, code):
    return urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b'{"error":"detalle"}'))


def install(monkeypatch, behavior):
    """behavior: dict modelo -> 'ok' | 'vacio' | código HTTP (int) | 'timeout'. Devuelve la lista de modelos pedidos."""
    asked = []
    def fake(req, timeout=None):
        m = json.loads(req.data)["model"]
        asked.append(m)
        b = behavior[m]
        if b == "ok":
            return ok("hola de " + m)
        if b == "vacio":
            return ok("")
        if b == "timeout":
            raise TimeoutError("agotado")
        raise http(req, b)
    monkeypatch.setattr("urllib.request.urlopen", fake)
    return asked


def test_parse_models():
    assert parse_models(" a/b , c/d,,a/b ") == ["a/b", "c/d"]
    assert parse_models(None) == [] and parse_models(["x", "x", " y "]) == ["x", "y"]


def test_modelos_desde_entorno_con_comas(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("AGENT_FORGE_MODEL", "a/1:free, b/2:free")
    c = OpenRouterClient()
    assert c.models == ["a/1:free", "b/2:free"] and c.model == "a/1:free" and c.n_models == 2


def test_pasa_al_siguiente_si_falla_y_se_queda_con_el_que_funciona(monkeypatch):
    asked = install(monkeypatch, {"a": 429, "b": "vacio", "c": "ok"})
    logs = []
    c = OpenRouterClient(model="a,b,c", api_key="k", log=logs.append)
    assert c.complete("s", "u") == "hola de c"
    assert asked == ["a", "b", "c"] and len(logs) == 2 and "probando b" in logs[0]
    c.complete("s", "u")
    assert asked[-1] == "c"                      # 'c' quedó como modelo actual: no reintenta a y b


@pytest.mark.parametrize("fallo", [404, 500, 402, "timeout", "vacio"])
def test_distintos_fallos_activan_el_respaldo(monkeypatch, fallo):
    asked = install(monkeypatch, {"a": fallo, "b": "ok"})
    assert OpenRouterClient(model="a,b", api_key="k").complete("s", "u") == "hola de b"
    assert asked == ["a", "b"]


def test_clave_invalida_no_prueba_otros_modelos(monkeypatch):
    asked = install(monkeypatch, {"a": 401, "b": "ok"})
    with pytest.raises(RuntimeError, match="HTTP 401"):
        OpenRouterClient(model="a,b", api_key="k").complete("s", "u")
    assert asked == ["a"]


def test_todos_fallan_lista_cada_motivo(monkeypatch):
    install(monkeypatch, {"a": 429, "b": 500})
    with pytest.raises(RuntimeError) as ei:
        OpenRouterClient(model="a,b", api_key="k").complete("s", "u")
    msg = str(ei.value)
    assert "Todos los modelos fallaron" in msg and "a:" in msg and "HTTP 429" in msg and "b:" in msg and "HTTP 500" in msg


def test_advance_cicla_y_un_solo_modelo_no_avanza():
    c = OpenRouterClient(model="a,b", api_key="k")
    assert c.advance() and c.model == "b" and c.advance() and c.model == "a"
    assert OpenRouterClient(model="a", api_key="k").advance() is False


def test_json_invalido_cambia_de_modelo():
    class C:
        n_models = 2
        def __init__(self):
            self.i, self.salidas = 0, {0: "no soy json", 1: '{"ok": true}'}
            self.avances = 0
        def complete(self, s, u, max_tokens=2500):
            return self.salidas[self.i]
        def advance(self):
            self.i += 1; self.avances += 1; return True
    c = C()
    assert _ask_json(c, "s", "u") == {"ok": True} and c.avances == 1


def test_list_models_solo_gratuitos(monkeypatch):
    payload = {"data": [{"id": "a/x:free", "pricing": {"prompt": "0", "completion": "0"}},
                        {"id": "b/y", "pricing": {"prompt": "0", "completion": "0"}},
                        {"id": "c/z", "pricing": {"prompt": "0.001", "completion": "0.002"}},
                        {"id": "d/auto", "pricing": {"prompt": "-1", "completion": "-1"}}]}
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResp(payload))
    assert list_models(free_only=True) == ["a/x:free", "b/y"]
    assert len(list_models(free_only=False)) == 4
