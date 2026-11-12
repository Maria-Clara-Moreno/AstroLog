"""Interface Gradio consumindo a AstroLog API.

Rodar (com a API já em execução em http://127.0.0.1:5000):
    python frontend/gradio_app.py
"""
import io
import os 
import base64

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

IMG_BASE64 = get_base64_image()

# ---------------------------------------------------------------------------
# CSS LIMPO E AJUSTADO PARA TELA CHEIA E POSICIONAMENTO
# ---------------------------------------------------------------------------
CSS = f"""
/* --- RESET AGRESSIVO --- */
html, body, .gradio-container, .main, .wrap {{
    margin: 0 !important;
    padding: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    max-width: 100vw !important;
    max-height: 100vh !important;
    overflow: hidden !important;
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
    position: absolute !important;
    top: 0;
    left: 0;
    display: flex !important;
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
# Layout Gradio: tela inicial + app com 3 abas
# ---------------------------------------------------------------------------
with gr.Blocks(title="AstroLog", css=CSS) as demo:

    # ---------- TELA INICIAL (visível ao abrir) ----------
    with gr.Column(visible=True, elem_id="tela-inicio") as tela_inicio:
        gr.HTML(HTML_HERO)
        btn_comecar = gr.Button("Comece agora", elem_id="btn-comecar")

    # ---------- APP PRINCIPAL (escondido até clicar no botão) ----------
    with gr.Column(visible=False) as tela_app:
        gr.Markdown("# 🔭 AstroLog — Diário de Observação Astronômica")

        with gr.Tab("Dashboard de Hoje"):
            btn_nasa = gr.Button("Carregar dados da NASA", variant="primary")
            texto_nasa = gr.Markdown()
            imagem_nasa = gr.Image(label="Imagem do dia", height=400)
            btn_nasa.click(carregar_dashboard, inputs=None,
                           outputs=[texto_nasa, imagem_nasa])

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

    # ---------- Clique em "Comece agora": troca de tela e carrega o dashboard ----------
    btn_comecar.click(
        entrar_no_app, inputs=None, outputs=[tela_inicio, tela_app]
    ).then(
        carregar_dashboard, inputs=None, outputs=[texto_nasa, imagem_nasa]
    ).then(
        listar_observacoes, inputs=None, outputs=df_hist
    )


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.abspath(os.path.join(current_dir, "..", "img"))
    demo.launch(allowed_paths=[img_path])