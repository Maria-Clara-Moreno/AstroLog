"""AstroLog — API de Tarefas e Agenda Astronômica.

Rodar:
    docker compose up -d          # sobe o MariaDB
    flask --app app init-db       # cria as tabelas
    flask --app app run           # inicia a API em http://127.0.0.1:5000

Testar:
    curl http://localhost:5000/api/health
    curl http://localhost:5000/swagger
"""
from datetime import datetime

import requests
from flask import Flask, jsonify, request, send_from_directory

from config import Config
from models import LocalObservacao, Observacao, db

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)


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