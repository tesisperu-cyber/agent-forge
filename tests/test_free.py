import pytest
from agent_forge import llm
from agent_forge.llm import OpenRouterClient


def fake_list(monkeypatch, ids):
    monkeypatch.setattr(llm, "list_models", lambda free_only=True, timeout=30: list(ids))


def test_sin_modelo_usa_los_gratuitos(monkeypatch):
    monkeypatch.delenv("AGENT_FORGE_MODEL", raising=False)
    fake_list(monkeypatch, ["a/1:free", "b/2:free"])
    assert OpenRouterClient(api_key="k").models == ["a/1:free", "b/2:free"]


def test_modelo_preferido_primero_y_luego_gratuitos_sin_repetir(monkeypatch):
    fake_list(monkeypatch, ["a/1:free", "mi/modelo", "b/2:free"])
    c = OpenRouterClient(model="mi/modelo,free", api_key="k")
    assert c.models == ["mi/modelo", "a/1:free", "b/2:free"]


def test_max_free_limita(monkeypatch):
    fake_list(monkeypatch, [f"m/{i}:free" for i in range(20)])
    assert len(OpenRouterClient(model="free", api_key="k", max_free=3).models) == 3


def test_sin_free_no_consulta_la_lista(monkeypatch):
    def boom(**kw):
        raise AssertionError("no debía consultar la lista")
    monkeypatch.setattr(llm, "list_models", boom)
    assert OpenRouterClient(model="a/1,b/2", api_key="k").models == ["a/1", "b/2"]


def test_si_falla_la_lista_y_hay_modelos_manuales_sigue(monkeypatch):
    def fail(**kw):
        raise RuntimeError("sin conexión")
    monkeypatch.setattr(llm, "list_models", fail)
    logs = []
    c = OpenRouterClient(model="mi/modelo,free", api_key="k", log=logs.append)
    assert c.models == ["mi/modelo"] and "sin conexión" in logs[0]


def test_si_falla_la_lista_y_no_hay_manuales_da_error_claro(monkeypatch):
    monkeypatch.delenv("AGENT_FORGE_MODEL", raising=False)
    def fail(**kw):
        raise RuntimeError("sin conexión")
    monkeypatch.setattr(llm, "list_models", fail)
    with pytest.raises(RuntimeError, match="a mano"):
        OpenRouterClient(api_key="k")


def test_lista_vacia_da_error(monkeypatch):
    fake_list(monkeypatch, [])
    with pytest.raises(RuntimeError, match="no devolvió modelos gratuitos"):
        OpenRouterClient(model="free", api_key="k")
