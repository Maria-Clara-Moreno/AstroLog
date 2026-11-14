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

API_BASE = os.getenv("ASTROLOG_API", "http://127.0.0.1:5000")
TIMEOUT = 15

# Script que injeta a máscara de digitação assim que a página carrega
INPUT_MASK_JS = """
<script>
document.addEventListener('input', function(e) {
    // 1. ID para excluir (Apenas números)
    if (e.target.closest('#id-excluir')) {
        let val = e.target.value;
        let novoVal = val.replace(/[^0-9]/g, ''); // Remove tudo que não for número
        if (val !== novoVal) {
            e.target.value = novoVal;
        }
    }
    
    // 2. Data e Hora (Apenas números, -, :, T e t)
    if (e.target.closest('#data-hora')) {
        let val = e.target.value;
        let novoVal = val.replace(/[^0-9\\-\\:Tt]/g, ''); // Remove caracteres inválidos para ISO 8601
        if (val !== novoVal) {
            e.target.value = novoVal;
        }
    }
}, true); // O 'true' ativa o modo de captura, funcionando mesmo se o Gradio recriar o campo
</script>
"""

EDIT_JS = """
<script>
window.editObs = function(obsId) {
    // Procura o botão oculto do Gradio que criaremos no layout
    const btn = document.querySelector('#hidden-edit-btn button');
    if (btn) {
        // Define o valor do textbox oculto (ID da observação)
        const input = document.querySelector('#hidden-edit-id textarea');
        if (input) {
            input.value = obsId;
            // Dispara o evento de input para o Gradio perceber a mudança
            input.dispatchEvent(new Event('input', { bubbles: true }));
            // Clica no botão para executar a função Python
            btn.click();
        }
    }
};
</script>
"""

def motivo_falha(erro):
    """Explica em português (texto simples) por que uma chamada à API falhou."""
    if isinstance(erro, requests.Timeout):
        return f"A API demorou demais para responder em {API_BASE}."
    if isinstance(erro, requests.ConnectionError):
        return (f"A API não respondeu em {API_BASE}. Ela provavelmente não está rodando "
                "ou caiu ao iniciar (por exemplo, porque o MariaDB não estava ligado).")
    if isinstance(erro, requests.HTTPError) and erro.response is not None:
        return (f"A API respondeu com erro {erro.response.status_code}. "
                "Veja a mensagem no terminal onde ela está rodando.")
    return f"Resposta inesperada da API: {erro}"

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
           padding: 12px 16px !important; border-radius: 5px !important; font-weight: 600 !important; }
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
/* ===== Blocos Inferiores do Dashboard ===== */
.dash-bottom {
    display: grid;
    grid-template-columns: 1fr 1.1fr; /* Mesma proporção da grid superior */
    gap: 20px;
    margin-top: 24px; /* Afasta do bloco de cima */
    align-items: start; /* Impede que os cards estiquem verticalmente se um for menor */
}
.bottom-card {
    background: rgba(22,24,52,.75);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 18px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    min-width: 0; /* Impede que o conteúdo force o card a ficar mais largo que a coluna */
}
.bottom-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}
.bottom-head h2 {
    font-size: 1.15rem;
    color: #fff;
    margin: 0;
    font-weight: 700;
}
.bottom-link {
    color: #8b5cf6;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 4px;
}
.bottom-link:hover { text-decoration: underline; }

/* Lista de Últimas Observações */
.obs-list { display: flex; flex-direction: column; width: 100%; }
.obs-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid rgba(255,255,255,.05);
    gap: 16px; /* Garante espaço entre nome e local */
}
.obs-row:last-child { border-bottom: none; }
.obs-row .obs-name { 
    color: #fff; 
    font-size: 0.9rem; 
    font-weight: 500; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis; /* Trunca o texto se for muito longo */
}
.obs-row .obs-local { 
    color: #a5a3c4; 
    font-size: 0.8rem; 
    text-align: right; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis; 
    max-width: 50%; /* Impede que o local empurre o nome */
}

/* Lista de Próximos Eventos */
.event-list { display: flex; flex-direction: column; gap: 12px; }
.event-row {
    display: flex;
    align-items: flex-start;
    gap: 16px;
}
.event-date {
    color: #f2c94c;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    min-width: 50px;
    margin-top: 2px;
}
.event-desc { color: #e8e6f5; font-size: 0.9rem; line-height: 1.4; }

@media (max-width: 800px) {
    .dash-bottom { grid-template-columns: 1fr; }
}
"""
CSS += CSS_DASH

CSS_MAPA = """
/* ===== Tela Mapa ===== */
#side-tag { margin-top: auto !important; background: rgba(255,255,255,.04) !important;
            border-radius: 14px !important; padding: 14px !important; border: none !important; }
.side-tag { color: #a5a3c4; font-size: .8rem; line-height: 1.45; }
.side-tag .estrela { color: #f2c94c; font-size: 1rem; display: block; margin-bottom: 4px; }

.loc-radio { position: absolute; opacity: 0; pointer-events: none; width: 0; height: 0; }
.mp-grid { display: grid; grid-template-columns: 1fr 340px; gap: 14px; height: calc(100vh - 114px); min-height: 560px; }
.mapa { position: relative; height: 100%; overflow: hidden; border-radius: 20px;
        border: 1px solid rgba(120,130,255,.15);
        background: radial-gradient(ellipse at 35% 43%, #12123a 0%, #0a0b20 55%, #07081a 100%); }
.mapa .estrelas { position: absolute; inset: 0; width: 100%; height: 100%; }
.hd-layer { display: none; }

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
.mk { position: absolute; width: 0; height: 0; cursor: pointer; transition: opacity .2s; }
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
.mk .mk-tag { display: none; position: absolute; left: 34px; top: 26px; padding: 2px 10px; border-radius: 999px;
              font-size: .7rem; font-weight: 700; color: #0a0b20; background: var(--c); white-space: nowrap; }

/* filtros no topo do mapa e botão Rota */
.mp-chips { position: absolute; left: 16px; top: 14px; display: flex; gap: 8px; z-index: 4; }
.mp-chips label { padding: 7px 16px; border-radius: 999px; cursor: pointer; font-size: .8rem; font-weight: 600;
                  color: #cfcde6; background: rgba(20,22,52,.85); border: 1px solid rgba(255,255,255,.12); }
.rota-btn { display: none; position: absolute; top: 12px; right: 16px; z-index: 4; padding: 10px 28px;
            border-radius: 999px; background: #8b5cf6; color: #fff !important; font-weight: 600;
            text-decoration: none; box-shadow: 0 6px 18px rgba(139,92,246,.35); }
.bussola { position: absolute; top: 64px; right: 22px; width: 40px; height: 40px; border-radius: 50%;
           border: 1px solid rgba(139,92,246,.6); background: rgba(20,16,50,.7); color: #fff;
           display: flex; flex-direction: column; align-items: center; justify-content: center;
           font-size: .55rem; font-weight: 700; line-height: 1; gap: 2px; }

/* legenda reaproveitada: faixa colorida vertical (o nome aparece ao passar o mouse) */
.faixa { position: absolute; left: 16px; top: 72px; z-index: 4; display: flex; flex-direction: column; gap: 10px;
         padding: 10px 8px; border-radius: 14px; background: rgba(15,14,40,.75); border: 1px solid rgba(255,255,255,.06); }
.faixa span { position: relative; display: block; width: 10px; height: 22px; border-radius: 6px; background: var(--c); }
.faixa span:hover::after { content: attr(data-nome); position: absolute; left: 24px; top: 50%;
         transform: translateY(-50%); padding: 4px 10px; border-radius: 8px; white-space: nowrap; color: #fff;
         font-size: .75rem; font-weight: 600; background: rgba(15,14,40,.95); border: 1px solid rgba(255,255,255,.12); }
.escala { position: absolute; left: 45%; bottom: 14px; color: #cfcde6; font-size: .75rem; width: 110px; }
.escala .nums { display: flex; justify-content: space-between; }
.escala .barra { height: 6px; border: 1px solid #cfcde6; border-top: none; margin-top: 6px; }

/* coluna da direita: card do local + gráfico */
.mp-lado { display: flex; flex-direction: column; gap: 14px; overflow-y: auto; min-height: 0; }
.mp-card { display: none; border-radius: 20px; overflow: hidden; flex: none;
           background: rgba(18,18,48,.96); border: 1px solid rgba(139,92,246,.2); }
.mp-card .foto { display: block; width: 100%; height: 120px; object-fit: cover; }
.p-body { padding: 14px 16px 16px; }
.p-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.p-head b { color: #fff; font-size: 1.02rem; }
.bortle { padding: 4px 12px; border-radius: 999px; font-size: .75rem; font-weight: 700; color: var(--c);
          background: color-mix(in srgb, var(--c) 18%, transparent); border: 1px solid var(--c); white-space: nowrap; }
.p-sub { color: #a5a3c4; font-size: .8rem; margin: 6px 0 14px; }
.p-stats { display: flex; justify-content: space-between; margin-bottom: 14px; }
.p-stats b { display: block; color: #fff; font-size: 1.05rem; }
.p-stats span { color: #a5a3c4; font-size: .72rem; }
.p-btns { display: flex; gap: 10px; }
.p-btns a { flex: 1; text-align: center; padding: 11px 0; border-radius: 999px; font-weight: 600;
            cursor: pointer; text-decoration: none; font-size: .9rem; }
.p-plan { background: #8b5cf6; color: #fff !important; }
.p-rota { background: rgba(255,255,255,.06); color: #fff !important; border: 1px solid rgba(255,255,255,.12); }
.mp-graf { padding: 16px 16px 12px; }
.mp-graf .p-sub { margin-bottom: 8px; }
.g-svg { display: block; width: 100%; height: auto; }
@media (max-width: 1000px) { .mp-grid { grid-template-columns: 1fr; height: auto; } .mapa { height: 480px; } }
"""
CSS += CSS_MAPA

CSS_DIARIO = """
/* ===== Tema do app (vale para os componentes padrão do Gradio dentro do app) ===== */
#tela-app {
    --body-text-color: #e8e6f5; --body-text-color-subdued: #a5a3c4;
    --background-fill-primary: #0f0f2a; --background-fill-secondary: #14143a;
    --block-background-fill: rgba(22,24,52,.75); --block-border-color: rgba(255,255,255,.07);
    --block-border-width: 1px; --block-radius: 16px; --panel-background-fill: rgba(22,24,52,.75);
    --block-label-background-fill: transparent; --block-label-text-color: #cfcde6;
    --block-title-text-color: #cfcde6; --border-color-primary: rgba(255,255,255,.08);
    --input-background-fill: #0d0d26; --input-border-color: rgba(139,92,246,.28);
    --input-border-color-focus: #8b5cf6; --input-placeholder-color: #6f6d92; --input-radius: 12px;
    --color-accent: #8b5cf6; --border-color-accent: #8b5cf6; --color-accent-soft: rgba(139,92,246,.18);
    --button-primary-background-fill: #8b5cf6; --button-primary-background-fill-hover: #7c4de8;
    --button-primary-text-color: #fff; --button-primary-border-color: transparent;
    --button-cancel-background-fill: rgba(244,63,94,.15);
    --button-cancel-background-fill-hover: rgba(244,63,94,.28);
    --button-cancel-text-color: #fb7185; --button-cancel-border-color: #f43f5e;
    --table-even-background-fill: #10102a; --table-odd-background-fill: #15153a;
    --table-border-color: rgba(255,255,255,.07); --table-row-focus: rgba(139,92,246,.18);
}
#tela-app button.primary, #tela-app button.stop { border-radius: 5px !important; font-weight: 600 !important; }

/* ===== Botão "Novo registro" na navbar ===== */
#btn-novo { margin-left: auto !important; flex: none !important; width: auto !important;
            min-width: 0 !important; background: #8b5cf6 !important; color: #fff !important;
            border: none !important; border-radius: 999px !important; font-weight: 600 !important;
            padding: 11px 24px !important; box-shadow: 0 6px 18px rgba(139,92,246,.35); }
#btn-novo:hover { background: #7c4de8 !important; }

/* ===== Abas do Diário (viram "pílulas") ===== */
#diario-tabs { background: transparent !important; border: none !important; }
#diario-tabs .tab-wrapper, #diario-tabs .tab-container, #diario-tabs .tab-nav
    { border: none !important; border-bottom: none !important; }
#diario-tabs .tab-container::after { display: none !important; }
#diario-tabs button[role="tab"] { background: rgba(255,255,255,.06) !important; color: #cfcde6 !important;
    border: none !important; border-radius: 999px !important; padding: 8px 20px !important;
    margin-right: 8px; font-weight: 600 !important; box-shadow: none !important; }
#diario-tabs button[role="tab"]::after { display: none !important; }
#diario-tabs button[role="tab"][aria-selected="true"], #diario-tabs button[role="tab"].selected
    { background: #8b5cf6 !important; color: #fff !important; }
#diario-tabs .tabitem, #diario-tabs div[role="tabpanel"]
    { background: transparent !important; border: none !important; padding: 18px 0 0 !important; }

/* ===== Diário: cabeçalho, filtros, lista e detalhes ===== */
.diario-head h1 { font-size: 1.9rem; font-weight: 800; color: #fff; margin: 0; }
.diario-head p { color: #a5a3c4; margin: 4px 0 16px; }
.d-radio { position: absolute; opacity: 0; pointer-events: none; width: 0; height: 0; }
.d-vazio code { background: rgba(139,92,246,.18); color: #cfc2ff; padding: 2px 8px; border-radius: 6px; }
.d-vazio { color: #a5a3c4; padding: 40px; text-align: center; border-radius: 16px;
           background: rgba(22,24,52,.75); border: 1px solid rgba(255,255,255,.06); }
.d-grid { display: grid; grid-template-columns: minmax(300px, 1fr) 1.15fr; gap: 22px; align-items: start; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.chip { padding: 7px 16px; border-radius: 999px; background: rgba(255,255,255,.06); color: #cfcde6;
        font-size: .8rem; font-weight: 600; cursor: pointer; }
.d-lista { display: flex; flex-direction: column; gap: 12px; max-height: calc(100vh - 370px); min-height: 240px;
           overflow-y: auto; padding: 2px 6px 2px 2px; }
.d-item { display: flex; gap: 14px; align-items: center; padding: 14px; border-radius: 16px; cursor: pointer;
          background: rgba(22,24,52,.75); border: 1px solid rgba(255,255,255,.06); }
.d-item:hover { border-color: rgba(139,92,246,.5); }
.d-item .ic { width: 52px; height: 52px; border-radius: 50%; background: rgba(255,255,255,.05); flex: none;
              display: flex; align-items: center; justify-content: center; }
.d-item .ic svg { width: 36px; height: 36px; }
.d-item b { display: block; color: #fff; font-size: .95rem; }
.d-item small { display: block; color: #a5a3c4; font-size: .78rem; margin: 3px 0 7px; }
.tag-t { display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: .72rem; font-weight: 700; }
.t-planeta .tag-t { background: #3a2f12; color: #f2c94c; } .t-estrela .tag-t { background: #12304a; color: #38bdf8; }
.t-nebula .tag-t { background: #3a1239; color: #f472b6; } .t-galaxia .tag-t { background: #0f3a3f; color: #22d3ee; }
.t-lua .tag-t { background: #2c2f45; color: #cfcde6; } .t-outro .tag-t { background: #2a2250; color: #c4b5fd; }
.d-det { display: none; padding: 16px; border-radius: 20px; background: rgba(22,24,52,.75);
         border: 1px solid rgba(255,255,255,.06); }
.d-banner { position: relative; height: 190px; border-radius: 16px; overflow: hidden; display: flex;
            align-items: center; justify-content: center;
            background: radial-gradient(circle at 50% 50%, rgba(139,92,246,.28), transparent 62%), #0b0b24; }
.d-banner::before, .d-banner::after { content: ""; position: absolute; border-radius: 50%;
            border: 1px solid rgba(139,92,246,.25); }
.d-banner::before { width: 230px; height: 230px; } .d-banner::after { width: 330px; height: 330px; opacity: .6; }
.d-banner svg { position: relative; z-index: 1; height: 150px; width: 150px; }
.d-det h2 { color: #fff; font-size: 1.4rem; margin: 18px 0 2px; }
.d-det .quando { color: #a5a3c4; font-size: .85rem; }
.d-tab { margin-top: 16px; border: 1px solid rgba(255,255,255,.07); border-radius: 14px; overflow: hidden; }
.d-tab > div { display: flex; justify-content: flex-start; gap: 12px; padding: 11px 16px; font-size: .85rem;
               border-bottom: 1px solid rgba(255,255,255,.05); }
.d-tab > div:last-child { border-bottom: none; }
.d-tab span { color: #a5a3c4; } .d-tab b { color: #fff; text-align: right; }
.d-notas { margin-top: 14px; padding: 14px 16px; border-radius: 14px; color: #e8e6f5; font-size: .9rem;
           border: 1px solid rgba(255,255,255,.07); line-height: 1.5; }
.d-notas small { display: block; color: #a5a3c4; letter-spacing: .08em; font-size: .65rem; margin-bottom: 6px; }
@media (max-width: 1000px) { .d-grid { grid-template-columns: 1fr; } }
/* ===== Botão Editar no Detalhe ===== */
.d-det-header { display: flex; justify-content: space-between; align-items: flex-start; margin-top: 18px; margin-bottom: 2px; }
.d-det-header h2 { margin: 0 !important; flex: 1; }
.btn-edit { background: rgba(139, 92, 246, 0.15); color: #cfc2ff; border: 1px solid rgba(139, 92, 246, 0.4); padding: 8px 16px; 
            border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; 
            transition: all 0.2s; text-decoration: none; white-space: nowrap; }
.btn-edit:hover { background: rgba(139, 92, 246, 0.3); border-color: #8b5cf6; color: #fff; }
/* Ajuste para telas menores */
@media (max-width: 600px) { .d-det-header { flex-direction: column; gap: 10px; } .btn-edit { align-self: flex-start; } }
/* ===== Linha do Tempo (Timeline) ===== */
.timeline-group { margin-bottom: 24px; }
.timeline-header { color: #a5a3c4; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 16px; padding-left: 14px; /* Alinha com o texto dos itens */ }
.timeline-item { display: flex; position: relative; margin-bottom: 12px; }
/* A linha vertical conectora */
.timeline-item::before { content: ""; position: absolute; left: 15px; /* Centraliza com a bolinha */ top: 32px; /* Começa depois da bolinha */
                        bottom: -16px; /* Vai até o próximo item */ width: 1px; background: rgba(255,255,255,0.1); z-index: 0; }
.timeline-item:last-child::before { display: none; /* Remove a linha do último item */ }
/* A bolinha colorida */
.tl-dot { width: 12px; height: 12px; border-radius: 50%; flex: none; margin-top: 22px; /* Alinha com o topo do card */ margin-right: 16px;
    margin-left: 9px; position: relative; z-index: 1; box-shadow: 0 0 10px var(--dot-color); }
/* Cores das bolinhas baseadas no tipo */
.t-planeta .tl-dot { --dot-color: #f2c94c; background-color: #f2c94c; }
.t-estrela .tl-dot { --dot-color: #38bdf8; background-color: #38bdf8; }
.t-nebula .tl-dot { --dot-color: #f472b6; background-color: #f472b6; }
.t-galaxia .tl-dot { --dot-color: #22d3ee; background-color: #22d3ee; }
.t-lua .tl-dot { --dot-color: #efe4c4; background-color: #efe4c4; }
.t-outro .tl-dot { --dot-color: #c4b5fd; background-color: #c4b5fd; }
/* Data em cima do card */
.tl-date { color: #f2c94c; /* Cor dourada conforme a imagem */ font-size: 0.8rem; font-weight: 700; margin-bottom: 6px; padding-left: 4px; }
/* Ajuste no item do card para ficar como na imagem */
.timeline-item .d-item { flex: 1; margin: 0; padding: 16px 20px; display: flex; 
                        align-items: center; background: rgba(22,24,52,.6); /* Um pouco mais transparente */ }
"""
CSS += CSS_DIARIO

CSS_EPOCA = """
/* ===== Melhor época ===== */
.me-radio { position: absolute; opacity: 0; pointer-events: none; width: 0; height: 0; }
.me-chips { display: flex; flex-wrap: wrap; gap: 10px; margin: 4px 0 22px; }
.me-chips label { padding: 10px 22px; border-radius: 999px; cursor: pointer; font-weight: 600; color: #cfcde6;
                  background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.1); }
.me-grid { display: grid; grid-template-columns: 1.75fr 1fr; gap: 22px; align-items: start; }
.me-card { padding: 18px; border-radius: 20px; background: rgba(15,16,38,.85); border: 1px solid rgba(255,255,255,.07); }
.me-tab { display: none; }
.me-linha { display: grid; grid-template-columns: 150px repeat(12, 1fr); gap: 8px; align-items: center; }
.me-cab { margin-bottom: 8px; padding: 0 12px; color: #8a88ad; font-size: .75rem; font-weight: 600; text-align: center; }
.me-cab .atual { color: #8b5cf6; }
.me-linha:not(.me-cab) { background: rgba(255,255,255,.03); border-radius: 14px; padding: 10px 12px; margin-bottom: 10px; }
.me-linha b { color: #fff; font-size: .95rem; }
.me-linha .cel { height: 38px; border-radius: 12px; background: #181a35; display: flex;
                 align-items: center; justify-content: center; }
.me-linha .cel.atual { outline: 1px solid rgba(139,92,246,.85); }
.me-linha .cel i { width: 9px; height: 9px; border-radius: 50%; background: #fff; }
.me-nota { color: #8a88ad; font-size: .8rem; margin-top: 6px; }
.me-dir { display: flex; flex-direction: column; gap: 18px; }
.me-noite { display: none; padding: 22px; border-radius: 20px; border: 1px solid rgba(139,92,246,.55);
            background: linear-gradient(135deg, rgba(76,29,149,.45), rgba(20,16,56,.9)); }
.me-noite .mini2 { color: #f6c453; font-size: .7rem; letter-spacing: .12em; font-weight: 700; }
.me-noite h3 { color: #fff; font-size: 1.5rem; margin: 8px 0 10px; line-height: 1.2; }
.me-noite p { color: #a5a3c4; margin: 6px 0; font-size: .9rem; }
.me-eventos { padding: 22px; border-radius: 20px; background: rgba(15,16,38,.85); border: 1px solid rgba(255,255,255,.07); }
.me-eventos h3 { color: #fff; font-size: 1.3rem; margin: 0 0 14px; }
.me-eventos .ev { display: flex; gap: 18px; padding: 9px 0; }
.me-eventos .ev b { color: #f6c453; min-width: 64px; } .me-eventos .ev span { color: #e8e6f5; }
@media (max-width: 1100px) { .me-grid { grid-template-columns: 1fr; }
                             .me-linha { grid-template-columns: 100px repeat(12, 1fr); } }
/* ===== SCROLLBAR PERSONALIZADA ===== */
/* Firefox */
* {
    scrollbar-width: thin;
    scrollbar-color: #8b5cf6 #0d0c1d;
}

/* Chrome, Edge, Safari */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}
::-webkit-scrollbar-track {
    background: #0d0c1d; /* Fundo escuro combinando com a sidebar */
    border-radius: 8px;
}
::-webkit-scrollbar-thumb {
    background: #3b0764; /* Roxo escuro para o "botão" */
    border-radius: 8px;
    border: 2px solid #0d0c1d; /* Cria um espaçamento entre a barra e o fundo */
}
::-webkit-scrollbar-thumb:hover {
    background: #8b5cf6; /* Roxo claro ao passar o mouse */
}

/* Para a barra horizontal (caso apareça) */
::-webkit-scrollbar-corner {
    background: #0d0c1d;
}

/* Esconde a barra de rolagem apenas no menu lateral (opcional, se quiser limpar) */
#sidebar::-webkit-scrollbar {
    width: 6px;
}
#sidebar::-webkit-scrollbar-track {
    background: transparent;
}
#sidebar::-webkit-scrollbar-thumb {
    background: rgba(139, 92, 246, 0.3);
    border: none;
}
#sidebar::-webkit-scrollbar-thumb:hover {
    background: rgba(139, 92, 246, 0.6);
}
"""
CSS += CSS_EPOCA

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
        return "❌ Informe o astro observado.", astro, tipo, equipamento, data_hora, local, poluicao, visibilidade, anotacoes
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
            # Retorna mensagem + campos limpos
            return (f"✅ Observação registrada! ID = {d['id']}",
                    "", "planeta", "", "", "", "baixa", "boa", "")
        return f"❌ Erro {r.status_code}: {r.text}", astro, tipo, equipamento, data_hora, local, poluicao, visibilidade, anotacoes
    except requests.RequestException as erro:
        return f"❌ {motivo_falha(erro)}", astro, tipo, equipamento, data_hora, local, poluicao, visibilidade, anotacoes


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
        gr.Warning(motivo_falha(erro))
        return pd.DataFrame({"erro": [motivo_falha(erro)]})


def excluir_observacao(obs_id):
    try:
        obs_id = int(obs_id)
    except (TypeError, ValueError):
        return "❌ Informe um ID numérico.", obs_id
    try:
        r = requests.delete(f"{API_BASE}/api/observacoes/{obs_id}", timeout=TIMEOUT)
        if r.status_code == 204:
            return f"✅ Observação {obs_id} excluída.", ""
        if r.status_code == 404:
            return f"❌ Observação {obs_id} não encontrada.", obs_id
        return f"❌ Erro {r.status_code}: {r.text}", obs_id
    except requests.RequestException as erro:
        return f"❌ {motivo_falha(erro)}", obs_id


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

    # Planetas de exemplo
    planetas = "".join(
        f'<div class="planeta">'
        f'  <img src="{img_url}" class="img-planeta" style="width:{tam}px; height:{tam}px;" alt="{n}">'
        f'  <div class="info"><b>{n}</b><span>{onde}</span></div>'
        f'  <div class="badge b-{vis.lower().replace("é", "e")}">{vis}</div>'
        f'</div>'
        for n, onde, vis, cor, img_url, tam in PLANETAS_EXEMPLO)

    # APOD
    d = _apod()
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

    # --- Buscar últimas observações para o bloco inferior ---
    obs_html = ""
    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        if r.status_code == 200:
            obs = r.json()
            obs.sort(key=lambda o: o.get("data_hora") or "", reverse=True)
            # Pega apenas as 3 mais recentes
            for o in obs[:3]:
                nome = escape(o.get("astro_observado") or "—")
                local = escape(o.get("local") or "—")
                obs_html += (
                    f'<div class="obs-row">'
                    f'  <div class="obs-name">{nome}</div>'
                    f'  <div class="obs-local">{local}</div>'
                    f'</div>'
                )
    except Exception:
        obs_html = '<div class="obs-row"><div class="obs-name">Erro ao carregar</div></div>'
    
    if not obs_html:
        obs_html = '<div class="obs-row"><div class="obs-name" style="color:#a5a3c4">Nenhum registro ainda.</div></div>'

    # Eventos fixos de exemplo (para o bloco de próximos eventos)
    eventos_html = """
        <div class="event-row"><div class="event-date">17 NOV</div><div class="event-desc">Chuva de meteoros Leónidas</div></div>
        <div class="event-row"><div class="event-date">25 NOV</div><div class="event-desc">Conjunção Lua e Júpiter</div></div>
        <div class="event-row"><div class="event-date">04 DEZ</div><div class="event-desc">Lua nova — céu escuro ideal</div></div>
        <div class="event-row"><div class="event-date">14 DEZ</div><div class="event-desc">Pico das Geminídeas</div></div>
    """

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
</div>

<!-- Blocos Inferiores -->
<div class="dash-bottom">
  <div class="bottom-card">
    <div class="bottom-head">
      <h2>Últimas observações</h2>
      <a class="bottom-link" onclick="document.getElementById('nav-diario').click()">Abrir diário →</a>
    </div>
    <div class="obs-list">{obs_html}</div>
  </div>
  <div class="bottom-card">
    <div class="bottom-head">
      <h2>Próximos eventos</h2>
    </div>
    <div class="event-list">{eventos_html}</div>
  </div>
</div>
"""


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
         km=42, minutos=38, mag="21.9", nuvens=12, qualidade="Excelente", serie=[88, 92, 85, 95, 90, 78, 91]),
    dict(id="vale", nome="Vale das Estrelas", cor="amarelo", foto="vale_das_estrelas.png", foco="50% 50%", x=57.4, y=19.5, bortle=5,
         km=35, minutos=31, mag="20.4", nuvens=28, qualidade="Regular", serie=[58, 64, 52, 70, 61, 48, 66]),
    dict(id="pico", nome="Pico da Neblina", cor="azul", foto="pico_da_neblina.png", foco="50% 30%", x=55.6, y=52.5, bortle=3,
         km=18, minutos=22, mag="21.3", nuvens=18, qualidade="Bom", serie=[72, 78, 69, 82, 75, 63, 80]),
    dict(id="morro", nome="Morro do Horizonte", cor="vermelho", foto="morro_do_horizonte.png", foco="50% 52%", x=15.0, y=65.0, bortle=7,
         km=9, minutos=14, mag="18.9", nuvens=45, qualidade="Ruim", serie=[34, 41, 30, 45, 38, 27, 42]),
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


def _grafico(l, hoje):
    """Barras + linha com a qualidade do céu (0-100) dos próximos 7 dias. Valores de exemplo."""
    from datetime import timedelta
    x0, larg, y0, alt = 34, 256, 10, 110
    passo = larg / 7
    base = y0 + alt
    grade = "".join(
        f'<line x1="{x0}" x2="{x0 + larg}" y1="{base - v / 100 * alt:.1f}" y2="{base - v / 100 * alt:.1f}" '
        f'stroke="rgba(255,255,255,.1)" stroke-dasharray="3 3"/>'
        f'<text x="{x0 - 6}" y="{base - v / 100 * alt + 3:.1f}" text-anchor="end" fill="#8a88ad" font-size="8">{v}</text>'
        for v in (0, 25, 50, 75, 100))
    pts = [(x0 + passo * (i + .5), base - v / 100 * alt) for i, v in enumerate(l["serie"])]
    gid = f'g-barra-{l["id"]}'
    barras = "".join(f'<rect x="{x - 4:.1f}" y="{y:.1f}" width="8" height="{base - y:.1f}" rx="4" fill="url(#{gid})"/>'
                     for x, y in pts)
    linha = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{base} {linha} {pts[-1][0]:.1f},{base}"
    maior = l["serie"].index(max(l["serie"]))
    bolas = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4.5 if i == maior else 3}" style="fill:var(--c)"/>'
                    for i, (x, y) in enumerate(pts))
    dias = "".join(f'<text x="{x:.1f}" y="{base + 16}" text-anchor="middle" fill="#8a88ad" font-size="8">'
                   f'{DIAS[(hoje + timedelta(days=i)).weekday()][:3]}</text>' for i, (x, _) in enumerate(pts))
    return (f'<svg class="g-svg" viewBox="0 0 300 150"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#8b5cf6" stop-opacity=".12"/>'
            f'</linearGradient></defs>{grade}{barras}<polygon points="{area}" fill="rgba(139,92,246,.12)"/>'
            f'<polyline points="{linha}" fill="none" stroke-width="2" style="stroke:var(--c)"/>{bolas}{dias}</svg>')


def montar_mapa_html():
    from urllib.parse import quote
    hoje = datetime.now()
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
    rnd2 = random.Random(11)    # camada extra de estrelas, ligada pelo filtro "HD"
    hd = "".join(f'<circle cx="{rnd2.uniform(0, 1000):.0f}" cy="{rnd2.uniform(0, 560):.0f}" r="{rnd2.choice([.4, .6, .8]):.1f}" '
                 f'fill="#fff" opacity="{rnd2.uniform(.3, .8):.2f}"/>' for _ in range(320))
    hd = f'<svg class="estrelas hd-layer" viewBox="0 0 1000 560" preserveAspectRatio="none">{hd}</svg>'
    aneis = "".join(f'<div class="anel-d" style="width:{d}px;height:{d}px"></div>' for d in (190, 400, 640))

    # filtros: o que não combina com os filtros ligados fica apagado no mapa (não some)
    filtros = [("ideal", "Ideais", "ideal", True), ("bortle", "Bortle 1-3", "b13", False),
               ("km", "≤ 50 km", "k50", False), ("hd", "HD", None, False)]
    checks = "".join(f'<input type="checkbox" id="flt-{f}" class="loc-radio"{" checked" if on else ""}>'
                     for f, _, _, on in filtros)
    chips = "".join(f'<label for="flt-{f}">{n}</label>' for f, n, _, _ in filtros)
    regras = ""
    for f, _, cls, _ in filtros:
        regras += f'#flt-{f}:checked ~ .mp-grid label[for=flt-{f}]{{background:#8b5cf6;color:#fff;border-color:#8b5cf6}}'
        if cls:
            regras += f'#flt-{f}:checked ~ .mp-grid .mk:not(.{cls}){{opacity:.25;filter:grayscale(.7)}}'
    regras += '#flt-hd:checked ~ .mp-grid .hd-layer{display:block}'

    radios = "".join(f'<input type="radio" name="loc" id="loc-{l["id"]}" class="loc-radio"'
                     f'{" checked" if i == 0 else ""}>' for i, l in enumerate(LOCAIS_EXEMPLO))
    for l in LOCAIS_EXEMPLO:
        i = l["id"]
        regras += (f'#loc-{i}:checked ~ .mp-grid .card-{i},#loc-{i}:checked ~ .mp-grid .graf-{i}{{display:block}}'
                   f'#loc-{i}:checked ~ .mp-grid .rota-{i}{{display:inline-block}}'
                   f'#loc-{i}:checked ~ .mp-grid .mk-{i} .ring{{transform:translate(-50%,-50%) scale(1.2);box-shadow:0 0 18px var(--c)}}'
                   f'#loc-{i}:checked ~ .mp-grid .mk-{i} .mk-tag{{display:inline-block}}')

    marcadores = "".join(
        f'<label for="loc-{l["id"]}" class="mk mk-{l["id"]} c-{l["cor"]}'
        f'{" ideal" if l["qualidade"] in ("Excelente", "Bom") else ""}{" b13" if l["bortle"] <= 3 else ""}'
        f'{" k50" if l["km"] <= 50 else ""}" style="left:{l["x"]}%;top:{l["y"]}%">'
        f'<span class="glow"></span><span class="ring"></span><span class="core"></span>'
        f'<span class="mk-nome">{escape(l["nome"])}</span><span class="mk-tag">Bortle {l["bortle"]}</span></label>'
        for l in LOCAIS_EXEMPLO)
    link = lambda l: f'https://www.google.com/maps/search/?api=1&query={quote(l["nome"])}'
    rotas = "".join(f'<a class="rota-btn rota-{l["id"]}" target="_blank" href="{link(l)}">Rota</a>' for l in LOCAIS_EXEMPLO)

    cards = "".join(
        f'<div class="mp-card card-{l["id"]} c-{l["cor"]}">{_cabecalho_popup(l)}'
        f'<div class="p-body"><div class="p-head"><b>{escape(l["nome"])}</b>'
        f'<span class="bortle">Bortle {l["bortle"]}</span></div>'
        f'<div class="p-sub">{l["km"]} km de você · {l["minutos"]} min de carro</div>'
        f'<div class="p-stats"><div><b>{l["mag"]}</b><span>mag/arcsec²</span></div>'
        f'<div><b>{l["nuvens"]}%</b><span>nuvens hoje</span></div>'
        f'<div><b>{l["qualidade"]}</b><span>qualidade</span></div></div>'
        f'<div class="p-btns"><a class="p-plan" onclick="document.getElementById(\'nav-diario\').click()">'
        f'Planejar sessão</a><a class="p-rota" target="_blank" href="{link(l)}">Rota</a></div></div></div>'
        for l in LOCAIS_EXEMPLO)
    graficos = "".join(
        f'<div class="mp-card mp-graf graf-{l["id"]} c-{l["cor"]}"><div class="p-head"><b>{l["qualidade"]} qualidade</b>'
        f'<span class="bortle">Bortle {l["bortle"]}</span></div>'
        f'<div class="p-sub">Previsão do céu · próximos 7 dias (exemplo)</div>{_grafico(l, hoje)}</div>'
        for l in LOCAIS_EXEMPLO)

    faixa = "".join(f'<span class="c-{c}" data-nome="{n}"></span>' for c, n in
                    [("verde", "Excelente"), ("azul", "Bom"), ("amarelo", "Regular"), ("vermelho", "Ruim")])
    bussola = ('<div class="bussola">N<svg width="14" height="14" viewBox="0 0 14 14">'
               '<polygon points="7,1 12,13 7,10 2,13" fill="#fff"/></svg></div>')
    escala = ('<div class="escala"><div class="nums"><span>0</span><span>25</span><span>50 km</span></div>'
              '<div class="barra"></div></div>')

    return (f'<style>{regras}</style><div class="mp-wrap">{radios}{checks}<div class="mp-grid">'
            f'<div class="mapa">{fundo}{hd}{aneis}'
            f'<div class="voce"><div class="halo"></div><div class="ponto"></div><div class="nome">Você</div></div>'
            f'{marcadores}<div class="mp-chips">{chips}</div>{rotas}{bussola}<div class="faixa">{faixa}</div>{escala}</div>'
            f'<div class="mp-lado">{cards}{graficos}</div></div></div>')


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
        gr.Warning(motivo_falha(erro))
        return pd.DataFrame({"erro": [motivo_falha(erro)]})


# ---------------------------------------------------------------------------
# DIÁRIO (aba "Meu diário"): lista + detalhes, tudo com dados reais da API
# ---------------------------------------------------------------------------
TIPO_ROTULO = {"planeta": "Planeta", "estrela": "Estrela", "nebula": "Nebulosa",
               "galaxia": "Galáxia", "lua": "Lua", "outro": "Outro"}
CHIPS = [("todos", "Todos"), ("planeta", "Planetas"), ("estrela", "Estrelas"), ("lua", "Lua"),
         ("nebula", "Nebulosas"), ("galaxia", "Galáxias"), ("outro", "Outros")]

DIARIO_DEFS = """<defs>
<linearGradient id="g-pl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c9824a"/>
<stop offset=".2" stop-color="#f0d9b0"/><stop offset=".38" stop-color="#b86a3a"/><stop offset=".55" stop-color="#f2e2c0"/>
<stop offset=".72" stop-color="#c07a45"/><stop offset=".88" stop-color="#e8c99a"/><stop offset="1" stop-color="#a35d34"/></linearGradient>
<radialGradient id="g-lu" cx=".35" cy=".35" r=".8"><stop offset="0" stop-color="#fff6dc"/><stop offset="1" stop-color="#b9a97f"/></radialGradient>
<radialGradient id="g-n1"><stop offset="0" stop-color="#ff7ad9" stop-opacity=".95"/><stop offset="1" stop-color="#ff7ad9" stop-opacity="0"/></radialGradient>
<radialGradient id="g-n2"><stop offset="0" stop-color="#8b5cf6" stop-opacity=".9"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></radialGradient>
<radialGradient id="g-ga"><stop offset="0" stop-color="#e6fbff"/><stop offset=".35" stop-color="#22d3ee" stop-opacity=".8"/><stop offset="1" stop-color="#2563eb" stop-opacity="0"/></radialGradient>
<radialGradient id="g-es"><stop offset="0" stop-color="#fff"/><stop offset=".3" stop-color="#ffe29a" stop-opacity=".7"/><stop offset="1" stop-color="#ffe29a" stop-opacity="0"/></radialGradient>
<linearGradient id="g-co" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c4b5fd"/><stop offset="1" stop-color="#c4b5fd" stop-opacity="0"/></linearGradient>
</defs>"""

ARTE = {
    "planeta": '<circle cx="60" cy="60" r="44" fill="url(#g-pl)"/>',
    "lua": ('<circle cx="60" cy="60" r="44" fill="url(#g-lu)"/><circle cx="48" cy="50" r="7" fill="#7a6f55" opacity=".35"/>'
            '<circle cx="72" cy="70" r="5" fill="#7a6f55" opacity=".35"/><circle cx="68" cy="44" r="4" fill="#7a6f55" opacity=".3"/>'),
    "nebula": ('<circle cx="52" cy="56" r="46" fill="url(#g-n1)"/><circle cx="76" cy="66" r="36" fill="url(#g-n2)"/>'
               '<circle cx="60" cy="60" r="4" fill="#fff"/>'),
    "galaxia": ('<g transform="rotate(-28 60 60)"><ellipse cx="60" cy="60" rx="54" ry="20" fill="url(#g-ga)"/>'
                '<ellipse cx="60" cy="60" rx="28" ry="9" fill="#e6fbff" opacity=".85"/></g>'),
    "estrela": ('<circle cx="60" cy="60" r="50" fill="url(#g-es)"/>'
                '<path d="M60 12L64 56 108 60 64 64 60 108 56 64 12 60 56 56Z" fill="#fff"/>'),
    "outro": ('<circle cx="84" cy="38" r="11" fill="#c4b5fd"/>'
              '<path d="M76 46L18 102" stroke="url(#g-co)" stroke-width="9" stroke-linecap="round"/>'),
}


def _arte(tipo):
    return f'<svg viewBox="0 0 120 120">{ARTE[tipo]}</svg>'


CABECALHO_DIARIO = ('<div class="diario-head"><h1>Diário de observações</h1>'
                    '<p>Seus registros do céu, organizados em um só lugar.</p></div>')

def carregar_observacao(obs_id):
    """Busca os dados de uma observação e preenche o formulário de edição."""
    try:
        obs_id = int(obs_id)
    except (TypeError, ValueError):
        return [gr.update() for _ in range(8)] + [gr.update(selected="registrar")]
    
    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        r.raise_for_status()
        obs = next((o for o in r.json() if o.get("id") == obs_id), None)
        
        if not obs:
            gr.Warning(f"Observação {obs_id} não encontrada.")
            return [gr.update() for _ in range(8)] + [gr.update(selected="registrar")]
            
        # Retorna os valores para preencher o formulário e muda para a aba de registro
        return (
            obs.get("astro_observado", ""),
            obs.get("tipo_astro", "planeta"),
            obs.get("equipamento", ""),
            obs.get("data_hora", ""),
            obs.get("local", ""),
            obs.get("poluicao_luminosa", "baixa"),
            obs.get("visibilidade", "boa"),
            obs.get("anotacoes", ""),
            gr.update(selected="registrar")
        )
    except (requests.RequestException, ValueError) as erro:
        gr.Warning(f"Erro ao carregar observação: {motivo_falha(erro)}")
        return [gr.update() for _ in range(8)] + [gr.update(selected="registrar")]
    
def montar_diario():
    """HTML do diário: filtros por tipo, lista de registros (timeline) e painel de detalhes."""
    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        r.raise_for_status()
        obs = r.json()
    except (requests.RequestException, ValueError) as erro:
        return (CABECALHO_DIARIO + '<div class="d-vazio"><b>Não foi possível carregar o diário.</b><br>'
                f'{escape(motivo_falha(erro))}<br><br>Na pasta do projeto, rode '
                '<code>docker compose up -d</code> e depois <code>flask --app app run</code>; '
                'em seguida clique em <b>Diário</b> de novo.</div>')
    
    if not obs:
        return CABECALHO_DIARIO + '<div class="d-vazio">Nenhum registro ainda. Clique em <b>Novo registro</b> para começar.</div>'
    
    obs.sort(key=lambda o: o.get("data_hora") or "", reverse=True)

    txt = lambda o, k: escape(str(o.get(k) or "—"))
    
    # Inputs de filtro (radios)
    radios = "".join(f'<input type="radio" name="filtro" id="f-{c}" class="d-radio"{" checked" if c == "todos" else ""}>'
                     for c, _ in CHIPS)
    # Inputs de seleção (radios)
    radios += "".join(f'<input type="radio" name="obs" id="o-{o["id"]}" class="d-radio"{" checked" if i == 0 else ""}>'
                      for i, o in enumerate(obs))
    
    # Regras CSS dinâmicas para os filtros e seleção
    regras = ""
    for c, _ in CHIPS:
        regras += f'#f-{c}:checked ~ .d-grid label[for=f-{c}]{{background:#8b5cf6;color:#fff}}'
        if c != "todos":
            regras += f'#f-{c}:checked ~ .d-grid .timeline-item:not(.t-{c}){{display:none}}'
    chips = "".join(f'<label for="f-{c}" class="chip">{n}</label>' for c, n in CHIPS)

    # Agrupar por mês/ano
    grupos = {}
    for o in obs:
        try:
            dt = datetime.fromisoformat(o.get("data_hora"))
            mes_ano = f"{MESES[dt.month - 1].upper()} {dt.year}"
            # Para ordenação, usamos YYYY-MM
            chave_ordem = f"{dt.year}-{dt.month:02d}"
        except (TypeError, ValueError):
            dt = None
            mes_ano = "DATA NÃO INFORMADA"
            chave_ordem = "0000-00"
            
        if chave_ordem not in grupos:
            grupos[chave_ordem] = {"titulo": mes_ano, "itens": []}
        grupos[chave_ordem]["itens"].append((o, dt))

    itens_html, detalhes = "", ""
    
    for chave in sorted(grupos.keys(), reverse=True):
        grupo = grupos[chave]
        itens_html += f'<div class="timeline-group"><div class="timeline-header">{grupo["titulo"]}</div>'
        
        for o, dt in grupo["itens"]:
            i = o["id"]
            tipo = o.get("tipo_astro") if o.get("tipo_astro") in TIPO_ROTULO else "outro"
            
            # Formatação de datas
            curta = dt.strftime("%d/%m/%Y %H:%M") if dt else "—"
            dia_mes = dt.strftime("%d %b").upper() if dt else "—"
            longa = (f"{DIAS[dt.weekday()]}, {dt.day} de {MESES[dt.month - 1]} de {dt.year} • {dt:%H:%M}"
                     if dt else "Data não informada")
            notas = escape(o.get("anotacoes") or "Sem anotações.").replace("\n", "<br>")
            
            # Regras para exibir o detalhe correspondente
            regras += (f'#o-{i}:checked ~ .d-grid .det-{i}{{display:block}}'
                       f'#o-{i}:checked ~ .d-grid label[for=o-{i}] .d-item{{border-color:#8b5cf6;box-shadow:0 0 0 1px #8b5cf6;background:rgba(139,92,246,.1)}}')
            
            # Item da Timeline
            itens_html += (
                f'<div class="timeline-item t-{tipo}">'
                f'  <div class="tl-dot"></div>'
                f'  <div style="flex:1">'
                f'    <div class="tl-date">{dia_mes}</div>'
                f'    <label for="o-{i}" class="d-item">'
                f'      <span class="ic">{_arte(tipo)}</span>'
                f'      <span style="flex:1"><b>{txt(o, "astro_observado")}</b><small>{txt(o, "local")} • {txt(o, "visibilidade").capitalize()}</small></span>'
                f'      <span class="tag-t">{TIPO_ROTULO[tipo]}</span>'
                f'    </label>'
                f'  </div>'
                f'</div>'
            )
            
            # Detalhe do lado direito
            detalhes += (
                f'<div class="d-det det-{i}">'
                f'  <div class="d-banner">{_arte(tipo)}</div>'
                f'  <div class="d-det-header">'
                f'    <h2>{txt(o, "astro_observado")}</h2>'
                f'    <button class="btn-edit" onclick="window.editObs({i})">✏️ Editar</button>'
                f'  </div>'
                f'  <div class="quando">{longa}</div>'
                f'  <div class="d-tab">'
                f'    <div><span>Tipo</span><b>{TIPO_ROTULO[tipo]}</b></div>'
                f'    <div><span>Local</span><b>{txt(o, "local")}</b></div>'
                f'    <div><span>Equipamento</span><b>{txt(o, "equipamento")}</b></div>'
                f'    <div><span>Poluição luminosa</span><b>{txt(o, "poluicao_luminosa").capitalize()}</b></div>'
                f'    <div><span>Visibilidade</span><b>{txt(o, "visibilidade").capitalize()}</b></div>'
                f'  </div>'
                f'  <div class="d-notas"><small>ANOTAÇÕES</small>{notas}</div>'
                f'</div>'
            )
            
        itens_html += '</div>' # Fecha timeline-group

    return (f'<svg width="0" height="0" style="position:absolute">{DIARIO_DEFS}</svg><style>{regras}</style>'
            f'<div class="d-wrap">{radios}<div class="d-grid"><div class="d-esq">{CABECALHO_DIARIO}<div class="chips">{chips}</div>'
            f'<div class="d-lista">{itens_html}</div></div><div class="d-dir">{detalhes}</div></div></div>')


# ---------------------------------------------------------------------------
# MELHOR ÉPOCA (tela "Melhor época")
# ---------------------------------------------------------------------------
MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
ROSA, CIANO, ROXO, VERDE, LARANJA, AMARELO = "#f783c0", "#3ecbf3", "#9d7bfb", "#3fd69b", "#fb9547", "#f6c453"


def _l(nome, meses, cor, ra=None, dec=None):
    """Uma linha da tabela: meses (1-12) da janela ideal; ra (horas) e dec (graus) só p/ objetos fixos."""
    return dict(nome=nome, meses=meses, cor=cor, ra=ra, dec=dec)


NOTA_PONTO = "O ponto indica o mês atual dentro da janela ideal."
EPOCA = {
    "planeta": dict(rotulo="Planetas", nota=NOTA_PONTO + " Janelas aproximadas para 2026; mudam a cada ano.", linhas=[
        _l("Vênus", [4, 5, 6, 7, 8, 9], AMARELO), _l("Júpiter", [1, 2, 3, 12], ROSA),
        _l("Saturno", [8, 9, 10, 11, 12], ROXO), _l("Marte", [11, 12], LARANJA),
        _l("Urano", [1, 10, 11, 12], CIANO), _l("Netuno", [8, 9, 10], VERDE)]),   # do mais fácil ao mais difícil
    "nebula": dict(rotulo="Nebulosas", nota=NOTA_PONTO, linhas=[
        _l("Órion M42", [1, 2, 3, 11, 12], ROSA, 5.59, -5.39), _l("Lagoa M8", [6, 7, 8, 9], CIANO, 18.06, -24.38),
        _l("Hélice", [9, 10, 11], ROXO, 22.49, -20.84), _l("Andrômeda", [9, 10, 11, 12], VERDE, 0.712, 41.27),
        _l("Trífida M20", [6, 7, 8], LARANJA, 18.04, -23.03), _l("Roseta", [1, 2, 3, 12], AMARELO, 6.56, 4.95)]),
    "galaxia": dict(rotulo="Galáxias", nota=NOTA_PONTO, linhas=[
        _l("Andrômeda M31", [9, 10, 11, 12], VERDE, 0.712, 41.27), _l("Triângulo M33", [10, 11, 12, 1], ROXO, 1.565, 30.66),
        _l("Nuvem Maior (LMC)", [11, 12, 1, 2, 3], ROSA, 5.393, -69.75),
        _l("Nuvem Menor (SMC)", [9, 10, 11, 12], CIANO, 0.878, -72.8),
        _l("Sombreiro M104", [3, 4, 5, 6], AMARELO, 12.666, -11.62), _l("Centaurus A", [4, 5, 6, 7], LARANJA, 13.425, -43.02)]),
    "chuva": dict(rotulo="Chuvas", nota=NOTA_PONTO + " Meses em que acontece o pico de cada chuva.", linhas=[
        _l("Quadrantídeas", [1], ROSA), _l("Líridas", [4], CIANO), _l("Eta Aquáridas", [5], ROXO),
        _l("Perseidas", [7, 8], VERDE), _l("Oriônidas", [10], LARANJA), _l("Leônidas", [11], AMARELO),
        _l("Geminídeas", [12], ROSA)]),
}
# picos das chuvas de meteoros (datas fixas todo ano): mês, dia, nome, meteoros/hora (aprox.)
PICOS = [(1, 3, "Quadrantídeas", 110), (4, 22, "Líridas", 18), (5, 6, "Eta Aquáridas", 50),
         (8, 12, "Perseidas", 100), (10, 21, "Oriônidas", 20), (11, 17, "Leônidas", 15),
         (12, 14, "Geminídeas", 120), (12, 22, "Úrsidas", 10)]


def _culminacao(ra_h, dec_g):
    """Hora local da próxima culminação do objeto e sua altura máxima (graus) em LATITUDE/LONGITUDE."""
    from datetime import timedelta
    agora = datetime.now().astimezone()
    d = agora.timestamp() / 86400 + 2440587.5 - 2451545.0
    lst = (18.697374558 + 24.06570982441908 * d + LONGITUDE / 15) % 24   # tempo sideral local
    quando = agora + timedelta(hours=((ra_h - lst) % 24) * 0.9972696)
    return quando, 90 - abs(LATITUDE - dec_g)


def _proximas_chuvas():
    """Lista (data, nome, meteoros/hora) dos próximos picos, do mais próximo ao mais distante."""
    hoje = datetime.now().astimezone()
    lista = []
    for mes, dia, nome, zhr in PICOS:
        d = hoje.replace(month=mes, day=dia, hour=0, minute=0, second=0, microsecond=0)
        if d.date() < hoje.date():
            d = d.replace(year=d.year + 1)
        lista.append((d, nome, zhr))
    return sorted(lista)


def _card_noite(cat, linhas, mes):
    p, _, ilum, _, _ = fase_lua()
    if ilum <= 25:
        lua = f"Lua em {ilum}%: céu escuro, ótimo para observar."
    elif p < .5:
        lua = f"Lua em {ilum}%: prefira depois que a Lua se pôr."
    else:
        lua = f"Lua em {ilum}%: prefira observar antes de a Lua nascer."

    if cat == "chuva":
        d, nome, zhr = _proximas_chuvas()[0]
        dias = (d.date() - datetime.now().astimezone().date()).days
        quando = "hoje" if dias == 0 else f"em {dias} dia{'s' if dias != 1 else ''}"
        titulo = f"{nome} — pico {quando}"
        info = f"Até ~{zhr} meteoros por hora em boas condições (pico em {d.day:02d} {MESES_ABREV[d.month - 1].upper()})."
    else:
        ativos = [l for l in linhas if mes in l["meses"]]
        if not ativos:
            titulo, info = "Sem janela ideal agora", "Veja os próximos meses na tabela ao lado."
        elif cat == "planeta":
            titulo, info = f"{ativos[0]['nome']} — boa janela", "Está entre as melhores épocas do ano para observar."
        else:
            def chave(l):
                q, alt = _culminacao(l["ra"], l["dec"])
                h = q.hour + q.minute / 60
                return (alt < 30, min(h, 24 - h))        # alto no céu e perto da meia-noite
            melhor = min(ativos, key=chave)
            q, alt = _culminacao(melhor["ra"], melhor["dec"])
            titulo = f"{melhor['nome']} — ótima janela"
            info = f"Culmina às {q:%H:%M} · altura máxima {alt:.0f}°"
    return (f'<div class="me-noite noite-{cat}"><div class="mini2">ESTA NOITE</div>'
            f'<h3>{escape(titulo)}</h3><p>{escape(info)}</p><p>{escape(lua)}</p></div>')


def _eventos(n=4):
    from datetime import timedelta
    hoje = datetime.now().astimezone()
    eventos = [(d, f"Chuva de meteoros {nome}") for d, nome, _ in _proximas_chuvas()]
    jd = hoje.timestamp() / 86400 + 2440587.5
    idade = (jd - 2451550.1) % SINODICO
    for k in range(3):
        eventos.append((hoje + timedelta(days=SINODICO - idade + k * SINODICO), "Lua nova — céu escuro ideal"))
        eventos.append((hoje + timedelta(days=(SINODICO / 2 - idade) % SINODICO + k * SINODICO), "Lua cheia"))
    eventos = sorted(e for e in eventos if e[0].date() >= hoje.date())[:n]
    linhas = "".join(f'<div class="ev"><b>{d.day:02d} {MESES_ABREV[d.month - 1].upper()}</b><span>{escape(txt)}</span></div>'
                     for d, txt in eventos)
    return f'<div class="me-eventos"><h3>Próximos eventos</h3>{linhas}</div>'


def _tabela(cat, dados, mes):
    cab = '<div class="me-linha me-cab"><span></span>' + "".join(
        f'<span class="{"atual" if i == mes else ""}">{m}</span>' for i, m in enumerate(MESES_ABREV, 1)) + "</div>"
    corpo = ""
    for l in dados["linhas"]:
        cel = ""
        for m in range(1, 13):
            ativo = m in l["meses"]
            atual = " atual" if m == mes else ""
            estilo = f' style="background:{l["cor"]}"' if ativo else ""
            ponto = "<i></i>" if ativo and m == mes else ""
            cel += f'<span class="cel{atual}"{estilo}>{ponto}</span>'
        corpo += f'<div class="me-linha"><b>{escape(l["nome"])}</b>{cel}</div>'
    return f'<div class="me-tab tab-{cat}">{cab}{corpo}<div class="me-nota">{dados["nota"]}</div></div>'


def montar_melhor_epoca():
    """HTML da página Melhor época: tabela por categoria, destaque da noite e próximos eventos."""
    mes = datetime.now().month
    radios = "".join(f'<input type="radio" name="cat" id="cat-{c}" class="me-radio"{" checked" if c == "nebula" else ""}>'
                     for c in EPOCA)
    regras = "".join(f'#cat-{c}:checked ~ .me-chips label[for=cat-{c}]{{background:#8b5cf6;color:#fff;border-color:#8b5cf6}}'
                     f'#cat-{c}:checked ~ .me-grid .tab-{c}{{display:block}}'
                     f'#cat-{c}:checked ~ .me-grid .noite-{c}{{display:block}}' for c in EPOCA)
    chips = "".join(f'<label for="cat-{c}">{d["rotulo"]}</label>' for c, d in EPOCA.items())
    tabelas = "".join(_tabela(c, d, mes) for c, d in EPOCA.items())
    noites = "".join(_card_noite(c, d["linhas"], mes) for c, d in EPOCA.items())
    return (f'<style>{regras}</style><div class="diario-head"><h1>Melhor época</h1>'
            f'<p>Quando observar cada astro ao longo do ano</p></div><div class="me-wrap">{radios}'
            f'<div class="me-chips">{chips}</div><div class="me-grid"><div class="me-card">{tabelas}</div>'
            f'<div class="me-dir">{noites}{_eventos()}</div></div></div>')


# ---------------------------------------------------------------------------
# Guarda a página atual (por aba do navegador) para o F5 não voltar à tela de boas-vindas
# ---------------------------------------------------------------------------
SESSION_JS = """
<script>
(function () {
    var PAGINA = {'nav-inicio': 'inicio', 'nav-mapa': 'mapa', 'nav-diario': 'diario', 'nav-epoca': 'epoca',
                  'btn-novo': 'diario', 'btn-comecar': 'inicio', 'hidden-edit-btn': 'diario'};
    var ABA = {'nav-diario': 'diario', 'btn-novo': 'registrar', 'hidden-edit-btn': 'registrar'};
    document.addEventListener('click', function (e) {
        var alvo = e.target.closest('#nav-inicio,#nav-mapa,#nav-diario,#nav-epoca,#btn-novo,#btn-comecar,#hidden-edit-btn');
        if (alvo) {
            sessionStorage.setItem('astrolog_pagina', PAGINA[alvo.id]);
            if (ABA[alvo.id]) sessionStorage.setItem('astrolog_aba', ABA[alvo.id]);
            return;
        }
        var aba = e.target.closest('#diario-tabs button[role="tab"]');
        if (aba) {
            var txt = aba.textContent;
            sessionStorage.setItem('astrolog_aba', txt.indexOf('Registrar') >= 0 ? 'registrar'
                                   : txt.indexOf('Hist') >= 0 ? 'historico' : 'diario');
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target.closest('#busca')) sessionStorage.setItem('astrolog_pagina', 'mapa');
    });
})();
</script>
"""

PAGINAS = ["inicio", "mapa", "diario", "epoca"]


def ir_para(pagina):
    """Mostra uma página e destaca o item correspondente do menu."""
    return ([gr.update(visible=(p == pagina)) for p in PAGINAS]
            + [gr.update(variant="primary" if p == pagina else "secondary") for p in PAGINAS])


def ir_para_diario(aba):
    """Abre a página Diário já na aba pedida ("diario", "registrar" ou "historico")."""
    return ir_para("diario") + [gr.update(selected=aba)]


def restaurar_sessao(pagina, aba):
    """Ao recarregar (F5), volta para a página em que o usuário estava, sem passar pela tela de boas-vindas."""
    if pagina not in PAGINAS:
        return [gr.update() for _ in range(2 + 2 * len(PAGINAS) + 1)]     # primeira visita: fica na tela inicial
    aba = aba if aba in ("diario", "registrar", "historico") else "diario"
    return [gr.update(visible=False), gr.update(visible=True)] + ir_para(pagina) + [gr.update(selected=aba)]


def carregar_dados_da_pagina(pagina):
    """Carrega só os dados da página restaurada: dashboard, locais, diário + histórico, melhor época."""
    nada = gr.update()
    if pagina == "inicio":
        return montar_dashboard(), nada, nada, nada, nada
    if pagina == "mapa":
        return nada, listar_locais(""), nada, nada, nada
    if pagina == "diario":
        return nada, nada, montar_diario(), listar_observacoes(), nada
    if pagina == "epoca":
        return nada, nada, nada, nada, montar_melhor_epoca()
    return nada, nada, nada, nada, nada


# ---------------------------------------------------------------------------
# Layout Gradio: tela inicial + app com 3 abas
# ---------------------------------------------------------------------------
with gr.Blocks(title="AstroLog") as demo:

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
            btn_novo = gr.Button("＋  Novo registro", elem_id="btn-novo", scale=0, min_width=0)

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
                nav_epoca = gr.Button("📅  Melhor época", variant="secondary",
                                      elem_id="nav-epoca", elem_classes="nav-btn")
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
                    with gr.Tabs(selected="diario", elem_id="diario-tabs") as abas_diario:
                        # --- Aba 1: o diário (lista + detalhes) ---
                        with gr.Tab("Meu diário", id="diario"):
                            diario_html = gr.HTML()

                        # --- Aba 2: formulário de registro ---
                        with gr.Tab("Registrar Observação", id="registrar"):
                            gr.HTML('<div class="diario-head"><h1>Registrar observação</h1>'
                                    '<p>Anote o que você viu no céu.</p></div>')
                            with gr.Row():
                                astro = gr.Textbox(label="Astro observado",
                                                   placeholder="Ex.: Júpiter")
                                tipo = gr.Dropdown(TIPOS_ASTRO, label="Tipo de astro",
                                                   value="planeta")
                            equipamento = gr.Textbox(label="Equipamento",
                                                     placeholder="Ex.: Telescópio Refletor 114mm")
                            data_hora = gr.Textbox(label="Data e hora (ISO 8601)",
                                                   placeholder="2025-03-10T22:30:00",
                                                   elem_id="data-hora")
                            local = gr.Textbox(label="Local", placeholder="Cidade ou coordenadas")
                            with gr.Row():
                                poluicao = gr.Dropdown(POLUICAO, label="Poluição luminosa",
                                                       value="baixa")
                                visibilidade = gr.Dropdown(VISIBILIDADE, label="Visibilidade",
                                                           value="boa")
                            anotacoes = gr.Textbox(label="Anotações", lines=3)
                            btn_salvar = gr.Button("Salvar", variant="primary")
                            msg_salvar = gr.Markdown()

                        # --- Aba 3: histórico em tabela ---
                        with gr.Tab("Histórico de Observações", id="historico"):
                            gr.HTML('<div class="diario-head"><h1>Histórico de observações</h1>'
                                    '<p>Todos os seus registros em formato de tabela.</p></div>')
                            btn_listar = gr.Button("Listar", variant="primary")
                            df_hist = gr.Dataframe(label="Observações registradas")
                            with gr.Row():
                                id_excluir = gr.Textbox(label="ID para excluir", scale=1,
                                                        elem_id="id-excluir")
                                btn_excluir = gr.Button("Excluir", variant="stop", scale=1)
                            msg_excluir = gr.Markdown()

                    # --- Componentes ocultos e evento do botão "Editar" ---
                    # (agora todos os campos já existem)
                    with gr.Row(visible=False):
                        hidden_edit_id = gr.Textbox(elem_id="hidden-edit-id")
                        hidden_edit_btn = gr.Button(elem_id="hidden-edit-btn")

                    hidden_edit_btn.click(
                        carregar_observacao,
                        inputs=hidden_edit_id,
                        outputs=[astro, tipo, equipamento, data_hora, local,
                                 poluicao, visibilidade, anotacoes, abas_diario]
                    )

                    # Eventos do diário: salvar/excluir atualizam a lista e a tabela
                    btn_salvar.click(
                        registrar_observacao,
                        inputs=[astro, tipo, equipamento, data_hora, local,
                                poluicao, visibilidade, anotacoes],
                        outputs=[msg_salvar, astro, tipo, equipamento, data_hora, local, poluicao, visibilidade, anotacoes],
                    ).then(montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)

                    btn_listar.click(listar_observacoes, inputs=None, outputs=df_hist)

                    btn_excluir.click(excluir_observacao, inputs=id_excluir, outputs=[msg_excluir, id_excluir]
                    ).then(montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)

                with gr.Column(visible=False) as pg_epoca:
                    epoca_html = gr.HTML()

    # ---------- Menu lateral e busca ----------
    saidas_nav = [pg_inicio, pg_mapa, pg_diario, pg_epoca,
                  nav_inicio, nav_mapa, nav_diario, nav_epoca]
    nav_inicio.click(lambda: ir_para("inicio"), None, saidas_nav).then(
        montar_dashboard, None, dash_html)
    nav_mapa.click(lambda: ir_para("mapa"), None, saidas_nav).then(
        listar_locais, busca, df_locais)
    saidas_diario = saidas_nav + [abas_diario]
    nav_diario.click(lambda: ir_para_diario("diario"), None, saidas_diario).then(
        montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)
    nav_epoca.click(lambda: ir_para("epoca"), None, saidas_nav).then(
        montar_melhor_epoca, None, epoca_html)
    btn_novo.click(lambda: ir_para_diario("registrar"), None, saidas_diario)
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

    # ---------- F5 / Ctrl+F5: volta para a página em que o usuário estava ----------
    salva_pagina = gr.Textbox(visible=False)   # só servem para receber o que o JS lê do navegador
    salva_aba = gr.Textbox(visible=False)
    demo.load(
        restaurar_sessao, inputs=[salva_pagina, salva_aba],
        outputs=[tela_inicio, tela_app] + saidas_nav + [abas_diario],
        js="() => [sessionStorage.getItem('astrolog_pagina') || '', sessionStorage.getItem('astrolog_aba') || '']",
    ).then(
        carregar_dados_da_pagina, inputs=[salva_pagina],
        outputs=[dash_html, df_locais, diario_html, df_hist, epoca_html],
        js="() => [sessionStorage.getItem('astrolog_pagina') || '']",
    )


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.abspath(os.path.join(current_dir, "..", "img"))
    demo.launch(css=CSS, allowed_paths=[img_path], head=INPUT_MASK_JS + EDIT_JS + SESSION_JS)