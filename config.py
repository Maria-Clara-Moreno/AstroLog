"""Configuração da aplicação: separa credenciais do código (slide 7)."""
import os


class Config:
    # DATABASE_URL tem prioridade; caso ausente, usa MariaDB do docker-compose
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:root@localhost:3306/astrolog",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False  # preserva acentos no JSON
    NASA_API_URL = "https://api.nasa.gov/planetary/apod"
    NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
    HTTP_TIMEOUT = 10  # segundos