# config.py
import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        # Mude a porta aqui para 3307
        "mysql+pymysql://root:root@127.0.0.1:3307/astrolog",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False
    NASA_API_URL = "https://api.nasa.gov/planetary/apod"
    NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
    HTTP_TIMEOUT = 10