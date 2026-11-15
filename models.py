"""Modelos SQLAlchemy — camada de persistência (ORM).

Entidades do domínio (slide 'Modelando o domínio'):
    Observacao       → registro de uma sessão de observação
    LocalObservacao  → local cadastrado com nível de poluição luminosa
    Usuario          → conta de acesso ao app (senha sempre em hash)
    Sessao           → token de login ativo (autenticação por Bearer token)
"""
from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# Duração padrão de uma sessão de login
DURACAO_SESSAO = timedelta(days=7)


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nome = db.Column(db.String(120), nullable=False)
    # Guardamos o e-mail em minúsculas para que o login não diferencie maiúsculas.
    email = db.Column(db.String(180), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    sessoes = db.relationship(
        "Sessao", back_populates="usuario", cascade="all, delete-orphan"
    )

    def definir_senha(self, senha):
        """Nunca guardamos a senha em texto puro, só o hash (PBKDF2/scrypt)."""
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha):
        if not self.senha_hash:
            return False
        return check_password_hash(self.senha_hash, senha)

    def to_dict(self):
        # A senha (nem o hash) nunca sai na resposta da API.
        return {
            "id": self.id,
            "nome": self.nome,
            "email": self.email,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }


class Sessao(db.Model):
    __tablename__ = "sessoes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    token = db.Column(db.String(128), nullable=False, unique=True, index=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    criada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expira_em = db.Column(db.DateTime, nullable=False)

    usuario = db.relationship("Usuario", back_populates="sessoes")

    @property
    def ativa(self):
        return self.expira_em > datetime.utcnow()

    def to_dict(self):
        return {
            "token": self.token,
            "criada_em": self.criada_em.isoformat() if self.criada_em else None,
            "expira_em": self.expira_em.isoformat() if self.expira_em else None,
        }


class LocalObservacao(db.Model):
    __tablename__ = "locais_observacao"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nome = db.Column(db.String(120), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    nivel_poluicao = db.Column(
        db.Enum("baixa", "media", "alta", name="nivel_poluicao_enum"),
        nullable=True,
    )
    descricao = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "nivel_poluicao": self.nivel_poluicao,
            "descricao": self.descricao,
        }


class Observacao(db.Model):
    __tablename__ = "observacoes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    astro_observado = db.Column(db.String(120), nullable=False)
    tipo_astro = db.Column(
        db.Enum(
            "planeta", "estrela", "nebula", "galaxia", "lua", "outro",
            name="tipo_astro_enum",
        ),
        nullable=False,
    )
    equipamento = db.Column(db.String(120), nullable=True)
    data_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    local = db.Column(db.String(120), nullable=True)
    poluicao_luminosa = db.Column(
        db.Enum("baixa", "media", "alta", name="poluicao_enum"),
        nullable=True,
    )
    visibilidade = db.Column(
        db.Enum(
            "excelente", "boa", "regular", "ruim",
            name="visibilidade_enum",
        ),
        nullable=True,
    )
    anotacoes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "astro_observado": self.astro_observado,
            "tipo_astro": self.tipo_astro,
            "equipamento": self.equipamento,
            "data_hora": self.data_hora.isoformat() if self.data_hora else None,
            "local": self.local,
            "poluicao_luminosa": self.poluicao_luminosa,
            "visibilidade": self.visibilidade,
            "anotacoes": self.anotacoes,
        }