"""Testes automatizados da AstroLog API.

Usa SQLite em memória apenas como banco de teste — a aplicação em
produção roda em MariaDB via docker-compose.
"""
import os
import sys

import pytest

# Garante que o diretório raiz (onde estão app.py e models.py) esteja no path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configura banco de teste ANTES de importar app/models
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app as modulo_app  # noqa: E402
from models import db  # noqa: E402


@pytest.fixture
def client():
    modulo_app.app.config["TESTING"] = True
    with modulo_app.app.app_context():
        db.drop_all()
        db.create_all()
        yield modulo_app.app.test_client()
        db.session.remove()
        db.drop_all()


def test_health_check(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["status"] == "ok"
    assert corpo["servico"] == "astrolog"


def test_criar_observacao(client):
    payload = {
        "astro_observado": "Júpiter",
        "tipo_astro": "planeta",
        "equipamento": "Telescópio Refletor 114mm",
        "data_hora": "2025-03-10T22:30:00",
        "local": "Serra da Canastra",
        "poluicao_luminosa": "baixa",
        "visibilidade": "excelente",
        "anotacoes": "Quatro luas galileanas visíveis.",
    }
    r = client.post("/api/observacoes", json=payload)
    assert r.status_code == 201
    dados = r.get_json()
    assert dados["id"] == 1
    assert dados["astro_observado"] == "Júpiter"


def test_listar_observacoes(client):
    client.post("/api/observacoes", json={
        "astro_observado": "Lua",
        "tipo_astro": "lua",
    })
    r = client.get("/api/observacoes")
    assert r.status_code == 200
    lista = r.get_json()
    assert isinstance(lista, list)
    assert len(lista) == 1
    assert lista[0]["astro_observado"] == "Lua"


def test_criar_observacao_sem_astro(client):
    r = client.post("/api/observacoes", json={"tipo_astro": "planeta"})
    assert r.status_code == 400


def test_obter_observacao_inexistente(client):
    assert client.get("/api/observacoes/999").status_code == 404


def test_atualizar_observacao(client):
    criada = client.post("/api/observacoes", json={
        "astro_observado": "Saturno",
        "tipo_astro": "planeta",
    }).get_json()
    r = client.patch(f"/api/observacoes/{criada['id']}",
                     json={"visibilidade": "ruim"})
    assert r.status_code == 200
    assert r.get_json()["visibilidade"] == "ruim"


def test_remover_observacao(client):
    criada = client.post("/api/observacoes", json={
        "astro_observado": "Marte",
        "tipo_astro": "planeta",
    }).get_json()
    assert client.delete(f"/api/observacoes/{criada['id']}").status_code == 204
    assert client.get(f"/api/observacoes/{criada['id']}").status_code == 404