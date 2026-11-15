"""Testes das rotas de autenticação (cadastro, login e sessão).

Rodar:
    pytest -q

O banco de teste é um SQLite temporário; o MariaDB do docker-compose não é usado.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Precisa vir antes de importar o app: ele cria as tabelas ao ser importado.
_ARQUIVO_DB = tempfile.NamedTemporaryFile(prefix="astrolog-teste-", suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_ARQUIVO_DB.name}"

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from models import Sessao, Usuario, db  # noqa: E402

SENHA = "ceuescuro123"


def _payload(nome="Ada Lovelace", email="ada@astrolog.app", senha=SENHA):
    return {"nome": nome, "email": email, "senha": senha}


@pytest.fixture()
def app():
    flask_app.config.update(TESTING=True)
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def cadastrar(client, **kwargs):
    return client.post("/api/auth/cadastro", json=_payload(**kwargs))


def login(client, email="ada@astrolog.app", senha=SENHA):
    return client.post("/api/auth/login", json={"email": email, "senha": senha})


# ---------------------------------------------------------------------------
# Cadastro
# ---------------------------------------------------------------------------
def test_cadastro_valido_cria_conta_sem_devolver_senha(client, app):
    resposta = cadastrar(client)
    assert resposta.status_code == 201, resposta.get_data(as_text=True)

    corpo = resposta.get_json()
    assert corpo["nome"] == "Ada Lovelace"
    assert corpo["email"] == "ada@astrolog.app"
    assert corpo["id"] == 1
    assert "senha" not in corpo
    assert "senha_hash" not in corpo

    with app.app_context():
        usuario = db.session.get(Usuario, corpo["id"])
        assert usuario is not None
        # A senha é guardada em hash, nunca em texto puro
        assert usuario.senha_hash != SENHA
        assert usuario.conferir_senha(SENHA) is True


def test_cadastro_normaliza_email_e_rejeita_duplicado(client):
    assert cadastrar(client, email="Ada@AstroLog.App").status_code == 201

    resposta = cadastrar(client, nome="Outra Pessoa", email="ada@astrolog.app")
    assert resposta.status_code == 409
    corpo = resposta.get_json()
    assert "email" in corpo["campos"]


@pytest.mark.parametrize(
    "dados, campo",
    [
        ({"nome": "", "email": "ada@astrolog.app", "senha": SENHA}, "nome"),
        ({"nome": "A", "email": "ada@astrolog.app", "senha": SENHA}, "nome"),
        ({"nome": "Ada", "email": "", "senha": SENHA}, "email"),
        ({"nome": "Ada", "email": "ada.astrolog", "senha": SENHA}, "email"),
        ({"nome": "Ada", "email": "ada@astrolog", "senha": SENHA}, "email"),
        ({"nome": "Ada", "email": "ada@astrolog.app", "senha": ""}, "senha"),
        ({"nome": "Ada", "email": "ada@astrolog.app", "senha": "12345"}, "senha"),
    ],
)
def test_cadastro_campos_invalidos(client, dados, campo):
    resposta = client.post("/api/auth/cadastro", json=dados)
    assert resposta.status_code == 400
    corpo = resposta.get_json()
    assert campo in corpo["campos"]
    assert corpo["erro"] == corpo["campos"][campo]


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_login_valido_devolve_token_e_usuario(client):
    cadastrar(client)
    resposta = login(client)
    assert resposta.status_code == 200, resposta.get_data(as_text=True)

    corpo = resposta.get_json()
    assert corpo["token"]
    assert corpo["usuario"]["email"] == "ada@astrolog.app"
    assert "senha_hash" not in corpo["usuario"]
    assert corpo["expira_em"]


def test_login_aceita_email_com_maiusculas(client):
    cadastrar(client)
    assert login(client, email="ADA@AstroLog.App").status_code == 200


@pytest.mark.parametrize(
    "email, senha",
    [
        ("ada@astrolog.app", "senha-errada"),
        ("ninguem@astrolog.app", SENHA),
    ],
)
def test_login_credenciais_invalidas(client, email, senha):
    cadastrar(client)
    resposta = login(client, email=email, senha=senha)
    assert resposta.status_code == 401
    # Mesma mensagem para não revelar quais e-mails existem
    assert resposta.get_json()["erro"] == "E-mail ou senha incorretos."


def test_login_campos_obrigatorios(client):
    resposta = client.post("/api/auth/login", json={"email": "", "senha": ""})
    assert resposta.status_code == 400
    campos = resposta.get_json()["campos"]
    assert "email" in campos and "senha" in campos


# ---------------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------------
def test_me_com_token_valido(client):
    cadastrar(client)
    token = login(client).get_json()["token"]

    resposta = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 200
    assert resposta.get_json()["nome"] == "Ada Lovelace"


def test_me_sem_token_ou_token_invalido(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nao-existe"}).status_code == 401


def test_logout_invalida_token(client):
    cadastrar(client)
    token = login(client).get_json()["token"]
    cabecalho = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/auth/logout", headers=cabecalho).status_code == 204
    assert client.get("/api/auth/me", headers=cabecalho).status_code == 401


def test_token_expirado_e_recusado_e_removido(client, app):
    cadastrar(client)
    token = login(client).get_json()["token"]

    with app.app_context():
        sessao = Sessao.query.filter_by(token=token).one()
        sessao.expira_em = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

    resposta = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 401

    with app.app_context():
        assert Sessao.query.filter_by(token=token).first() is None

# ---------------------------------------------------------------------------
# Perfil (PATCH /api/auth/me)
# ---------------------------------------------------------------------------
def test_atualizar_nome_do_usuario_autenticado(client, app):
    cadastrar(client)
    token = login(client).get_json()["token"]
    cabecalho = {"Authorization": f"Bearer {token}"}

    resposta = client.patch("/api/auth/me", json={"nome": "Grace Hopper"}, headers=cabecalho)
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    assert resposta.get_json()["nome"] == "Grace Hopper"

    with app.app_context():
        usuario = db.session.get(Usuario, 1)
        assert usuario.nome == "Grace Hopper"


@pytest.mark.parametrize("nome", ["", " ", "A", "x" * 121])
def test_atualizar_nome_invalido(client, nome):
    cadastrar(client)
    token = login(client).get_json()["token"]
    resposta = client.patch("/api/auth/me", json={"nome": nome},
                            headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 400
    assert "nome" in resposta.get_json()["campos"]


def test_atualizar_nome_sem_token(client):
    assert client.patch("/api/auth/me", json={"nome": "Grace"}).status_code == 401

# ---------------------------------------------------------------------------
# Excluir conta (DELETE /api/auth/me)
# ---------------------------------------------------------------------------
def test_excluir_conta_remove_usuario_e_sessoes(client, app):
    cadastrar(client)
    token = login(client).get_json()["token"]
    cabecalho = {"Authorization": f"Bearer {token}"}

    resposta = client.delete("/api/auth/me", headers=cabecalho)
    assert resposta.status_code == 204

    with app.app_context():
        assert db.session.get(Usuario, 1) is None
        assert Sessao.query.count() == 0

    # A sessão deixa de valer e o login não encontra mais a conta
    assert client.get("/api/auth/me", headers=cabecalho).status_code == 401
    assert login(client).status_code == 401


def test_excluir_conta_sem_token(client):
    assert client.delete("/api/auth/me").status_code == 401
