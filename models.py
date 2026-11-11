"""Modelos SQLAlchemy — camada de persistência (ORM).

Entidades do domínio (slide 'Modelando o domínio'):
    Observacao       → registro de uma sessão de observação
    LocalObservacao  → local cadastrado com nível de poluição luminosa
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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