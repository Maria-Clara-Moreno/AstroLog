"""Interface Gradio consumindo a AstroLog API.

Rodar (com a API já em execução em http://127.0.0.1:5000):
    python frontend/gradio_app.py
"""
import base64
import io
import math
import random
import os
from datetime import datetime, timezone
from html import escape

import gradio as gr
import pandas as pd
import requests
from PIL import Image

API_BASE = "http://127.0.0.1:5000"
TIMEOUT = 15

TIPOS_ASTRO = ["planeta", "estrela", "nebula", "galaxia", "lua", "outro"]
POLUICAO = ["baixa", "media", "alta"]
VISIBILIDADE = ["excelente", "boa", "regular", "ruim"]

def get_base64_image():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.abspath(os.path.join(current_dir, "..", "img", "lua.png"))
    try:
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            return f"data:image/png;base64,{encoded_string}"
    except FileNotFoundError:
        print(f"Aviso: Imagem não encontrada em {img_path}")
        return ""

def get_base64_planeta(nome_arquivo):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.abspath(os.path.join(current_dir, "..", "img", nome_arquivo))
    try:
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            # Detecta se é png ou jpg
            ext = "png" if nome_arquivo.endswith(".png") else "jpeg"
            return f"data:image/{ext};base64,{encoded_string}"
    except FileNotFoundError:
        return ""

IMG_BASE64 = get_base64_image()

# ---------------------------------------------------------------------------
# CSS LIMPO E AJUSTADO PARA TELA CHEIA E POSICIONAMENTO
# ---------------------------------------------------------------------------
CSS = f"""
/* --- RESET AGRESSIVO --- */
html, body, .gradio-container {{
    margin: 0 !important;
    padding: 0 !important;
    max-width: 100% !important;
    min-height: 100vh;
    background: #0b0a17 !important;
}}

.gradio-container > .main, .gradio-container > .wrap {{
    padding: 0 !important;
    margin: 0 !important;
}}

/* Tela inicial: preenche toda a tela com flexbox para organizar verticalmente */
#tela-inicio {{ 
    background-image: url('{IMG_BASE64}'); 
    background-size: cover; 
    background-position: center; 
    background-repeat: no-repeat;
    padding: 24px 56px 40px !important; 
    height: 100vh !important;
    width: 100vw !important;
    box-sizing: border-box !important; 
    margin: 0 !important;
    position: fixed !important;
    z-index: 50;
    top: 0;
    left: 0;
    flex-direction: column !important;
    justify-content: space-between !important; /* Empurra o botão para o final */
}}

#tela-inicio > div, #tela-inicio .block, #tela-inicio .form {{
    background: transparent !important; 
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
}}

/* Grade: título no topo-esquerda, painel à direita */
.hero {{ display: grid; grid-template-columns: 1.2fr 1fr;
        grid-template-rows: auto 1fr; column-gap: 48px; min-height: 100%; }}
.topo {{ grid-column: 1; grid-row: 1; }}
.lua-area {{ grid-column: 1; grid-row: 2; }} 

/* PAINEL AJUSTADO: Mais para baixo conforme solicitado */
.painel {{ 
    grid-area: 2 / 2 / 3;
    place-self: end;
    margin-bottom: 15vh; /* Move o card para cima/baixo */
    width: 100%;
    max-width: 460px;
    padding: 32px 36px;
    border-radius: 24px;
    background: rgba(11, 10, 23, 0.4);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(139, 92, 246, 0.15);
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
}}

.marca {{ display: flex; align-items: center; gap: 8px; color: #e8e6f5;
         font-weight: 600; font-size: 1.1rem; }}
.titulo-bemvindo {{ font-size: 4.2rem; font-weight: 800; color: #8b5cf6;
                   line-height: 1.1; margin: 8px 0 6px 0; }}
.slogan {{ color: #cfcde6; font-size: .7rem; letter-spacing: .15em;
          line-height: 1.8; text-transform: uppercase; }}

/* Textos do painel */
.tag {{ color: #8b5cf6; font-size: .7rem; letter-spacing: .15em; font-weight: 600; }}
.chamada {{ color: #fff; font-size: 2.4rem; font-weight: 700; margin: 8px 0 12px;
           line-height: 1.15; }}
.sub {{ color: #a5a3c4; font-size: .95rem; margin-bottom: 22px; }}
.item {{ display: flex; gap: 14px; align-items: center; margin: 16px 0; }}
.icone {{ width: 46px; height: 46px; border-radius: 12px; display: flex;
         align-items: center; justify-content: center; font-size: 1.3rem;
         flex-shrink: 0; }}
.i1 {{ background: #2a2250; }} .i2 {{ background: #123a33; }} .i3 {{ background: #3a2f12; }}
.item b {{ color: #fff; font-size: .95rem; display: block; }}
.item span {{ color: #a5a3c4; font-size: .78rem; }}

/* BOTÃO AJUSTADO: Alinhado na parte inferior centralizada */
#btn-comecar {{ 
    background: #8b5cf6 !important; 
    color: #fff !important;
    border: none !important; 
    border-radius: 999px !important;
    font-size: 1rem !important; 
    font-weight: 600 !important;
    width: 320px !important; 
    max-width: 320px !important; 
    padding: 14px 0 !important; 
    margin: 0 auto !important; /* Centraliza horizontalmente */
}}
#btn-comecar:hover {{ background: #7c4de8 !important; }}

@media (max-width: 900px) {{
  .hero {{ grid-template-columns: 1fr; grid-template-rows: auto auto; }}
  .lua-area {{ display: none; }}
  .painel {{ grid-column: 1; grid-row: 2; justify-self: center; margin-bottom: 5vh; }}
}}
"""


CSS_DASH = """
/* a tela inicial só aparece enquanto estiver visível */
#tela-inicio:not(.hide):not(.hidden):not([hidden]) { display: flex !important; }
#tela-inicio.hide, #tela-inicio.hidden, #tela-inicio[hidden] { display: none !important; }

/* ===== App: barra superior + menu lateral ===== */
#tela-app { background: #0b0a17; min-height: 100vh; gap: 0 !important; padding: 0 !important; }

/* --- NAVBAR FIXA --- */
#topbar { 
    background: linear-gradient(90deg, #3b0764, #4c1d95); 
    padding: 14px 28px !important;
    align-items: center; 
    justify-content: flex-start !important; 
    gap: 32px !important;
    flex-wrap: nowrap !important; 
    margin: 0 !important;
    /* Fixação */
    position: fixed !important;
    top: 0;
    left: 0;
    width: 100% !important;
    z-index: 1000 !important;
    box-sizing: border-box !important;
    height: 70px; /* Altura fixa para cálculo */
}

#topbar-logo, #topbar-logo > * { background: transparent !important; border: none !important;
          padding: 0 !important; flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
.logo { color: #fff; font-size: 1.4rem; font-weight: 700; }
#busca { flex: 0 1 400px !important; width: 400px !important; max-width: 400px !important;
         min-width: 0 !important; background: transparent !important; border: none !important; }
#busca textarea, #busca input { background: rgb(0 0 0 / 30%) !important; color: #e8e6f5 !important;
          border: 1px solid rgb(0 0 0 / 12%) !important; border-radius: 999px !important;
          padding: 10px 18px !important; }

/* Container principal ajustado para não esconder atrás da navbar */
#corpo { 
    gap: 0 !important; 
    flex-wrap: nowrap !important; 
    margin-top: 70px !important; /* Compensa a navbar fixa */
    min-height: calc(100vh - 70px) !important;
    display: flex !important;
}

/* --- SIDEBAR FIXA --- */
#sidebar { 
    background: #0d0c1d; 
    border-right: 1px solid rgba(255,255,255,.05);
    padding: 18px 14px !important; 
    gap: 8px !important;
    flex: none !important; 
    width: 210px !important; 
    /* Fixação */
    position: fixed !important;
    top: 70px; /* Abaixo da navbar */
    left: 0;
    bottom: 0;
    overflow-y: auto; /* Permite scroll interno se o menu for muito longo */
    z-index: 900 !important;
    box-sizing: border-box !important;
}

.nav-btn { background: transparent !important; color: #cfcde6 !important; border: none !important;
           box-shadow: none !important; justify-content: flex-start !important; text-align: left;
           padding: 12px 16px !important; border-radius: 12px !important; font-weight: 600 !important; }
.nav-btn:hover { background: rgba(139,92,246,.15) !important; }
.nav-btn.primary { background: #8b5cf6 !important; color: #fff !important; }

/* --- CONTEÚDO AJUSTADO --- */
#conteudo { 
    padding: 22px 28px !important; 
    background: #0b0a17; 
    margin-left: 210px !important; /* Compensa a sidebar fixa */
    width: calc(100% - 210px) !important;
    min-height: calc(100vh - 70px) !important;
    box-sizing: border-box !important;
}

/* ===== Dashboard ===== */
.dash { display: grid; grid-template-columns: 1fr 1.1fr; gap: 20px; color: #e8e6f5; }
.dcol { display: flex; flex-direction: column; gap: 16px; }
.dash h1 { font-size: 2.2rem; font-weight: 800; margin: 0; color: #fff; }
.dash .data { color: #a5a3c4; margin: 4px 0 6px; }
.dash h3 { font-size: 1.05rem; margin: 6px 0 0; color: #fff; }
.dcard { background: rgba(22,24,52,.75); border: 1px solid rgba(255,255,255,.06);
         border-radius: 18px; padding: 20px; }
.lua-card { display: flex; align-items: center; gap: 22px; }
.lua-card svg { width: 96px; height: 96px; flex: none; filter: drop-shadow(0 0 14px rgba(255,240,200,.25)); }
.mini { font-size: .7rem; letter-spacing: .1em; color: #a5a3c4; text-transform: uppercase; }
.lua-nome { font-size: 1.7rem; font-weight: 700; color: #fff; }
.amarelo { color: #f2c94c; font-size: .85rem; }
.clima { display: flex; justify-content: space-around; }
.clima div { text-align: center; }
.clima b { display: block; font-size: 1.3rem; }
.clima span { font-size: .75rem; color: #a5a3c4; }
.verde { color: #34d399; } .azul { color: #38bdf8; }
.planeta { display: flex; align-items: center; gap: 14px; padding: 12px 6px;
           border-bottom: 1px solid rgba(255,255,255,.05); }
.planeta:last-child { border-bottom: none; }
.planeta .img-planeta {  border-radius: 50%;  flex: none;  object-fit: cover; box-shadow: 0 0 10px rgba(0,0,0,0.5); transition: transform 0.2s; }
.planeta:hover .img-planeta { transform: scale(1.1); /* Efeito de zoom ao passar o mouse */ }
.planeta .info { flex: 1; } .planeta b { display: block; color: #fff; }
.planeta span { font-size: .75rem; color: #a5a3c4; }
.badge { padding: 6px 16px; border-radius: 999px; font-size: .78rem; font-weight: 600; }
.b-baixa { background: #3a2f12; color: #f2c94c; } .b-media { background: #3a3417; color: #e8d26a; }
.b-alta { background: #123a33; color: #34d399; }
.ceu-head { display: flex; justify-content: space-between; align-items: flex-start; }
.ceu-head b { font-size: 1.1rem; color: #fff; }
.ceu-head .sub { display: block; font-size: .8rem; color: #a5a3c4; }
.dash-link { cursor: pointer; background: rgba(139,92,246,.18); color: #cfc2ff; padding: 8px 14px;
             border-radius: 999px; font-size: .8rem; white-space: nowrap; }
.ceu-svg { width: 100%; height: auto; }

/* CARD DA NASA (APOD) - Ajustado para garantir a imagem */
.apod { display: flex; flex-direction: row; padding: 0; overflow: hidden; min-height: 250px; }
.apod .txt { flex: 1.1; padding: 22px; display: flex; flex-direction: column; gap: 8px; }
.apod .tag2 { color: #f2c94c; font-size: .7rem; letter-spacing: .1em; font-weight: 700; }
.apod h2 { margin: 0; font-size: 1.4rem; color: #fff; display: -webkit-box; -webkit-line-clamp: 2;
           -webkit-box-orient: vertical; overflow: hidden; }
.apod p { margin: 0; color: #a5a3c4; font-size: .85rem; display: -webkit-box; -webkit-line-clamp: 4;
          -webkit-box-orient: vertical; overflow: hidden; }
.apod .img { flex: 1; min-height: 250px; background-size: cover; background-position: center; }
.btn-det { align-self: flex-start; margin-top: auto; background: #8b5cf6; color: #fff !important;
           padding: 10px 20px; border-radius: 999px; font-weight: 600; text-decoration: none; }
@media (max-width: 1000px) { .dash { grid-template-columns: 1fr; } }
"""
CSS += CSS_DASH

CSS_MAPA = """
/* ===== Tela Mapa ===== */
#side-tag { margin-top: auto !important; background: rgba(255,255,255,.04) !important;
            border-radius: 14px !important; padding: 14px !important; border: none !important; }
.side-tag { color: #a5a3c4; font-size: .8rem; line-height: 1.45; }
.side-tag .estrela { color: #f2c94c; font-size: 1rem; display: block; margin-bottom: 4px; }

.mapa { position: relative; height: calc(100vh - 114px); min-height: 480px; overflow: hidden;
        border-radius: 20px; border: 1px solid rgba(120,130,255,.15);
        background: radial-gradient(ellipse at 35% 43%, #12123a 0%, #0a0b20 55%, #07081a 100%); }
.mapa .estrelas { position: absolute; inset: 0; width: 100%; height: 100%; }
.loc-radio { position: absolute; opacity: 0; pointer-events: none; width: 0; height: 0; }

.anel-d { position: absolute; left: 35.3%; top: 43.3%; transform: translate(-50%, -50%);
          border-radius: 50%; border: 1px dashed rgba(139,92,246,.22); pointer-events: none; }
.voce { position: absolute; left: 35.3%; top: 43.3%; width: 0; height: 0; }
.voce .halo { position: absolute; left: 0; top: 0; width: 230px; height: 230px; border-radius: 50%;
              transform: translate(-50%, -50%);
              background: radial-gradient(circle, rgba(139,92,246,.7) 0%, rgba(124,58,237,.45) 30%,
                          rgba(109,40,217,.18) 58%, transparent 70%); }
.voce .ponto { position: absolute; left: 0; top: 0; width: 13px; height: 13px; border-radius: 50%;
               background: #fff; transform: translate(-50%, -50%); box-shadow: 0 0 10px #fff; }
.voce .nome { position: absolute; left: 14px; top: 0; transform: translateY(-50%); color: #fff;
              font-size: .8rem; font-weight: 600; }

.c-verde { --c: #22d3a0; } .c-azul { --c: #2ea8ff; }
.c-amarelo { --c: #f5b93a; } .c-vermelho { --c: #f43f5e; }
.mk { position: absolute; width: 0; height: 0; cursor: pointer; }
.mk .glow, .mk .ring, .mk .core { position: absolute; left: 0; top: 0; border-radius: 50%;
                                  transform: translate(-50%, -50%); }
.mk .glow { width: 120px; height: 120px;
            background: radial-gradient(circle, color-mix(in srgb, var(--c) 45%, transparent) 0%,
                        color-mix(in srgb, var(--c) 15%, transparent) 55%, transparent 70%); }
.mk .ring { width: 44px; height: 44px; border: 2px solid var(--c);
            background: color-mix(in srgb, var(--c) 18%, transparent); transition: transform .15s; }
.mk .core { width: 14px; height: 14px; background: var(--c); box-shadow: 0 0 10px var(--c); }
.mk:hover .ring { transform: translate(-50%, -50%) scale(1.15); }
.mk .mk-nome { position: absolute; left: 34px; top: 0; transform: translateY(-50%); width: 110px;
               color: #fff; font-size: .8rem; font-weight: 600; line-height: 1.2;
               text-shadow: 0 1px 6px rgba(0,0,0,.8); }

.bussola { position: absolute; top: 18px; right: 18px; width: 40px; height: 40px; border-radius: 50%;
           border: 1px solid rgba(139,92,246,.6); background: rgba(20,16,50,.7); color: #fff;
           display: flex; flex-direction: column; align-items: center; justify-content: center;
           font-size: .55rem; font-weight: 700; line-height: 1; gap: 2px; }
.legenda { position: absolute; left: 12px; bottom: 12px; background: rgba(15,14,40,.75);
           border: 1px solid rgba(255,255,255,.06); border-radius: 12px; padding: 12px 16px; }
.legenda div { display: flex; align-items: center; gap: 10px; color: #cfcde6; font-size: .8rem;
               margin: 5px 0; }
.legenda i { width: 12px; height: 12px; border-radius: 50%; background: var(--c); display: inline-block; }
.escala { position: absolute; left: 45%; bottom: 14px; color: #cfcde6; font-size: .75rem; width: 110px; }
.escala .nums { display: flex; justify-content: space-between; }
.escala .barra { height: 6px; border: 1px solid #cfcde6; border-top: none; margin-top: 6px; }

.popup { display: none; position: absolute; right: 14px; bottom: 14px; width: min(38%, 330px);
         background: rgba(18,18,48,.96); border: 1px solid rgba(139,92,246,.25); border-radius: 16px;
         overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,.45); }
.popup .foto { display: block; width: 100%; height: 110px; object-fit: cover; }
.popup .fechar { position: absolute; top: 8px; right: 10px; color: #cfcde6; cursor: pointer;
                 font-size: .9rem; width: 22px; height: 22px; text-align: center; line-height: 22px;
                 border-radius: 50%; background: rgba(0,0,0,.35); }
.p-body { padding: 14px 16px 16px; }
.p-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.p-head b { color: #fff; font-size: 1.02rem; }
.bortle { padding: 4px 12px; border-radius: 999px; font-size: .75rem; font-weight: 700; color: var(--c);
          background: color-mix(in srgb, var(--c) 18%, transparent); border: 1px solid var(--c); }
.p-sub { color: #a5a3c4; font-size: .8rem; margin: 6px 0 14px; }
.p-stats { display: flex; justify-content: space-between; margin-bottom: 14px; }
.p-stats b { display: block; color: #fff; font-size: 1.05rem; }
.p-stats span { color: #a5a3c4; font-size: .72rem; }
.p-btns { display: flex; gap: 10px; }
.p-btns a { flex: 1; text-align: center; padding: 11px 0; border-radius: 999px; font-weight: 600;
            cursor: pointer; text-decoration: none; font-size: .9rem; }
.p-plan { background: #8b5cf6; color: #fff !important; }
.p-rota { background: rgba(255,255,255,.06); color: #fff !important; border: 1px solid rgba(255,255,255,.12); }
"""
CSS += CSS_MAPA

HTML_HERO = """
<div class="hero">
  <div class="topo">
    <div class="marca">🌙 AstroLog</div>
    <div class="titulo-bemvindo">Bem-vindo!</div>
    <div class="slogan">Céus mais escuros<br>Um mundo mais curioso</div>
  </div>

  <div class="lua-area"></div>

  <div class="painel">
    <div class="tag">EXPLORE • OBSERVE • REGISTRE</div>
    <div class="chamada">O diário do seu céu</div>
    <div class="sub">Registre observações, planeje noites e encontre os céus
    mais escuros perto de você.</div>
    <div class="item"><div class="icone i1">🔭</div>
      <div><b>Planeje suas noites</b>
      <span>Veja condições, fases da Lua e os melhores horários.</span></div></div>
    <div class="item"><div class="icone i2">📍</div>
      <div><b>Encontre locais ideais</b>
      <span>Descubra áreas de céu escuro perto de você.</span></div></div>
    <div class="item"><div class="icone i3">📒</div>
      <div><b>Registre e acompanhe</b>
      <span>Mantenha seu diário e evolua como observador.</span></div></div>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Navegação: tela inicial -> app (Dashboard)
# ---------------------------------------------------------------------------
def entrar_no_app():
    """Esconde a tela inicial e mostra o app com as abas."""
    return gr.update(visible=False), gr.update(visible=True)


# ---------------------------------------------------------------------------
# ABA 1 — Dashboard NASA
# ---------------------------------------------------------------------------
def carregar_dashboard():
    try:
        r = requests.get(f"{API_BASE}/api/dashboard/hoje", timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        texto = f"### {d.get('titulo')}\n**Data:** {d.get('data')}\n\n{d.get('descricao')}"
        img_url = d.get("url_imagem") if d.get("media_type") == "image" else None
        return texto, img_url
    except (requests.RequestException, ValueError) as erro:
        gr.Warning(f"Falha ao carregar dashboard: {erro}")
        return f"❌ Erro: {erro}", None


# ---------------------------------------------------------------------------
# ABA 2 — Registrar observação
# ---------------------------------------------------------------------------
def registrar_observacao(astro, tipo, equipamento, data_hora, local,
                         poluicao, visibilidade, anotacoes):
    if not astro:
        return "❌ Informe o astro observado."
    payload = {
        "astro_observado": astro,
        "tipo_astro": tipo,
        "equipamento": equipamento,
        "data_hora": data_hora,
        "local": local,
        "poluicao_luminosa": poluicao,
        "visibilidade": visibilidade,
        "anotacoes": anotacoes,
    }
    try:
        r = requests.post(f"{API_BASE}/api/observacoes",
                          json=payload, timeout=TIMEOUT)
        if r.status_code == 201:
            d = r.json()
            return f"✅ Observação registrada! ID = {d['id']}"
        return f"❌ Erro {r.status_code}: {r.text}"
    except requests.RequestException as erro:
        return f"❌ Falha de conexão: {erro}"


# ---------------------------------------------------------------------------
# ABA 3 — Histórico
# ---------------------------------------------------------------------------
def listar_observacoes():
    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        r.raise_for_status()
        dados = r.json()
        if not dados:
            return pd.DataFrame(columns=["id", "astro_observado", "tipo_astro"])
        return pd.DataFrame(dados)
    except (requests.RequestException, ValueError) as erro:
        gr.Warning(f"Falha ao listar: {erro}")
        return pd.DataFrame({"erro": [str(erro)]})


def excluir_observacao(obs_id):
    try:
        obs_id = int(obs_id)
    except (TypeError, ValueError):
        return "❌ Informe um ID numérico."
    try:
        r = requests.delete(f"{API_BASE}/api/observacoes/{obs_id}", timeout=TIMEOUT)
        if r.status_code == 204:
            return f"✅ Observação {obs_id} excluída."
        if r.status_code == 404:
            return f"❌ Observação {obs_id} não encontrada."
        return f"❌ Erro {r.status_code}: {r.text}"
    except requests.RequestException as erro:
        return f"❌ Falha de conexão: {erro}"


# ---------------------------------------------------------------------------
# DASHBOARD (tela "Início")
# ---------------------------------------------------------------------------
LATITUDE, LONGITUDE = -23.55, -46.63   # ajuste para a sua cidade (usado só no clima)
SINODICO = 29.530588853                # duração do ciclo lunar, em dias
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# DADOS DE EXEMPLO (não há endpoint de planetas na API): nome, onde/quando, visibilidade, cor
PLANETAS_EXEMPLO = [
    ("Vênus", "Oeste · 18:30", "Baixa", "#f2c94c", get_base64_planeta("venus.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Venus_2_Approach_Image.jpg/240px-Venus_2_Approach_Image.jpg", 28),
    ("Júpiter", "Leste · 20:10", "Alta", "#d9a066", get_base64_planeta("jupiter.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Jupiter.jpg/240px-Jupiter.jpg", 42),
    ("Saturno", "Norte · 19:40", "Média", "#e0b96a", get_base64_planeta("saturno.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/Saturn_during_Equinox.jpg/240px-Saturn_during_Equinox.jpg", 38),
    ("Marte", "Madrugada · 04:15", "Média", "#e5534b", get_base64_planeta("marte.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/OSIRIS_Mars_true_color.jpg/240px-OSIRIS_Mars_true_color.jpg", 24),
]


def fase_lua():
    """Fase da Lua calculada a partir do ciclo sinódico (sem API externa)."""
    jd = datetime.now(timezone.utc).timestamp() / 86400 + 2440587.5
    idade = (jd - 2451550.1) % SINODICO          # 2000-01-06 = lua nova de referência
    p = idade / SINODICO                          # 0 nova · .25 quarto cresc. · .5 cheia
    ilum = (1 - math.cos(2 * math.pi * p)) / 2
    for limite, nome in [(.03, "Nova"), (.22, "Crescente"), (.28, "Quarto crescente"),
                         (.47, "Crescente gibosa"), (.53, "Cheia"), (.72, "Minguante gibosa"),
                         (.78, "Quarto minguante"), (.97, "Minguante")]:
        if p < limite:
            break
    else:
        nome = "Nova"
    nasce = (6 + p * 24) % 24                     # estimativa grosseira (~50 min/dia)
    se_poe = (nasce + 12) % 24
    hhmm = lambda h: f"{int(h):02d}:{int((h % 1) * 60):02d}"
    return p, nome, round(ilum * 100), hhmm(nasce), hhmm(se_poe)


def lua_svg(p, r=40):
    """Desenha a Lua iluminada de acordo com a fase p (0..1)."""
    c = r + 8
    crescendo = p < .5
    q = p if crescendo else 1 - p
    rx = abs(math.cos(2 * math.pi * q)) * r
    sweep = 0 if q < .25 else 1
    luz = f"M{c},{c-r} A{r},{r} 0 0 1 {c},{c+r} A{rx:.2f},{r} 0 0 {sweep} {c},{c-r} Z"
    espelho = "" if crescendo else f' transform="translate({2*c},0) scale(-1,1)"'
    return (f'<svg viewBox="0 0 {2*c} {2*c}"><circle cx="{c}" cy="{c}" r="{r}" fill="#14122b" '
            f'stroke="rgba(255,255,255,.08)"/><path d="{luz}" fill="#efe4c4"{espelho}/></svg>')


def _clima():
    """Nuvens (%), temperatura (°C) e umidade (%) via Open-Meteo (sem chave)."""
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=TIMEOUT, params={
            "latitude": LATITUDE, "longitude": LONGITUDE, "timezone": "auto",
            "current": "temperature_2m,relative_humidity_2m,cloud_cover"})
        r.raise_for_status()
        c = r.json()["current"]
        return round(c["cloud_cover"]), round(c["temperature_2m"]), round(c["relative_humidity_2m"])
    except (requests.RequestException, ValueError, KeyError):
        return None


def _apod():
    try:
        r = requests.get(f"{API_BASE}/api/dashboard/hoje", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


CEU_SVG = """<svg class="ceu-svg" viewBox="0 0 420 220"><defs><radialGradient id="gv">
<stop offset="0" stop-color="#ff5a6e"/><stop offset="1" stop-color="#7a1030" stop-opacity=".15"/>
</radialGradient></defs>
<circle cx="210" cy="110" r="200" fill="none" stroke="#8b5cf6" stroke-opacity=".15"/>
<circle cx="210" cy="110" r="150" fill="none" stroke="#8b5cf6" stroke-opacity=".12"/>
<circle cx="300" cy="110" r="100" fill="url(#gv)" opacity=".45"/>
<circle cx="300" cy="110" r="72" fill="url(#gv)" opacity=".65"/>
<circle cx="300" cy="110" r="46" fill="url(#gv)"/>
<circle cx="300" cy="110" r="7" fill="#fff"/><text x="314" y="115" fill="#fff" font-size="13" font-weight="600">Você</text>
<circle cx="120" cy="70" r="18" fill="#f2c94c" opacity=".25"/><circle cx="120" cy="70" r="9" fill="#f2c94c"/>
<circle cx="165" cy="150" r="18" fill="#2dd4bf" opacity=".25"/><circle cx="165" cy="150" r="6" fill="#2dd4bf"/>
<circle cx="55" cy="165" r="5" fill="#3b82f6"/></svg>"""


def montar_dashboard():
    """Monta o HTML completo do dashboard (Início)."""
    agora = datetime.now()
    h = agora.hour
    saudacao = "Bom dia" if 5 <= h < 12 else "Boa tarde" if 12 <= h < 18 else "Boa noite"
    data_txt = f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]}"

    p, fase, ilum, nasce, se_poe = fase_lua()
    nuvens, temp, umid = _clima() or (None, None, None)
    fmt = lambda v, un: "—" if v is None else f"{v}{un}"

    # --- CORREÇÃO AQUI: Descompactando as 6 variáveis corretamente ---
    planetas = "".join(
        f'<div class="planeta">'
        f'  <img src="{img_url}" class="img-planeta" style="width:{tam}px; height:{tam}px;" alt="{n}">'
        f'  <div class="info"><b>{n}</b><span>{onde}</span></div>'
        f'  <div class="badge b-{vis.lower().replace("é", "e")}">{vis}</div>'
        f'</div>'
        for n, onde, vis, cor, img_url, tam in PLANETAS_EXEMPLO)

    d = _apod()
    
    # Imagem padrão (fallback) caso a API falhe
    fallback_img = "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=800&auto=format&fit=crop"
    
    if d:
        link = d.get("hdurl") or d.get("url_imagem") or "#"
        img = d.get("url_imagem") if d.get("media_type") == "image" else fallback_img
        titulo = escape(d.get("titulo") or "Nebulosa em Detalhe")
        descricao = escape(d.get("descricao") or "Uma das nebulosas planetárias mais famosas do céu.")
        
        apod = (
            f'<div class="dcard apod">'
            f'  <div class="txt">'
            f'    <div class="tag2">FOTO ASTRONÔMICA DO DIA</div>'
            f'    <h2>{titulo}</h2>'
            f'    <p>{descricao}</p>'
            f'    <a class="btn-det" href="{escape(link)}" target="_blank">Ver detalhes ›</a>'
            f'  </div>'
            f'  <div class="img" style=\'background-image: url("{img}");\'></div>'
            f'</div>'
        )
    else:
        apod = (
            f'<div class="dcard apod">'
            f'  <div class="txt">'
            f'    <div class="tag2">FOTO ASTRONÔMICA DO DIA</div>'
            f'    <h2>Nebulosa em Detalhe</h2>'
            f'    <p>Uma das nebulosas planetárias mais famosas do céu, revelando sua estrutura em cores impressionantes.</p>'
            f'    <a class="btn-det" href="#" target="_blank">Ver detalhes ›</a>'
            f'  </div>'
            f'  <div class="img" style=\'background-image: url("{fallback_img}");\'></div>'
            f'</div>'
        )

    return f"""
<div class="dash">
  <div class="dcol">
    <div><h1>{saudacao}, Observador</h1><div class="data">{data_txt}</div></div>
    <div class="dcard lua-card">{lua_svg(p)}
      <div><div class="mini">Fase da Lua</div><div class="lua-nome">{fase}</div>
      <div style="font-weight:600;margin:4px 0">Iluminação: {ilum}%</div>
      <div class="amarelo">Nasce ~{nasce} · Se põe ~{se_poe}</div></div></div>
    <div class="dcard clima">
      <div><b class="verde">☁️ {fmt(nuvens, "%")}</b><span>Nuvens</span></div>
      <div><b>🌡️ {fmt(temp, "°C")}</b><span>Temperatura</span></div>
      <div><b class="azul">💧 {fmt(umid, "%")}</b><span>Umidade</span></div></div>
    <h3>Visibilidade planetária hoje</h3>
    <div class="dcard" style="padding:8px 16px">{planetas}</div>
  </div>
  <div class="dcol">
    <div class="dcard"><div class="ceu-head"><div><b>Seu céu esta noite</b>
      <span class="sub">Explore o universo ao seu redor</span></div>
      <a class="dash-link" onclick="document.getElementById('nav-mapa').click()">Ver mapa completo ›</a></div>
      {CEU_SVG}</div>
    {apod}
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Locais (tela "Mapa") e navegação do menu lateral
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# MAPA (tela "Mapa") — locais de exemplo; x/y são a posição em % do mapa
# ---------------------------------------------------------------------------
def foto_local(arquivo, largura=640):
    """Lê img/<arquivo>, reduz para uma miniatura JPEG e devolve um data URI (leve p/ a página)."""
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
    try:
        with Image.open(os.path.join(pasta, arquivo)) as im:
            im = im.convert("RGB")
            im.thumbnail((largura, largura))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except (FileNotFoundError, OSError):
        print(f"[AVISO] foto não encontrada: img/{arquivo}")
        return ""


LOCAIS_EXEMPLO = [
    dict(id="serra", nome="Serra do Campo Escuro", cor="verde", foto="serra_do_campo.png", foco="50% 62%", x=23.4, y=18.4, bortle=2,
         km=42, minutos=38, mag="21.9", nuvens=12, qualidade="Excelente"),
    dict(id="vale", nome="Vale das Estrelas", cor="amarelo", foto="vale_das_estrelas.png", foco="50% 50%", x=57.4, y=19.5, bortle=5,
         km=35, minutos=31, mag="20.4", nuvens=28, qualidade="Regular"),
    dict(id="pico", nome="Pico da Neblina", cor="azul", foto="pico_da_neblina.png", foco="50% 30%", x=55.6, y=52.5, bortle=3,
         km=18, minutos=22, mag="21.3", nuvens=18, qualidade="Bom"),
    dict(id="morro", nome="Morro do Horizonte", cor="vermelho", foto="morro_do_horizonte.png", foco="50% 52%", x=15.0, y=65.0, bortle=7,
         km=9, minutos=14, mag="18.9", nuvens=45, qualidade="Ruim"),
]


def _cabecalho_popup(l):
    uri = foto_local(l["foto"])
    if uri:
        return f'<img class="foto" src="{uri}" alt="{escape(l["nome"])}" style="object-position:{l["foco"]}">'
    return (f'<svg class="foto" viewBox="0 0 300 40" preserveAspectRatio="none"><defs>'
            f'<linearGradient id="ceu-{l["id"]}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f2a55"/>'
            f'<stop offset="1" stop-color="#2b5c9a"/></linearGradient></defs>'
            f'<rect width="300" height="40" fill="url(#ceu-{l["id"]})"/>'
            f'<path d="M0,40 L0,28 L40,18 L70,26 L120,8 L170,24 L210,14 L260,26 L300,16 L300,40 Z" fill="#0a0f24"/></svg>')


def montar_mapa_html():
    from urllib.parse import quote
    rnd = random.Random(7)
    estrelas = "".join(
        f'<circle cx="{rnd.uniform(0, 1000):.0f}" cy="{rnd.uniform(0, 560):.0f}" '
        f'r="{rnd.choice([.6, .8, 1, 1.4]):.1f}" fill="{rnd.choice(["#fff", "#fff", "#9ec5ff", "#ffe29a"])}" '
        f'opacity="{rnd.uniform(.25, .9):.2f}"/>' for _ in range(170))
    linhas = "".join(
        f'<polyline points="{pts}" fill="none" stroke="#6d7bff" stroke-opacity=".28"/>'
        for pts in ("690,110 750,150 820,140 880,205", "120,300 180,255 250,275",
                    "800,330 870,385 950,350", "300,470 360,420 450,430"))
    fundo = f'<svg class="estrelas" viewBox="0 0 1000 560" preserveAspectRatio="none">{linhas}{estrelas}</svg>'
    aneis = "".join(f'<div class="anel-d" style="width:{d}px;height:{d}px"></div>' for d in (190, 400, 640))

    radios = "".join(f'<input type="radio" name="loc" id="loc-{l["id"]}" class="loc-radio"'
                     f'{" checked" if i == 0 else ""}>' for i, l in enumerate(LOCAIS_EXEMPLO))
    radios += '<input type="radio" name="loc" id="loc-nenhum" class="loc-radio">'
    regras = "".join(f'#loc-{l["id"]}:checked ~ .mapa .popup-{l["id"]}{{display:block}}'
                     f'#loc-{l["id"]}:checked ~ .mapa .mk-{l["id"]} .ring{{transform:translate(-50%,-50%) scale(1.2);'
                     f'box-shadow:0 0 18px var(--c)}}' for l in LOCAIS_EXEMPLO)

    marcadores = "".join(
        f'<label for="loc-{l["id"]}" class="mk mk-{l["id"]} c-{l["cor"]}" style="left:{l["x"]}%;top:{l["y"]}%">'
        f'<span class="glow"></span><span class="ring"></span><span class="core"></span>'
        f'<span class="mk-nome">{escape(l["nome"])}</span></label>' for l in LOCAIS_EXEMPLO)

    popups = "".join(
        f'<div class="popup popup-{l["id"]} c-{l["cor"]}">'
        f'<label for="loc-nenhum" class="fechar">✕</label>'
        f'{_cabecalho_popup(l)}'
        f'<div class="p-body"><div class="p-head"><b>{escape(l["nome"])}</b>'
        f'<span class="bortle">Bortle {l["bortle"]}</span></div>'
        f'<div class="p-sub">{l["km"]} km de você · {l["minutos"]} min de carro</div>'
        f'<div class="p-stats"><div><b>{l["mag"]}</b><span>mag/arcsec²</span></div>'
        f'<div><b>{l["nuvens"]}%</b><span>nuvens hoje</span></div>'
        f'<div><b>{l["qualidade"]}</b><span>qualidade</span></div></div>'
        f'<div class="p-btns"><a class="p-plan" onclick="document.getElementById(\'nav-diario\').click()">'
        f'Planejar sessão</a><a class="p-rota" target="_blank" '
        f'href="https://www.google.com/maps/search/?api=1&query={quote(l["nome"])}">Rota</a></div></div></div>'
        for l in LOCAIS_EXEMPLO)

    legenda = "".join(f'<div class="c-{c}"><i></i>{n}</div>' for c, n in
                      [("verde", "Excelente"), ("azul", "Bom"), ("amarelo", "Regular"), ("vermelho", "Ruim")])
    bussola = ('<div class="bussola">N<svg width="14" height="14" viewBox="0 0 14 14">'
               '<polygon points="7,1 12,13 7,10 2,13" fill="#fff"/></svg></div>')
    escala = ('<div class="escala"><div class="nums"><span>0</span><span>25</span><span>50 km</span></div>'
              '<div class="barra"></div></div>')

    return (f'<style>{regras}</style><div class="mapa-wrap">{radios}<div class="mapa">{fundo}{aneis}'
            f'<div class="voce"><div class="halo"></div><div class="ponto"></div><div class="nome">Você</div></div>'
            f'{marcadores}{bussola}<div class="legenda">{legenda}</div>{escala}{popups}</div></div>')


MAPA_HTML = montar_mapa_html()


COLS_LOCAIS = ["id", "nome", "latitude", "longitude", "nivel_poluicao", "descricao"]


def listar_locais(busca=""):
    try:
        r = requests.get(f"{API_BASE}/api/locais", timeout=TIMEOUT)
        r.raise_for_status()
        df = pd.DataFrame(r.json(), columns=COLS_LOCAIS)
        if busca:
            df = df[df["nome"].str.contains(busca, case=False, na=False)]
        return df
    except (requests.RequestException, ValueError) as erro:
        gr.Warning(f"Falha ao listar locais: {erro}")
        return pd.DataFrame({"erro": [str(erro)]})


PAGINAS = ["inicio", "mapa", "diario"]


def ir_para(pagina):
    """Mostra uma página e destaca o item correspondente do menu."""
    return ([gr.update(visible=(p == pagina)) for p in PAGINAS]
            + [gr.update(variant="primary" if p == pagina else "secondary") for p in PAGINAS])


# ---------------------------------------------------------------------------
# Layout Gradio: tela inicial + app com 3 abas
# ---------------------------------------------------------------------------
with gr.Blocks(title="AstroLog", css=CSS) as demo:

    # ---------- TELA INICIAL (visível ao abrir) ----------
    with gr.Column(visible=True, elem_id="tela-inicio") as tela_inicio:
        gr.HTML(HTML_HERO)
        btn_comecar = gr.Button("Comece agora", elem_id="btn-comecar")

    # ---------- APP PRINCIPAL (escondido até clicar no botão) ----------
    with gr.Column(visible=False, elem_id="tela-app") as tela_app:
        # Topbar (Agora fixa via CSS)
        with gr.Row(elem_id="topbar"):
            gr.HTML('<div class="logo">🌙 AstroLog</div>', elem_id="topbar-logo")
            busca = gr.Textbox(show_label=False, container=False, elem_id="busca",
                               scale=0, min_width=0,
                               placeholder="🔍  Buscar local de observação...")

        # Corpo (Ajustado via CSS com margens para compensar os fixos)
        with gr.Row(elem_id="corpo", equal_height=False):
            with gr.Column(scale=0, min_width=210, elem_id="sidebar"):
                # Botões do menu (mantidos)
                nav_inicio = gr.Button("🏠  Início", variant="primary",
                                       elem_id="nav-inicio", elem_classes="nav-btn")
                nav_mapa = gr.Button("📍  Mapa", variant="secondary",
                                     elem_id="nav-mapa", elem_classes="nav-btn")
                nav_diario = gr.Button("📒  Diário", variant="secondary",
                                       elem_id="nav-diario", elem_classes="nav-btn")
                gr.HTML('<div class="side-tag"><span class="estrela">☆</span>'
                        'Céus mais escuros para um amanhã mais brilhante.</div>', elem_id="side-tag")

            with gr.Column(scale=1, elem_id="conteudo"):
                # ... (conteúdo mantido igual) ...
                with gr.Column(visible=True) as pg_inicio:
                    dash_html = gr.HTML()

                with gr.Column(visible=False) as pg_mapa:
                    gr.HTML(MAPA_HTML)
                    with gr.Accordion("Locais cadastrados (API)", open=False):
                        df_locais = gr.Dataframe(label="Locais cadastrados")

                with gr.Column(visible=False) as pg_diario:
                    gr.Markdown("## 📒 Diário de observações")
                    with gr.Tab("Registrar Observação"):
                        with gr.Row():
                            astro = gr.Textbox(label="Astro observado",
                                               placeholder="Ex.: Júpiter")
                            tipo = gr.Dropdown(TIPOS_ASTRO, label="Tipo de astro",
                                               value="planeta")
                        equipamento = gr.Textbox(label="Equipamento",
                                                 placeholder="Ex.: Telescópio Refletor 114mm")
                        data_hora = gr.Textbox(label="Data e hora (ISO 8601)",
                                               placeholder="2025-03-10T22:30:00")
                        local = gr.Textbox(label="Local", placeholder="Cidade ou coordenadas")
                        with gr.Row():
                            poluicao = gr.Dropdown(POLUICAO, label="Poluição luminosa",
                                                   value="baixa")
                            visibilidade = gr.Dropdown(VISIBILIDADE, label="Visibilidade",
                                                       value="boa")
                        anotacoes = gr.Textbox(label="Anotações", lines=3)
                        btn_salvar = gr.Button("Salvar", variant="primary")
                        msg_salvar = gr.Markdown()
                        btn_salvar.click(
                            registrar_observacao,
                            inputs=[astro, tipo, equipamento, data_hora, local,
                                    poluicao, visibilidade, anotacoes],
                            outputs=msg_salvar,
                        )

                    with gr.Tab("Histórico de Observações"):
                        btn_listar = gr.Button("Listar", variant="primary")
                        df_hist = gr.Dataframe(label="Observações registradas")
                        with gr.Row():
                            id_excluir = gr.Textbox(label="ID para excluir", scale=1)
                            btn_excluir = gr.Button("Excluir", variant="stop", scale=1)
                        msg_excluir = gr.Markdown()

                        btn_listar.click(listar_observacoes, inputs=None, outputs=df_hist)
                        btn_excluir.click(excluir_observacao, inputs=id_excluir,
                                          outputs=msg_excluir)

    # ---------- Menu lateral e busca ----------
    saidas_nav = [pg_inicio, pg_mapa, pg_diario, nav_inicio, nav_mapa, nav_diario]
    nav_inicio.click(lambda: ir_para("inicio"), None, saidas_nav).then(
        montar_dashboard, None, dash_html)
    nav_mapa.click(lambda: ir_para("mapa"), None, saidas_nav).then(
        listar_locais, busca, df_locais)
    nav_diario.click(lambda: ir_para("diario"), None, saidas_nav).then(
        listar_observacoes, None, df_hist)
    busca.submit(lambda: ir_para("mapa"), None, saidas_nav).then(
        listar_locais, busca, df_locais)

    # ---------- "Comece agora": esconde a tela inicial e abre o dashboard ----------
    btn_comecar.click(
        entrar_no_app, inputs=None, outputs=[tela_inicio, tela_app]
    ).then(
        montar_dashboard, inputs=None, outputs=dash_html
    ).then(
        listar_observacoes, inputs=None, outputs=df_hist
    )


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.abspath(os.path.join(current_dir, "..", "img"))
    demo.launch(allowed_paths=[img_path])