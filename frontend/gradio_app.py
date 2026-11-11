"""Interface Gradio consumindo a AstroLog API.

Rodar (com a API já em execução em http://127.0.0.1:5000):
    python frontend/gradio_app.py
"""
import io

import gradio as gr
import pandas as pd
import requests
from PIL import Image

API_BASE = "http://127.0.0.1:5000"
TIMEOUT = 15

TIPOS_ASTRO = ["planeta", "estrela", "nebula", "galaxia", "lua", "outro"]
POLUICAO = ["baixa", "media", "alta"]
VISIBILIDADE = ["excelente", "boa", "regular", "ruim"]


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
# Layout Gradio com 3 abas
# ---------------------------------------------------------------------------
with gr.Blocks(title="AstroLog") as demo:
    gr.Markdown("# 🔭 AstroLog — Diário de Observação Astronômica")

    with gr.Tab("Dashboard de Hoje"):
        btn_nasa = gr.Button("Carregar dados da NASA", variant="primary")
        texto_nasa = gr.Markdown()
        imagem_nasa = gr.Image(label="Imagem do dia", height=400)
        btn_nasa.click(carregar_dashboard, inputs=None,
                       outputs=[texto_nasa, imagem_nasa])
        demo.load(carregar_dashboard, inputs=None,
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

        demo.load(listar_observacoes, inputs=None, outputs=df_hist)


if __name__ == "__main__":
    demo.launch()