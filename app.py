"""AstroLog — API de Tarefas e Agenda Astronômica.

Rodar:
    docker compose up -d          # sobe o MariaDB
    flask --app app init-db       # cria as tabelas
    flask --app app run           # inicia a API em http://127.0.0.1:5000

Testar:
    curl http://localhost:5000/api/health
    curl http://localhost:5000/swagger
"""
from datetime import datetime, timedelta
import re
import secrets

import requests
from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy.exc import IntegrityError

from config import Config
from models import DURACAO_SESSAO, LocalObservacao, Observacao, Sessao, Usuario, db

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Validação de e-mail: algo@dominio.tld (sem espaços, com ponto no domínio)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
SENHA_MIN = 6
SENHA_MAX = 128
NOME_MIN = 2
NOME_MAX = 120


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_datetime(valor):
    """Converte string ISO-8601 em datetime. Retorna None em caso de erro."""
    if valor in (None, ""):
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _buscar_observacao(obs_id):
    return db.session.get(Observacao, obs_id)


def _buscar_local(local_id):
    return db.session.get(LocalObservacao, local_id)


def _buscar_usuario(usuario_id):
    return db.session.get(Usuario, usuario_id)


def _validar_cadastro(dados):
    """Valida os campos do cadastro.

    Devolve (nome, email, senha, erros). `erros` é um dict campo → mensagem,
    pronto para ser exibido embaixo de cada campo no formulário.
    """
    nome = str(dados.get("nome", "") or "").strip()
    email = str(dados.get("email", "") or "").strip().lower()
    senha = dados.get("senha", "")
    senha = senha if isinstance(senha, str) else ""

    erros = {}
    if not nome:
        erros["nome"] = "Informe o seu nome."
    elif len(nome) < NOME_MIN:
        erros["nome"] = f"O nome deve ter pelo menos {NOME_MIN} caracteres."
    elif len(nome) > NOME_MAX:
        erros["nome"] = f"O nome deve ter no máximo {NOME_MAX} caracteres."

    if not email:
        erros["email"] = "Informe o seu e-mail."
    elif len(email) > 180 or not EMAIL_RE.match(email):
        erros["email"] = "Informe um e-mail válido (ex.: voce@email.com)."

    if not senha:
        erros["senha"] = "Informe uma senha."
    elif len(senha) < SENHA_MIN:
        erros["senha"] = f"A senha deve ter pelo menos {SENHA_MIN} caracteres."
    elif len(senha) > SENHA_MAX:
        erros["senha"] = f"A senha deve ter no máximo {SENHA_MAX} caracteres."

    return nome, email, senha, erros


def _erro_campos(erros):
    """Resposta 400 padronizada, com o detalhe de cada campo inválido."""
    primeira = next(iter(erros.values()))
    return jsonify({"erro": primeira, "campos": erros}), 400


def _token_da_requisicao():
    """Lê o token de Authorization: Bearer <token> (ou X-Auth-Token)."""
    cabecalho = request.headers.get("Authorization", "").strip()
    if cabecalho.lower().startswith("bearer "):
        return cabecalho[7:].strip()
    return (request.headers.get("X-Auth-Token") or "").strip()


def _sessao_atual():
    """Retorna a Sessao válida do token enviado, ou None."""
    token = _token_da_requisicao()
    if not token:
        return None
    sessao = Sessao.query.filter_by(token=token).first()
    if sessao is None:
        return None
    if not sessao.ativa:
        db.session.delete(sessao)
        db.session.commit()
        return None
    return sessao


# ---------------------------------------------------------------------------
# CLI: flask --app app init-db
# ---------------------------------------------------------------------------
@app.cli.command("init-db")
def init_db():
    """Cria as tabelas a partir das classes do ORM (slide 7)."""
    db.create_all()
    print("Banco de dados inicializado.")


# ---------------------------------------------------------------------------
# Health check (slide 'Testando a API')
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "servico": "astrolog"})

@app.get("/")
def inicio():
    return jsonify({
        "mensagem": "AstroLog API no ar!",
        "docs": "/swagger",
        "endpoints": [
            "/api/health",
            "/api/observacoes",
            "/api/locais",
            "/api/dashboard/hoje",
            "/api/auth/cadastro",
            "/api/auth/login",
            "/api/auth/me",
            "/api/auth/logout",
        ],
    }), 200

# ---------------------------------------------------------------------------
# Swagger UI (servindo o contrato openapi.yaml local)
# ---------------------------------------------------------------------------
@app.get("/swagger")
def swagger_ui():
    """Página HTML mínima que carrega o Swagger UI via CDN."""
    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AstroLog API — Swagger UI</title>
  <link rel="stylesheet"
        href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "/openapi.yaml",
        dom_id: "#swagger-ui",
      });
    };
  </script>
</body>
</html>"""
    return html


@app.get("/openapi.yaml")
def openapi_spec():
    return send_from_directory(app.root_path, "openapi.yaml",
                               mimetype="application/yaml")


# ===========================================================================
# ROTAS: Autenticação (cadastro, login, sessão)
# ===========================================================================
@app.post("/api/auth/cadastro")
def cadastrar_usuario():
    """Cria uma conta. 201 em sucesso; 400 campos inválidos; 409 e-mail já usado."""
    dados = request.get_json(silent=True) or {}
    nome, email, senha, erros = _validar_cadastro(dados)
    if erros:
        return _erro_campos(erros)

    if Usuario.query.filter(db.func.lower(Usuario.email) == email).first() is not None:
        return jsonify({
            "erro": "Já existe uma conta com este e-mail.",
            "campos": {"email": "Já existe uma conta com este e-mail."},
        }), 409

    usuario = Usuario(nome=nome, email=email)
    usuario.definir_senha(senha)
    db.session.add(usuario)
    try:
        db.session.commit()
    except IntegrityError:
        # Corrida entre dois cadastros simultâneos com o mesmo e-mail
        db.session.rollback()
        return jsonify({
            "erro": "Já existe uma conta com este e-mail.",
            "campos": {"email": "Já existe uma conta com este e-mail."},
        }), 409

    # O cadastro NÃO autentica automaticamente: o frontend leva para o login.
    return jsonify(usuario.to_dict()), 201


@app.post("/api/auth/login")
def login():
    """Valida e-mail + senha e devolve um token de sessão (Bearer)."""
    dados = request.get_json(silent=True) or {}
    email = str(dados.get("email", "") or "").strip().lower()
    senha = dados.get("senha", "")
    senha = senha if isinstance(senha, str) else ""

    erros = {}
    if not email:
        erros["email"] = "Informe o seu e-mail."
    elif not EMAIL_RE.match(email):
        erros["email"] = "Informe um e-mail válido."
    if not senha:
        erros["senha"] = "Informe a sua senha."
    if erros:
        return _erro_campos(erros)

    usuario = Usuario.query.filter(db.func.lower(Usuario.email) == email).first()
    # Mesma mensagem para e-mail inexistente e senha errada (não revela quem tem conta).
    if usuario is None or not usuario.conferir_senha(senha):
        return jsonify({"erro": "E-mail ou senha incorretos."}), 401

    agora = datetime.utcnow()
    # Limpa sessões expiradas deste usuário antes de criar outra
    Sessao.query.filter(
        Sessao.usuario_id == usuario.id, Sessao.expira_em <= agora
    ).delete(synchronize_session=False)

    sessao = Sessao(
        token=secrets.token_urlsafe(32),
        usuario_id=usuario.id,
        criada_em=agora,
        expira_em=agora + DURACAO_SESSAO,
    )
    db.session.add(sessao)
    db.session.commit()

    return jsonify({
        "token": sessao.token,
        "expira_em": sessao.expira_em.isoformat(),
        "usuario": usuario.to_dict(),
    }), 200


@app.get("/api/auth/me")
def usuario_atual():
    """Dados do usuário dono do token enviado (usado para restaurar a sessão)."""
    sessao = _sessao_atual()
    if sessao is None:
        return jsonify({"erro": "Sessão inválida ou expirada. Faça login novamente."}), 401
    return jsonify(sessao.usuario.to_dict()), 200


@app.patch("/api/auth/me")
def atualizar_usuario_atual():
    """Atualiza o nome de exibição do usuário autenticado (tela de Perfil)."""
    sessao = _sessao_atual()
    if sessao is None:
        return jsonify({"erro": "Sessão inválida ou expirada. Faça login novamente."}), 401

    dados = request.get_json(silent=True) or {}
    if "nome" in dados:
        nome = str(dados.get("nome") or "").strip()
        if not nome:
            return _erro_campos({"nome": "Informe o seu nome."})
        if len(nome) < NOME_MIN:
            return _erro_campos({"nome": f"O nome deve ter pelo menos {NOME_MIN} caracteres."})
        if len(nome) > NOME_MAX:
            return _erro_campos({"nome": f"O nome deve ter no máximo {NOME_MAX} caracteres."})
        sessao.usuario.nome = nome

    db.session.commit()
    return jsonify(sessao.usuario.to_dict()), 200


@app.post("/api/auth/logout")
def logout():
    """Encerra a sessão do token enviado."""
    sessao = _sessao_atual()
    if sessao is None:
        return "", 204
    db.session.delete(sessao)
    db.session.commit()
    return "", 204


@app.delete("/api/auth/me")
def excluir_usuario_atual():
    """Exclui a conta do usuário autenticado (e todas as suas sessões)."""
    sessao = _sessao_atual()
    if sessao is None:
        return jsonify({"erro": "Sessão inválida ou expirada. Faça login novamente."}), 401

    usuario = sessao.usuario
    # Sessao tem cascade delete-orphan em Usuario.sessoes
    db.session.delete(usuario)
    db.session.commit()
    return "", 204


# ===========================================================================
# ROTAS: Observacao
# ===========================================================================
@app.get("/api/observacoes")
def listar_observacoes():
    """Lista observações; aceita filtro ?tipo_astro=planeta."""
    query = Observacao.query
    tipo = request.args.get("tipo_astro")
    if tipo:
        query = query.filter(Observacao.tipo_astro == tipo)
    return jsonify([o.to_dict() for o in query.all()]), 200


@app.post("/api/observacoes")
def criar_observacao():
    """Cria uma nova observação. 201 em sucesso, 400 se inválido."""
    dados = request.get_json(silent=True) or {}

    astro = str(dados.get("astro_observado", "")).strip()
    tipo = str(dados.get("tipo_astro", "")).strip()
    if not astro:
        return jsonify({"erro": "O campo 'astro_observado' é obrigatório"}), 400
    if tipo not in {"planeta", "estrela", "nebula", "galaxia", "lua", "outro"}:
        return jsonify({"erro": "tipo_astro inválido"}), 400

    data_hora = _parse_datetime(dados.get("data_hora")) or datetime.utcnow()

    obs = Observacao(
        astro_observado=astro,
        tipo_astro=tipo,
        equipamento=dados.get("equipamento"),
        data_hora=data_hora,
        local=dados.get("local"),
        poluicao_luminosa=dados.get("poluicao_luminosa"),
        visibilidade=dados.get("visibilidade"),
        anotacoes=dados.get("anotacoes"),
    )
    db.session.add(obs)
    db.session.commit()
    return jsonify(obs.to_dict()), 201


@app.get("/api/observacoes/<int:obs_id>")
def obter_observacao(obs_id):
    obs = _buscar_observacao(obs_id)
    if obs is None:
        return jsonify({"erro": "Observação não encontrada"}), 404
    return jsonify(obs.to_dict()), 200


@app.patch("/api/observacoes/<int:obs_id>")
def atualizar_observacao(obs_id):
    """Atualização parcial (PATCH)."""
    obs = _buscar_observacao(obs_id)
    if obs is None:
        return jsonify({"erro": "Observação não encontrada"}), 404

    dados = request.get_json(silent=True) or {}

    if "astro_observado" in dados:
        obs.astro_observado = dados["astro_observado"]
    if "tipo_astro" in dados:
        obs.tipo_astro = dados["tipo_astro"]
    if "equipamento" in dados:
        obs.equipamento = dados["equipamento"]
    if "local" in dados:
        obs.local = dados["local"]
    if "poluicao_luminosa" in dados:
        obs.poluicao_luminosa = dados["poluicao_luminosa"]
    if "visibilidade" in dados:
        obs.visibilidade = dados["visibilidade"]
    if "anotacoes" in dados:
        obs.anotacoes = dados["anotacoes"]
    if "data_hora" in dados:
        nova = _parse_datetime(dados["data_hora"])
        if nova is not None:
            obs.data_hora = nova

    db.session.commit()
    return jsonify(obs.to_dict()), 200


@app.delete("/api/observacoes/<int:obs_id>")
def remover_observacao(obs_id):
    obs = _buscar_observacao(obs_id)
    if obs is None:
        return jsonify({"erro": "Observação não encontrada"}), 404
    db.session.delete(obs)
    db.session.commit()
    return "", 204


# ===========================================================================
# ROTAS: LocalObservacao
# ===========================================================================
@app.get("/api/locais")
def listar_locais():
    return jsonify([l.to_dict() for l in LocalObservacao.query.all()]), 200


@app.post("/api/locais")
def criar_local():
    dados = request.get_json(silent=True) or {}
    nome = str(dados.get("nome", "")).strip()
    if not nome:
        return jsonify({"erro": "O campo 'nome' é obrigatório"}), 400

    local = LocalObservacao(
        nome=nome,
        latitude=dados.get("latitude"),
        longitude=dados.get("longitude"),
        nivel_poluicao=dados.get("nivel_poluicao"),
        descricao=dados.get("descricao"),
    )
    db.session.add(local)
    db.session.commit()
    return jsonify(local.to_dict()), 201


@app.get("/api/locais/<int:local_id>")
def obter_local(local_id):
    local = _buscar_local(local_id)
    if local is None:
        return jsonify({"erro": "Local não encontrado"}), 404
    return jsonify(local.to_dict()), 200


@app.delete("/api/locais/<int:local_id>")
def remover_local(local_id):
    local = _buscar_local(local_id)
    if local is None:
        return jsonify({"erro": "Local não encontrado"}), 404
    db.session.delete(local)
    db.session.commit()
    return "", 204


# ===========================================================================
# ROTA: Dashboard (consumo de API externa — NASA APOD)
# ===========================================================================
@app.get("/api/dashboard/hoje")
def dashboard_hoje():
    """Consome a API pública da NASA (APOD) e devolve dados formatados."""
    try:
        resposta = requests.get(
            app.config["NASA_API_URL"],
            params={"api_key": app.config["NASA_API_KEY"]},
            timeout=app.config["HTTP_TIMEOUT"],
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.RequestException, ValueError) as erro:
        return jsonify({"erro": f"Falha ao consultar NASA APOD: {erro}"}), 502

    return jsonify({
        "titulo": dados.get("title"),
        "data": dados.get("date"),
        "descricao": dados.get("explanation"),
        "url_imagem": dados.get("url"),
        "hdurl": dados.get("hdurl"),
        "media_type": dados.get("media_type", "image"),
        "copyright": dados.get("copyright"),
    }), 200


# ---------------------------------------------------------------------------
# Criação automática das tabelas ao importar (útil em testes e demo local)
# ---------------------------------------------------------------------------
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)