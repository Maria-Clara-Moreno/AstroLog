"""Interface Gradio consumindo a AstroLog API.

Rodar (com a API já em execução em http://127.0.0.1:5000):
    python frontend/gradio_app.py
"""
import base64
import io
import json
import math
import random
import os
import re
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
    
    // 2. Data e Hora (Formato dd/mm/aaaa 00:00)
    if (e.target.closest('#data-hora')) {
        let val = e.target.value;
        
        // Remove tudo que não for número, barra, espaço ou dois pontos
        val = val.replace(/[^0-9\\/\\:\\s]/g, '');
        
        // Remove barras e dois pontos antigos para aplicar a máscara limpa
        let num = val.replace(/[^0-9]/g, '');
        
        let formatado = '';
        if (num.length > 0) {
            formatado += num.substring(0, 2);
        }
        if (num.length > 2) {
            formatado += '/' + num.substring(2, 4);
        }
        if (num.length > 4) {
            formatado += '/' + num.substring(4, 8);
        }
        if (num.length > 8) {
            formatado += ' ' + num.substring(8, 10);
        }
        if (num.length > 10) {
            formatado += ':' + num.substring(10, 12);
        }
        
        // Atualiza o valor no campo apenas se for diferente
        if (e.target.value !== formatado) {
            e.target.value = formatado;
        }
    }
}, true); // O 'true' ativa o modo de captura, funcionando mesmo se o Gradio recriar o campo
</script>
"""

EDIT_JS = """
<script>
window.editObs = function(obsId) {
    const btn = document.getElementById("hidden-edit-btn");
    if (btn) {
        const input = document.querySelector('#hidden-edit-id textarea, #hidden-edit-id input');
        if (input) {
            input.value = obsId;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            btn.click();
        }
    }
};

window.irParaPremium = function() {
    const btn = document.getElementById("nav-premium");
    if (btn) {
        btn.click();
    } else {
        console.warn("Botão nav-premium não encontrado no DOM.");
    }
};
</script>
"""

AUTH_JS = """
<script>
(function () {
    // ------------------------------------------------------------------
    // Utilitários
    // ------------------------------------------------------------------
    // Um elem_id do Gradio pode cair no wrapper (div) e não no <button>.
    // Este helper clica no botão de verdade em qualquer um dos casos.
    function clicarComponente(id) {
        var el = document.getElementById(id);
        if (!el) return false;
        if (el.tagName === 'BUTTON') { el.click(); return true; }
        var btn = el.querySelector('button');
        if (btn) { btn.click(); return true; }
        el.click();
        return false;
    }
    window.astrologClicar = clicarComponente;

    function setValorGradio(seletor, valor) {
        var raiz = document.querySelector(seletor);
        if (!raiz) return false;
        var input = (raiz.tagName === 'TEXTAREA' || raiz.tagName === 'INPUT')
            ? raiz
            : raiz.querySelector('textarea, input');
        if (!input) return false;
        var proto = input.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(input, valor);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }

    function emailValido(email) {
        return /^[^@\\s]+@[^@\\s]+\\.[A-Za-z]{2,}$/.test(email);
    }

    // Mensagens de erro somem sozinhas depois de alguns segundos
    var TEMPO_ERRO_MS = 5000;
    var timersErro = {};

    function agendarSumico(chave, acao) {
        if (timersErro[chave]) clearTimeout(timersErro[chave]);
        timersErro[chave] = setTimeout(function () {
            delete timersErro[chave];
            acao();
        }, TEMPO_ERRO_MS);
    }

    function cancelarSumico(chave) {
        if (timersErro[chave]) { clearTimeout(timersErro[chave]); delete timersErro[chave]; }
    }

    function mostrarErro(id, msg) {
        var erro = document.getElementById('erro-' + id);
        if (erro) { erro.textContent = msg; erro.classList.add('show'); }
        var input = document.getElementById(id);
        if (input) input.classList.add('invalido');
        agendarSumico('erro-' + id, function () { limparErro(id); });
    }

    function limparErro(id) {
        cancelarSumico('erro-' + id);
        var erro = document.getElementById('erro-' + id);
        if (erro) { erro.textContent = ''; erro.classList.remove('show'); }
        var input = document.getElementById(id);
        if (input) input.classList.remove('invalido');
    }

    function mostrarAlerta(prefixo, msg, tipo) {
        var alerta = document.getElementById('alerta-' + prefixo);
        if (!alerta) return;
        cancelarSumico('alerta-' + prefixo);
        alerta.textContent = msg || '';
        alerta.classList.toggle('show', !!msg);
        alerta.classList.toggle('sucesso', tipo === 'sucesso');
        // Só os avisos de erro somem sozinhos; o de sucesso fica
        if (msg && tipo !== 'sucesso') {
            agendarSumico('alerta-' + prefixo, function () { mostrarAlerta(prefixo, ''); });
        }
    }

    function limparFormulario(prefixo) {
        ['nome', 'email', 'senha'].forEach(function (campo) {
            limparErro(prefixo + '-' + campo);
        });
        mostrarAlerta(prefixo, '');
    }

    function focarPrimeiroInvalido(prefixo) {
        var invalido = document.querySelector('#' + prefixo + '-painel input.invalido');
        if (invalido) invalido.focus();
    }

    document.addEventListener('input', function (e) {
        var id = e.target && e.target.id;
        if (id) limparErro(id);
    }, true);

    // ------------------------------------------------------------------
    // Cadastro
    // ------------------------------------------------------------------
    window.realizarCadastro = function () {
        limparFormulario('cad');

        var nome = (document.getElementById('cad-nome').value || '').trim();
        var email = (document.getElementById('cad-email').value || '').trim();
        var senha = document.getElementById('cad-senha').value || '';
        var ok = true;

        if (!nome) {
            mostrarErro('cad-nome', 'Informe o seu nome.');
            ok = false;
        } else if (nome.length < 2) {
            mostrarErro('cad-nome', 'O nome deve ter pelo menos 2 caracteres.');
            ok = false;
        }

        if (!email) {
            mostrarErro('cad-email', 'Informe o seu e-mail.');
            ok = false;
        } else if (!emailValido(email)) {
            mostrarErro('cad-email', 'Informe um e-mail válido (ex.: voce@email.com).');
            ok = false;
        }

        if (!senha) {
            mostrarErro('cad-senha', 'Informe uma senha.');
            ok = false;
        } else if (senha.length < 6) {
            mostrarErro('cad-senha', 'A senha deve ter pelo menos 6 caracteres.');
            ok = false;
        }

        if (!ok) {
            focarPrimeiroInvalido('cad');
            return false;
        }

        // Envia os valores para os componentes ocultos do Gradio e dispara o backend
        setValorGradio('#hidden-cad-nome', nome);
        setValorGradio('#hidden-cad-email', email);
        setValorGradio('#hidden-cad-senha', senha);
        clicarComponente('hidden-cad-btn');
        return false;
    };

    // ------------------------------------------------------------------
    // Login
    // ------------------------------------------------------------------
    window.realizarLogin = function () {
        limparFormulario('login');

        var email = (document.getElementById('login-email').value || '').trim();
        var senha = document.getElementById('login-senha').value || '';
        var ok = true;

        if (!email) {
            mostrarErro('login-email', 'Informe o seu e-mail.');
            ok = false;
        } else if (!emailValido(email)) {
            mostrarErro('login-email', 'Informe um e-mail válido.');
            ok = false;
        }

        if (!senha) {
            mostrarErro('login-senha', 'Informe a sua senha.');
            ok = false;
        }

        if (!ok) {
            focarPrimeiroInvalido('login');
            return false;
        }

        setValorGradio('#hidden-login-email', email);
        setValorGradio('#hidden-login-senha', senha);
        clicarComponente('hidden-login-btn');
        return false;
    };

    window.avisoGoogle = function (prefixo) {
        mostrarAlerta(prefixo, 'Login com Google ainda não está disponível. Use e-mail e senha.');
    };

    // Mostrar / ocultar a senha (olho)
    window.astrologAlternarSenha = function (idCampo, botao) {
        var campo = document.getElementById(idCampo);
        if (!campo) return;
        var estavaOculta = campo.type === 'password';
        campo.type = estavaOculta ? 'text' : 'password';
        if (botao) {
            var rotulo = estavaOculta ? 'Ocultar senha' : 'Mostrar senha';
            botao.setAttribute('aria-label', rotulo);
            botao.setAttribute('title', rotulo);
        }
        campo.focus();
    };

    // ------------------------------------------------------------------
    // Retorno do backend (erros de validação / credenciais)
    // ------------------------------------------------------------------
    function aplicarErros(prefixo, payload) {
        if (!payload) return;
        var erros;
        try { erros = JSON.parse(payload); } catch (e) { return; }

        limparFormulario(prefixo);

        if (typeof erros === 'string') {
            mostrarAlerta(prefixo, erros);
            return;
        }
        if (erros.geral) mostrarAlerta(prefixo, erros.geral);
        ['nome', 'email', 'senha'].forEach(function (campo) {
            if (erros[campo]) mostrarErro(prefixo + '-' + campo, erros[campo]);
        });
        focarPrimeiroInvalido(prefixo);
    }

    window.astrologErrosCadastro = function (payload) { aplicarErros('cad', payload); };
    window.astrologErrosLogin = function (payload) { aplicarErros('login', payload); };

    // Depois de criar a conta: limpa o cadastro, leva para o login e preenche o e-mail
    window.astrologIrParaLogin = function (email) {
        ['cad-nome', 'cad-senha', 'cad-email'].forEach(function (id) {
            var campo = document.getElementById(id);
            if (campo) campo.value = '';
        });
        limparFormulario('cad');
        limparFormulario('login');

        var loginEmail = document.getElementById('login-email');
        var loginSenha = document.getElementById('login-senha');
        if (loginEmail) loginEmail.value = email || '';
        if (loginSenha) loginSenha.value = '';

        setValorGradio('#hidden-login-email', email || '');
        setValorGradio('#hidden-login-senha', '');

        if (loginSenha) loginSenha.focus();
    };

    // ------------------------------------------------------------------
    // Sessão (token guardado no navegador)
    // ------------------------------------------------------------------
    window.astrologSalvarSessao = function (token, nome, email) {
        if (!token) return;
        localStorage.setItem('astrolog_token', token);
        localStorage.setItem('astrolog_nome', nome || '');
        localStorage.setItem('astrolog_email', email || '');
        sessionStorage.setItem('astrolog_pagina', 'inicio');
    };

    window.astrologLimparSessao = function () {
        localStorage.removeItem('astrolog_token');
        localStorage.removeItem('astrolog_nome');
        localStorage.removeItem('astrolog_email');
        sessionStorage.removeItem('astrolog_pagina');
        sessionStorage.removeItem('astrolog_aba');
    };

    // ------------------------------------------------------------------
    // Menu do perfil (avatar na navbar)
    // ------------------------------------------------------------------
    window.astrologPerfilFechar = function () {
        var menu = document.getElementById('perfil-menu');
        var btn = document.getElementById('perfil-btn');
        if (menu) menu.classList.remove('aberto');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    };

    window.astrologPerfilToggle = function (evento) {
        if (evento) evento.stopPropagation();
        var menu = document.getElementById('perfil-menu');
        var btn = document.getElementById('perfil-btn');
        if (!menu) return;
        var abrir = !menu.classList.contains('aberto');
        menu.classList.toggle('aberto', abrir);
        if (btn) btn.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        if (abrir) {
            var nome = localStorage.getItem('astrolog_nome') || 'Observador';
            var email = localStorage.getItem('astrolog_email') || '';
            var elNome = document.getElementById('perfil-nome');
            var elEmail = document.getElementById('perfil-email');
            if (elNome) elNome.textContent = nome;
            if (elEmail) elEmail.textContent = email;
            var primeiro = nome.trim().split(' ')[0] || 'O';
            var inicial = document.getElementById('perfil-inicial');
            if (inicial) inicial.textContent = email ? '' : primeiro.charAt(0).toUpperCase();
        }
    };

    window.astrologPerfilSair = function () {
        window.astrologPerfilFechar();
        window.astrologClicar('btn-sair');
    };

    document.addEventListener('click', function (e) {
        if (!e.target.closest('#topbar-perfil')) window.astrologPerfilFechar();
    });

    // ------------------------------------------------------------------
    // Aviso "em breve" (recursos ainda sem backend)
    // ------------------------------------------------------------------
    window.astrologEmBreve = function (recurso) {
        var anterior = document.getElementById('astro-em-breve');
        if (anterior) anterior.remove();
        clearTimeout(window.__astroEmBreveTimer);

        var aviso = document.createElement('div');
        aviso.id = 'astro-em-breve';
        aviso.className = 'em-breve-toast';
        aviso.setAttribute('role', 'status');
        aviso.setAttribute('aria-live', 'polite');
        aviso.innerHTML = '<span class="em-breve-estrela"><svg viewBox="0 0 24 24" aria-hidden="true">' +
            '<path d="M12 3.2l1.9 4.7 4.7 1.9-4.7 1.9L12 16.4l-1.9-4.7-4.7-1.9 4.7-1.9z"/>' +
            '<path d="M18.6 15.2l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg></span>' +
            '<div class="em-breve-txt"><b>' + (recurso || 'Este recurso') + '</b>' +
            '<span>Em breve</span></div>';

        document.body.appendChild(aviso);
        requestAnimationFrame(function () { aviso.classList.add('mostrar'); });

        window.__astroEmBreveTimer = setTimeout(function () {
            aviso.classList.remove('mostrar');
            setTimeout(function () { aviso.remove(); }, 260);
        }, 2600);
    };

    // ------------------------------------------------------------------
    // Excluir conta (confirmação)
    // ------------------------------------------------------------------
    window.astrologExcluirErro = function (msg) {
        var el = document.getElementById('pf-excluir-erro');
        if (!el) return;
        el.textContent = msg || '';
        el.classList.toggle('show', !!msg);
    };

    window.astrologAbrirExcluirConta = function () {
        var modal = document.getElementById('pf-excluir-modal');
        if (!modal) return;
        window.astrologExcluirErro('');
        modal.classList.add('aberto');
    };

    window.astrologFecharExcluirConta = function () {
        var modal = document.getElementById('pf-excluir-modal');
        if (modal) modal.classList.remove('aberto');
    };

    window.astrologConfirmarExcluirConta = function () {
        clicarComponente('btn-excluir-conta');
    };

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            window.astrologPerfilFechar();
            window.astrologFecharExcluirConta();
        }
    });
})();
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
            ext = "png" if nome_arquivo.endswith(".png") else "jpeg"
            return f"data:image/{ext};base64,{encoded_string}"
    except FileNotFoundError:
        return ""

IMG_BASE64 = get_base64_image()

# ---------------------------------------------------------------------------
# CSS LIMPO E AJUSTADO PARA TELA CHEIA E POSICIONAMENTO CENTRALIZADO
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ícones vetoriais (substituem os emojis em todas as telas)
# ---------------------------------------------------------------------------
ICONE_LUA = ('<svg class="ico-svg" viewBox="0 0 24 24" aria-hidden="true">'
             '<path d="M20.6 14.4A8.9 8.9 0 0 1 9.6 3.4 8.9 8.9 0 1 0 20.6 14.4Z" fill="currentColor"/></svg>')

ICONE_TELESCOPIO = ('<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                    '<path d="M3.2 13.7 15.9 7.4l2.5 5.3-12.7 6.3z"/>'
                    '<path d="m8.2 15.6 1.9 4.2"/><path d="m16.1 9.4 1.1-2.6 2.9 1.3-1 2.5"/>'
                    '<path d="M11.6 6.1 12.8 3.2"/></svg>')

ICONE_PIN = ('<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M12 21s-6.5-5.3-6.5-10.2A6.5 6.5 0 0 1 18.5 10.8C18.5 15.7 12 21 12 21Z"/>'
             '<circle cx="12" cy="10.6" r="2.4"/></svg>')

ICONE_DIARIO = ('<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v18H6.5A1.5 1.5 0 0 1 5 19.5z"/>'
                '<path d="M5 17h14"/><path d="M9 7h6"/></svg>')

ICONE_LAPIS = ('<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
               '<path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17z"/><path d="m13.5 6.5 3 3"/></svg>')

ICONE_CHECK = ('<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
               '<path d="m4.5 12.5 5 5 10-11"/></svg>')

ICONE_NUVEM = ('<svg class="ico-clima" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
               '<path d="M7 18.5h9.5a3.5 3.5 0 0 0 .4-7 5.2 5.2 0 0 0-10-1.4A4 4 0 0 0 7 18.5Z"/></svg>')

ICONE_TERMOMETRO = ('<svg class="ico-clima" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                    '<path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0Z"/><path d="M12 9v6"/></svg>')

ICONE_GOTA = ('<svg class="ico-clima" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
              'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<path d="M12 3.5s5.5 5.6 5.5 9.6a5.5 5.5 0 0 1-11 0C6.5 9.1 12 3.5 12 3.5Z"/></svg>')

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

/* Rodapé padrão do Gradio (com emojis) fica oculto para manter o tema do app */
footer {{ display: none !important; }}

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
    justify-content: space-between !important;
}}

#tela-inicio > div, #tela-inicio .block, #tela-inicio .form {{
    background: transparent !important; 
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
}}

.hero {{ 
    display: grid; 
    grid-template-columns: 1.2fr 1fr;
    grid-template-rows: auto 1fr; 
    column-gap: 48px; 
    min-height: 100%; 
    align-items: center; 
}}
.topo {{ grid-column: 1; grid-row: 1; }}
.lua-area {{ grid-column: 1; grid-row: 2; }} 

.painel {{ 
    grid-area: 2 / 2 / 3;
    place-self: center;
    width: 100%;
    max-width: 460px;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
    padding: 28px 36px;
    border-radius: 24px;
    background: rgba(11, 10, 23, 0.55);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(139, 92, 246, 0.2);
    box-shadow: 0 10px 30px rgba(0,0,0,0.4);
}}

.marca {{ display: flex; align-items: center; gap: 8px; color: #e8e6f5;
         font-weight: 600; font-size: 1.1rem; }}
.ico-svg {{ width: 22px; height: 22px; display: block; flex: none; }}
.marca .ico-svg {{ width: 20px; height: 20px; color: #c4b5fd; }}
.marca .ico-svg path {{ fill: #c4b5fd !important; }}
.icone .ico-svg {{ width: 22px; height: 22px; }}
.i1 .ico-svg {{ color: #c4b5fd; }}
.i2 .ico-svg {{ color: #5eead4; }}
.i3 .ico-svg {{ color: #fcd34d; }}
.titulo-bemvindo {{ font-size: 4.2rem; font-weight: 800; color: #8b5cf6;
                   line-height: 1.1; margin: 8px 0 6px 0; }}
.slogan {{ color: #cfcde6; font-size: .7rem; letter-spacing: .15em;
          line-height: 1.8; text-transform: uppercase; }}

.tag {{ color: #8b5cf6; font-size: .7rem; letter-spacing: .15em; font-weight: 600; }}
.chamada {{ color: #fff; font-size: 2.2rem; font-weight: 700; margin: 6px 0 10px;
           line-height: 1.15; }}
.sub {{ color: #a5a3c4; font-size: .9rem; margin-bottom: 18px; }}
.item {{ display: flex; gap: 12px; align-items: center; margin: 12px 0; }}
.icone {{ width: 42px; height: 42px; border-radius: 12px; display: flex;
         align-items: center; justify-content: center; font-size: 1.2rem;
         flex-shrink: 0; }}
.i1 {{ background: #2a2250; }} .i2 {{ background: #123a33; }} .i3 {{ background: #3a2f12; }}
.item b {{ color: #fff; font-size: .9rem; display: block; }}
.item span {{ color: #a5a3c4; font-size: .75rem; }}

.botoes-inicio {{
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 20px;
    align-items: center;
}}

.btn-hero-primario {{ 
    background: #8b5cf6 !important; 
    color: #fff !important;
    border: none !important; 
    border-radius: 999px !important;
    font-size: 0.95rem !important; 
    font-weight: 600 !important;
    width: 100% !important; 
    max-width: 340px !important; 
    padding: 12px 0 !important; 
    cursor: pointer;
    transition: background 0.2s ease;
}}
.btn-hero-primario:hover {{ 
    background: #7c4de8 !important; 
}}

.btn-hero-secundario {{ 
    background: rgba(11, 10, 23, 0.45) !important; 
    color: #fff !important;
    border: 1.5px solid rgba(255, 255, 255, 0.45) !important; 
    border-radius: 999px !important;
    font-size: 0.95rem !important; 
    font-weight: 600 !important;
    width: 100% !important; 
    max-width: 340px !important; 
    padding: 11px 0 !important; 
    cursor: pointer;
    transition: all 0.2s ease;
}}
.btn-hero-secundario:hover {{ 
    background: rgba(255, 255, 255, 0.1) !important;
    border-color: #fff !important;
}}

@media (max-width: 900px) {{
  .hero {{ grid-template-columns: 1fr; grid-template-rows: auto auto; }}
  .lua-area {{ display: none; }}
  .painel {{ grid-column: 1; grid-row: 2; justify-self: center; }}
}}
"""

CSS_CADASTRO = f"""
#tela-cadastro {{ 
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
    justify-content: space-between !important;
}}

#tela-cadastro:not(.hide):not(.hidden):not([hidden]) {{ display: flex !important; }}
#tela-cadastro.hide, #tela-cadastro.hidden, #tela-cadastro[hidden] {{ display: none !important; }}

#tela-cadastro > div, #tela-cadastro .block, #tela-cadastro .form {{
    background: transparent !important; 
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
}}

.cad-painel {{
    grid-area: 2 / 2 / 3;
    place-self: center;
    width: 100%;
    max-width: 410px;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
    padding: 26px 30px 22px;
    border-radius: 22px;
    background: rgba(11, 10, 23, 0.8);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.22);
    box-shadow: 0 14px 36px rgba(0, 0, 0, 0.45);
}}

.cad-campo {{
    margin-bottom: 14px;
}}

.cad-campo label {{
    display: block;
    color: #cfcde6;
    font-size: 0.78rem;
    font-weight: 500;
    margin-bottom: 5px;
}}

.cad-campo input {{
    width: 100%;
    box-sizing: border-box;
    background: #17182b;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 11px 16px;
    color: #fff;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.2s;
}}

.cad-campo input::placeholder {{
    color: #6f6d92;
}}

.cad-campo input:focus {{
    border-color: #8b5cf6;
    outline: none !important;
    box-shadow: none !important;
}}

/* --- Olho para mostrar/ocultar a senha --- */
.cad-senha-wrap {{
    position: relative;
}}

.cad-senha-wrap input {{
    padding-right: 48px !important;
}}

.cad-olho {{
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: #cfcde6;
    cursor: pointer;
    transition: color 0.15s ease, background 0.15s ease;
}}

.cad-olho:hover {{
    color: #fff;
    background: rgba(255, 255, 255, 0.06);
}}

.cad-olho:focus-visible {{
    outline: 2px solid #8b5cf6;
    outline-offset: 1px;
}}

.cad-olho svg {{
    width: 20px;
    height: 20px;
    display: block;
}}

.cad-senha-wrap input[type="password"] + .cad-olho .olho-fechado,
.cad-senha-wrap input[type="text"] + .cad-olho .olho-aberto {{
    display: none;
}}

/* --- Validação de formulário --- */
.cad-campo input.invalido {{
    border-color: #f43f5e !important;
    background: rgba(244, 63, 94, 0.08);
}}

.cad-erro {{
    display: none;
    margin-top: 5px;
    color: #fb7185;
    font-size: 0.74rem;
    line-height: 1.35;
}}

.cad-erro.show {{
    display: block;
}}

.cad-alerta {{
    display: none;
    margin-bottom: 14px;
    padding: 10px 14px;
    border-radius: 10px;
    background: rgba(244, 63, 94, 0.12);
    border: 1px solid rgba(244, 63, 94, 0.45);
    color: #fda4af;
    font-size: 0.8rem;
    line-height: 1.4;
}}

.cad-alerta.show {{
    display: block;
}}

.cad-alerta.sucesso {{
    background: rgba(52, 211, 153, 0.12);
    border-color: rgba(52, 211, 153, 0.45);
    color: #6ee7b7;
}}

.btn-cad-primario {{
    width: 100%;
    margin-top: 6px;
    padding: 12px 0;
    border-radius: 999px;
    border: none;
    background: #8b5cf6;
    color: #fff;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
}}

.btn-cad-primario:hover {{
    background: #7c4de8;
}}

.cad-divisor {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin: 12px 0;
    color: #8a88ad;
    font-size: 0.78rem;
}}

.cad-divisor::before,
.cad-divisor::after {{
    content: "";
    flex: 1;
    height: 1px;
    background: rgba(255, 255, 255, 0.12);
}}

.btn-cad-google {{
    width: 100%;
    padding: 12px 0;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    background: #17182b;
    color: #fff;
    font-size: 0.92rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
}}

.btn-cad-google:hover {{
    background: #1f213b;
    border-color: rgba(255, 255, 255, 0.28);
}}

.cad-rodape {{
    text-align: center;
    margin-top: 16px;
    font-size: 0.8rem;
    color: #8a88ad;
}}

.cad-rodape a {{
    color: #fff;
    font-weight: 700;
    text-decoration: none;
    cursor: pointer;
}}

.cad-rodape a:hover {{
    text-decoration: underline;
}}

@media (max-width: 900px) {{
  .cad-painel {{ grid-column: 1; grid-row: 2; justify-self: center; }}
}}
"""
CSS += CSS_CADASTRO

CSS_LOGIN = f"""
#tela-login {{ 
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
    justify-content: space-between !important;
}}

#tela-login:not(.hide):not(.hidden):not([hidden]) {{ display: flex !important; }}
#tela-login.hide, #tela-login.hidden, #tela-login[hidden] {{ display: none !important; }}

#tela-login > div, #tela-login .block, #tela-login .form {{
    background: transparent !important; 
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
}}
"""
CSS += CSS_LOGIN

CSS_DASH = """
#tela-inicio:not(.hide):not(.hidden):not([hidden]) { display: flex !important; }
#tela-inicio.hide, #tela-inicio.hidden, #tela-inicio[hidden] { display: none !important; }

#tela-app { background: #0b0a17; min-height: 100vh; gap: 0 !important; padding: 0 !important; }

#topbar { 
    background: linear-gradient(90deg, #3b0764, #4c1d95); 
    padding: 14px 28px !important;
    align-items: center; 
    justify-content: flex-start !important; 
    gap: 32px !important;
    flex-wrap: nowrap !important; 
    margin: 0 !important;
    position: fixed !important;
    top: 0;
    left: 0;
    width: 100% !important;
    z-index: 1000 !important;
    box-sizing: border-box !important;
    height: 70px;
}

#topbar-logo, #topbar-logo > * { background: transparent !important; border: none !important;
          padding: 0 !important; flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
.logo { display: flex; align-items: center; gap: 10px; color: #fff; font-size: 1.4rem; font-weight: 700; }
.logo .ico-svg { width: 24px; height: 24px; color: #e9d5ff; }
.logo .ico-svg path { fill: #e9d5ff !important; }
#busca { flex: 0 1 400px !important; width: 400px !important; max-width: 400px !important;
         min-width: 0 !important; background: transparent !important; border: none !important; }
#busca textarea, #busca input {
          background-color: rgb(0 0 0 / 30%) !important; color: #e8e6f5 !important;
          border: 1px solid rgb(0 0 0 / 12%) !important; border-radius: 999px !important;
          padding: 10px 18px 10px 42px !important;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23a5a3c4' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='6.5'/%3E%3Cpath d='m16 16 4.5 4.5'/%3E%3C/svg%3E") !important;
          background-repeat: no-repeat !important;
          background-position: 16px center !important;
          background-size: 16px 16px !important; }

/* --- Avatar de perfil na navbar --- */
#topbar-perfil, #topbar-perfil > * {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
}
#topbar-perfil { position: relative; margin-left: -18px !important; }

.perfil-btn {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, .18);
    background: #0d0c1d;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
    transition: background .2s ease, border-color .2s ease, transform .2s ease;
    box-shadow: 0 4px 14px rgba(0, 0, 0, .35);
}
.perfil-btn:hover { background: #1a1830; border-color: rgba(255, 255, 255, .42); transform: translateY(-1px); }
.perfil-btn:focus-visible { outline: 2px solid #8b5cf6; outline-offset: 2px; }
.perfil-btn svg { width: 22px; height: 22px; display: block; }

.perfil-menu {
    display: none;
    position: absolute;
    top: 52px;
    right: 0;
    width: 250px;
    z-index: 2000;
    background: #14132b;
    border: 1px solid rgba(255, 255, 255, .1);
    border-radius: 14px;
    box-shadow: 0 18px 44px rgba(0, 0, 0, .55);
    padding: 16px;
    text-align: left;
}
.perfil-menu.aberto { display: block; }
.perfil-nome { color: #fff; font-weight: 700; font-size: .95rem;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.perfil-email { color: #a5a3c4; font-size: .76rem; margin-top: 3px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.perfil-sep { height: 1px; background: rgba(255, 255, 255, .08); margin: 13px -16px; }
.perfil-item {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
    background: transparent;
    border: none;
    color: rgb(255, 255, 255);
    font-size: .87rem;
    font-weight: 600;
    padding: 10px 12px;
    border-radius: 10px;
    cursor: pointer;
    text-align: left;
}
.perfil-item:hover { background: rgba(244, 63, 94, .14); color: #fecdd3; }
.perfil-item svg { width: 17px; height: 17px; flex: none; }

@media (max-width: 700px) {
    #topbar { gap: 14px !important; padding: 12px 16px !important; }
    #busca { flex: 1 1 auto !important; width: auto !important; max-width: none !important; }
    #topbar-perfil { margin-left: -6px !important; }
}

#corpo { 
    gap: 0 !important; 
    flex-wrap: nowrap !important; 
    margin-top: 70px !important;
    min-height: calc(100vh - 70px) !important;
    display: flex !important;
}

#sidebar { 
    background: #0d0c1d; 
    border-right: 1px solid rgba(255,255,255,.05);
    padding: 18px 14px !important; 
    gap: 8px !important;
    flex: none !important; 
    width: 210px !important; 
    position: fixed !important;
    top: 70px;
    left: 0;
    bottom: 0;
    overflow-y: auto;
    z-index: 900 !important;
    box-sizing: border-box !important;
}

.nav-btn { background: transparent !important; color: #cfcde6 !important; border: none !important;
           box-shadow: none !important; justify-content: flex-start !important; text-align: left;
           padding: 12px 16px !important; border-radius: 5px !important; font-weight: 600 !important; }
.nav-btn:hover { background: rgba(139,92,246,.15) !important; }
.nav-btn.primary { background: #8b5cf6 !important; color: #fff !important; }

/* Ícones do menu lateral (SVG via mask, sem emojis) */
#nav-inicio::before, #nav-inicio button::before,
#nav-mapa::before, #nav-mapa button::before,
#nav-diario::before, #nav-diario button::before,
#nav-epoca::before, #nav-epoca button::before,
#nav-perfil::before, #nav-perfil button::before {
    content: "";
    width: 18px;
    height: 18px;
    flex: none;
    margin-right: 10px;
    background-color: currentColor;
    -webkit-mask: var(--nav-ico) center / contain no-repeat;
    mask: var(--nav-ico) center / contain no-repeat;
}
#nav-inicio, #nav-inicio button { --nav-ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 10.7 12 3l9 7.7'/%3E%3Cpath d='M5.6 9.6V21h12.8V9.6'/%3E%3C/svg%3E"); }
#nav-mapa, #nav-mapa button { --nav-ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 21s-6.5-5.3-6.5-10.2A6.5 6.5 0 0 1 18.5 10.8C18.5 15.7 12 21 12 21Z'/%3E%3Ccircle cx='12' cy='10.6' r='2.4'/%3E%3C/svg%3E"); }
#nav-diario, #nav-diario button { --nav-ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 4.5A1.5 1.5 0 0 1 6.5 3H19v18H6.5A1.5 1.5 0 0 1 5 19.5z'/%3E%3Cpath d='M5 17h14M9 7h6'/%3E%3C/svg%3E"); }
#nav-epoca, #nav-epoca button { --nav-ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3.5' y='5' width='17' height='15.5' rx='2.5'/%3E%3Cpath d='M3.5 9.5h17M8 3v4M16 3v4'/%3E%3C/svg%3E"); }
#nav-perfil, #nav-perfil button { --nav-ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23000'%3E%3Ccircle cx='12' cy='8' r='3.8'/%3E%3Cpath d='M4.3 20.5c0-4 3.5-6.6 7.7-6.6s7.7 2.6 7.7 6.6z'/%3E%3C/svg%3E"); }

#conteudo { 
    padding: 22px 28px !important; 
    background: #0b0a17; 
    margin-left: 210px !important;
    width: calc(100% - 210px) !important;
    min-height: calc(100vh - 70px) !important;
    box-sizing: border-box !important;
}

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
.clima b { display: block; font-size: 1.3rem; display: inline-flex; align-items: center; gap: 6px; }
.ico-clima { width: 19px; height: 19px; flex: none; }
.clima span { font-size: .75rem; color: #a5a3c4; }
.verde { color: #34d399; } .azul { color: #38bdf8; }
.planeta { display: flex; align-items: center; gap: 14px; padding: 12px 6px;
           border-bottom: 1px solid rgba(255,255,255,.05); }
.planeta:last-child { border-bottom: none; }
.planeta .img-planeta { border-radius: 50%; flex: none; object-fit: cover; box-shadow: 0 0 10px rgba(0,0,0,0.5); transition: transform 0.2s; }
.planeta:hover .img-planeta { transform: scale(1.1); }
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

.dash-bottom {
    display: grid;
    grid-template-columns: 1fr 1.1fr;
    gap: 20px;
    margin-top: 24px;
    align-items: start;
}
.bottom-card {
    background: rgba(22,24,52,.75);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 18px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    min-width: 0;
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

.obs-list { display: flex; flex-direction: column; width: 100%; }
.obs-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid rgba(255,255,255,.05);
    gap: 16px;
}
.obs-row:last-child { border-bottom: none; }
.obs-row .obs-name { 
    color: #fff; 
    font-size: 0.9rem; 
    font-weight: 500; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis; 
}
.obs-row .obs-local { 
    color: #a5a3c4; 
    font-size: 0.8rem; 
    text-align: right; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis; 
    max-width: 50%; 
}

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

.faixa { position: absolute; left: 16px; top: 72px; z-index: 4; display: flex; flex-direction: column; gap: 10px;
         padding: 10px 8px; border-radius: 14px; background: rgba(15,14,40,.75); border: 1px solid rgba(255,255,255,.06); }
.faixa span { position: relative; display: block; width: 10px; height: 22px; border-radius: 6px; background: var(--c); }
.faixa span:hover::after { content: attr(data-nome); position: absolute; left: 24px; top: 50%;
         transform: translateY(-50%); padding: 4px 10px; border-radius: 8px; white-space: nowrap; color: #fff;
         font-size: .75rem; font-weight: 600; background: rgba(15,14,40,.95); border: 1px solid rgba(255,255,255,.12); }
.escala { position: absolute; left: 45%; bottom: 14px; color: #cfcde6; font-size: .75rem; width: 110px; }
.escala .nums { display: flex; justify-content: space-between; }
.escala .barra { height: 6px; border: 1px solid #cfcde6; border-top: none; margin-top: 6px; }

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

CSS_MAPA_REAL = """
#astro-map { position: absolute; inset: 0; z-index: 1; border-radius: 20px; background: #07081a; font-family: inherit; }
#astro-map img { margin: 0 !important; border-radius: 0 !important; box-shadow: none !important; }
#astro-map img.leaflet-tile { max-width: none !important; max-height: none !important; }
.camada-luzes { mix-blend-mode: screen; }
.astro-pin { background: none !important; border: none !important; }
.astro-pin .mk .glow, .astro-pin .mk .mk-nome, .astro-pin .vm * { pointer-events: none; }
.astro-pin .mk .mk-nome { width: auto; max-width: 150px; }
.zoom-baixo .mk-nome { display: none; }
.zoom-baixo .mk .glow { width: 64px; height: 64px; }
.vm { position: absolute; width: 0; height: 0; }
.vm .halo { position: absolute; left: 0; top: 0; width: 150px; height: 150px; border-radius: 50%;
            transform: translate(-50%, -50%);
            background: radial-gradient(circle, rgba(139,92,246,.7) 0%, rgba(124,58,237,.4) 35%, transparent 70%); }
.vm .ponto { position: absolute; left: 0; top: 0; width: 13px; height: 13px; border-radius: 50%;
             background: #fff; transform: translate(-50%, -50%); box-shadow: 0 0 10px #fff; }
.vm .nome { position: absolute; left: 14px; top: 0; transform: translateY(-50%); color: #fff;
            font-size: .8rem; font-weight: 600; text-shadow: 0 1px 6px rgba(0,0,0,.9); }
.bussola { cursor: pointer; padding: 0; }
.bussola:hover { background: rgba(139,92,246,.35); }
.mapa .leaflet-control-attribution { background: rgba(10,11,32,.7); color: #8a88ad; font-size: 10px; }
.mapa .leaflet-control-attribution a { color: #a5a3c4; }
.mapa .leaflet-bar { border: 1px solid rgba(255,255,255,.12) !important; box-shadow: none; }
.mapa .leaflet-bar a, .mapa .leaflet-bar a:hover { background: #141634; color: #fff; border-bottom: 1px solid #2a2c5e; }
.mapa .leaflet-bar a:hover { background: #22245a; }
.mapa .leaflet-control-layers { background: #141634; color: #fff; border: 1px solid rgba(255,255,255,.12); box-shadow: none; }
.mapa .leaflet-control-scale-line { color: #cfcde6; border-color: #cfcde6; background: rgba(10,11,32,.55); }
.mapa-aviso { position: absolute; left: 50%; bottom: 56px; transform: translateX(-50%); z-index: 5; padding: 9px 18px;
              border-radius: 999px; background: rgba(15,14,40,.95); border: 1px solid rgba(255,255,255,.15);
              color: #fff; font-size: .8rem; }
.ico-loc { width: 18px; height: 18px; display: block; margin: 6px auto; }
"""
CSS += CSS_MAPA_REAL


CSS_DIARIO = """
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

#btn-novo { margin-left: auto !important; flex: none !important; width: auto !important;
            min-width: 0 !important; background: #8b5cf6 !important; color: #fff !important;
            border: none !important; border-radius: 999px !important; font-weight: 600 !important;
            padding: 11px 24px !important; box-shadow: 0 6px 18px rgba(139,92,246,.35); }
#btn-novo:hover { background: #7c4de8 !important; }
#btn-novo::before, #btn-novo button::before {
    content: "";
    width: 16px;
    height: 16px;
    margin-right: 8px;
    background-color: currentColor;
    -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2.4' stroke-linecap='round'%3E%3Cpath d='M12 5v14M5 12h14'/%3E%3C/svg%3E") center / contain no-repeat;
    mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2.4' stroke-linecap='round'%3E%3Cpath d='M12 5v14M5 12h14'/%3E%3C/svg%3E") center / contain no-repeat;
}

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

.d-det-header { display: flex; justify-content: space-between; align-items: flex-start; margin-top: 18px; margin-bottom: 2px; }
.d-det-header h2 { margin: 0 !important; flex: 1; }
.btn-edit { background: rgba(139, 92, 246, 0.15); color: #cfc2ff; border: 1px solid rgba(139, 92, 246, 0.4); padding: 8px 16px; 
            border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; 
            transition: all 0.2s; text-decoration: none; white-space: nowrap; }
.btn-edit:hover { background: rgba(139, 92, 246, 0.3); border-color: #8b5cf6; color: #fff; }
.btn-edit .ico-svg { width: 16px; height: 16px; }
@media (max-width: 600px) { .d-det-header { flex-direction: column; gap: 10px; } .btn-edit { align-self: flex-start; } }

.timeline-group { margin-bottom: 24px; }
.timeline-header { color: #a5a3c4; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 16px; padding-left: 14px; }
.timeline-item { display: flex; position: relative; margin-bottom: 12px; }
.timeline-item::before { content: ""; position: absolute; left: 15px; top: 32px;
                        bottom: -16px; width: 1px; background: rgba(255,255,255,0.1); z-index: 0; }
.timeline-item:last-child::before { display: none; }
.tl-dot { width: 12px; height: 12px; border-radius: 50%; flex: none; margin-top: 22px; margin-right: 16px;
    margin-left: 9px; position: relative; z-index: 1; box-shadow: 0 0 10px var(--dot-color); }
.t-planeta .tl-dot { --dot-color: #f2c94c; background-color: #f2c94c; }
.t-estrela .tl-dot { --dot-color: #38bdf8; background-color: #38bdf8; }
.t-nebula .tl-dot { --dot-color: #f472b6; background-color: #f472b6; }
.t-galaxia .tl-dot { --dot-color: #22d3ee; background-color: #22d3ee; }
.t-lua .tl-dot { --dot-color: #efe4c4; background-color: #efe4c4; }
.t-outro .tl-dot { --dot-color: #c4b5fd; background-color: #c4b5fd; }
.tl-date { color: #f2c94c; font-size: 0.8rem; font-weight: 700; margin-bottom: 6px; padding-left: 4px; }
.timeline-item .d-item { flex: 1; margin: 0; padding: 16px 20px; display: flex; 
                        align-items: center; background: rgba(22,24,52,.6); }
"""
CSS += CSS_DIARIO

CSS_EPOCA = """
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

* {
    scrollbar-width: thin;
    scrollbar-color: #8b5cf6 #0d0c1d;
}

::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}
::-webkit-scrollbar-track {
    background: #0d0c1d;
    border-radius: 8px;
}
::-webkit-scrollbar-thumb {
    background: #3b0764;
    border-radius: 8px;
    border: 2px solid #0d0c1d;
}
::-webkit-scrollbar-thumb:hover {
    background: #8b5cf6;
}
::-webkit-scrollbar-corner {
    background: #0d0c1d;
}

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

CSS_PREMIUM = """
#nav-premium, #hidden-edit-id, #hidden-edit-btn { display: none !important; }
#hidden-cad-nome, #hidden-cad-email, #hidden-cad-senha, #hidden-cad-btn { display: none !important; }
#hidden-login-email, #hidden-login-senha, #hidden-login-btn { display: none !important; }
#btn-criar-conta, #btn-ja-tenho-conta, #btn-concluir-cadastro, #btn-ir-entrar, #btn-voltar-inicio { display: none !important; }
#btn-concluir-login, #btn-ir-cadastro, #btn-voltar-inicio-login { display: none !important; }
#btn-sair, #btn-excluir-conta { display: none !important; }

#side-premium {
    margin-top: auto !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
}
.premium-side-card {
    background: rgba(242, 201, 76, 0.08);
    border: 1px solid rgba(242, 201, 76, 0.35);
    border-radius: 16px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: left;
}
.premium-side-card:hover {
    background: rgba(242, 201, 76, 0.14);
    border-color: #f2c94c;
    transform: translateY(-2px);
}
.premium-side-title {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #f2c94c;
    font-weight: 700;
    font-size: 0.95rem;
    margin-bottom: 6px;
}
.gradio-container-6-31-0 .prose * {
    color: rgb(255, 255, 255);
}
.premium-side-title span { color: rgb(242, 201, 76); }
.premium-side-desc {
    color: rgb(255 254 165 / 88%);
    font-size: 0.78rem;
    line-height: 1.45;
    margin: 0;
}

.prem-wrap {
    display: grid;
    grid-template-columns: 1.45fr 1fr;
    gap: 36px;
    align-items: start;
    padding: 20px 10px;
    max-width: 1180px;
    margin: 0 auto;
    color: #e8e6f5;
}
.prem-header {
    display: flex;
    align-items: center;
    gap: 24px;
    margin-bottom: 32px;
}
.prem-star-outer {
    width: 108px;
    height: 108px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.03);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.prem-star-inner {
    width: 76px;
    height: 76px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.04);
    display: flex;
    align-items: center;
    justify-content: center;
}
.prem-tag {
    color: #f2c94c;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.prem-title {
    font-size: 2.35rem;
    font-weight: 800;
    color: #fff;
    margin: 0 0 8px 0;
    line-height: 1.15;
}
.prem-sub {
    color: #a5a3c4;
    font-size: 1.05rem;
    margin: 0;
}
.prem-features {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
}
.prem-feat-card {
    background: rgba(22, 24, 52, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 18px;
    padding: 22px;
    display: flex;
    align-items: flex-start;
    gap: 16px;
}
.prem-check .ico-svg {
    width: 16px;
    height: 16px;
}
.prem-check {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: rgba(242, 201, 76, 0.12);
    color: #f2c94c;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.9rem;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 2px;
}
.prem-feat-card b {
    display: block;
    color: #fff;
    font-size: 1rem;
    margin-bottom: 6px;
}
.prem-feat-card span {
    display: block;
    color: #a5a3c4;
    font-size: 0.85rem;
    line-height: 1.45;
}

.prem-plan-box {
    background: rgba(22, 24, 52, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 22px;
    padding: 32px 28px;
    text-align: center;
}
.prem-plan-label {
    color: #a5a3c4;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-align: left;
    margin-bottom: 18px;
}
.prem-radio {
    position: absolute;
    opacity: 0;
    pointer-events: none;
}
.prem-plans-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 24px;
}
.prem-plan-card {
    position: relative;
    background: rgba(13, 12, 29, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 22px 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.prem-plan-card:hover {
    border-color: rgba(242, 201, 76, 0.5);
}
#plano-mensal:checked ~ .prem-plans-grid label[for="plano-mensal"],
#plano-anual:checked ~ .prem-plans-grid label[for="plano-anual"] {
    border-color: #f2c94c;
    background: rgba(139, 92, 246, 0.14);
    box-shadow: 0 0 0 1px rgba(242, 201, 76, 0.4);
}
.prem-badge-desconto {
    position: absolute;
    top: -11px;
    background: #f2c94c;
    color: #0b0a17;
    font-size: 0.72rem;
    font-weight: 800;
    padding: 3px 12px;
    border-radius: 999px;
}
.prem-plan-name {
    color: #f2c94c;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
}
.prem-plan-price {
    color: #fff;
    font-size: 1.75rem;
    font-weight: 800;
    margin-bottom: 4px;
}
.prem-plan-period {
    color: #a5a3c4;
    font-size: 0.78rem;
}
.prem-cta-btn {
    display: block;
    width: 100%;
    padding: 15px 20px;
    border-radius: 999px;
    background: #f5c956;
    color: #0b0a17 !important;
    font-size: 1rem;
    font-weight: 700;
    border: none;
    cursor: pointer;
    box-shadow: 0 6px 24px rgba(245, 201, 86, 0.35);
    transition: all 0.2s ease;
    text-decoration: none;
    margin-bottom: 20px;
    box-sizing: border-box;
}
.prem-cta-btn:hover {
    background: #ffd666;
    transform: translateY(-1px);
}
.prem-footer-note {
    color: #a5a3c4;
    font-size: 0.78rem;
    margin-bottom: 6px;
}
.prem-b2b-link {
    color: #8b5cf6;
    font-size: 0.8rem;
    font-weight: 600;
    text-decoration: none;
}
.prem-b2b-link:hover {
    text-decoration: underline;
}

@media (max-width: 1050px) {
    .prem-wrap { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
    .prem-features { grid-template-columns: 1fr; }
}
"""
CSS += CSS_PREMIUM

CSS_PERFIL = """
/* --- Página de perfil --- */
.perfil-page { padding: 6px 4px 30px; color: #e8e6f5; }
.pf-head { display: flex; align-items: center; margin-bottom: 22px; }
.pf-titulo { margin: 0; color: #fff; font-size: 2.1rem; font-weight: 800; letter-spacing: -.01em; }

.pf-grid { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 24px; align-items: start; }
.pf-col { display: flex; flex-direction: column; gap: 18px; }
.pf-card { background: #14132b; border: 1px solid rgba(255,255,255,.06); border-radius: 20px; }
.pf-side { padding: 30px 24px 24px; text-align: center; }

.pf-avatar { width: 104px; height: 104px; margin: 0 auto 18px; border-radius: 50%;
             background: radial-gradient(circle at 50% 40%, #221f45, #16152e 70%);
             border: 2px solid #6d4bd8; color: #fff;
             display: flex; align-items: center; justify-content: center;
             box-shadow: 0 0 0 7px rgba(139,92,246,.10), 0 10px 26px rgba(0,0,0,.35); }
.pf-avatar svg { width: 50px; height: 50px; }
.pf-nome { color: #fff; font-size: 1.3rem; font-weight: 800; line-height: 1.25;
           overflow-wrap: anywhere; }
.pf-email { color: #8a88ad; font-size: .78rem; margin-top: 5px; overflow-wrap: anywhere; }
.pf-plano { display: inline-block; margin: 14px 0 22px; padding: 5px 15px; border-radius: 999px;
            background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
            color: #cfcde6; font-size: .74rem; font-weight: 600; }
.pf-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;
            background: rgba(255,255,255,.025); border-radius: 14px; padding: 15px 6px; }
.pf-stats b { display: block; color: rgb(139, 92, 246); font-size: 1.45rem; font-weight: 800; line-height: 1.1; }
.pf-stats span { color: #a5a3c4; font-size: .72rem; }

.pf-premium { display: flex; align-items: center; gap: 14px; width: 100%; text-align: left;
              padding: 16px 18px; border-radius: 18px; cursor: pointer;
              border: 1px solid rgba(242,201,76,.35); background: rgba(242,201,76,.07);
              transition: all .2s ease; }
.pf-premium:hover { background: rgba(242,201,76,.12); border-color: #f2c94c; transform: translateY(-1px); }
.pf-premium-ico { color: #f2c94c; display: flex; flex: none; }
.pf-premium-ico svg { width: 24px; height: 24px; }
.pf-premium b { display: block; color: #f2c94c; font-size: .95rem; font-weight: 700; }
.pf-premium span span { display: block; color: rgba(255, 254, 165, 0.88); font-size: .76rem; margin-top: 2px; }
.pf-premium .seta { margin-left: auto; color: #f2c94c; font-size: 1.2rem; }

.pf-main { display: flex; flex-direction: column; gap: 28px; min-width: 0; }
.pf-secao { color: #8a88ad; font-size: .7rem; letter-spacing: .13em; font-weight: 700;
            text-transform: uppercase; margin-bottom: 12px; }
.pf-equips { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.pf-equip { display: flex; align-items: center; gap: 12px; padding: 18px 20px; text-align: left;
            cursor: pointer; transition: all .2s ease; }
.pf-equip:hover { border-color: rgba(139,92,246,.5); background: #191833; }
.pf-equip b { display: block; color: #fff; font-size: .95rem; font-weight: 700; }
.pf-equip span span { display: block; color: #a5a3c4; font-size: .76rem; margin-top: 3px; }
.pf-equip .seta { margin-left: auto; color: #6f6d92; font-size: 1.15rem; }

.pf-lista { padding: 4px 8px; overflow: hidden; }
.pf-item { display: flex; align-items: center; gap: 16px; width: 100%; padding: 16px 14px;
           background: transparent; border: none; border-bottom: 1px solid rgba(255,255,255,.05);
           color: #e8e6f5; font-size: .9rem; text-align: left; cursor: pointer;
           transition: background .15s ease; }
.pf-item:last-child { border-bottom: none; }
.pf-item:hover { background: rgba(139,92,246,.10); }
.pf-item:focus-visible { outline: 2px solid #8b5cf6; outline-offset: -2px; }
.pf-item .ico { width: 22px; display: flex; justify-content: center; color: #cfcde6; flex: none; }
.pf-item .ico svg { width: 18px; height: 18px; }
.pf-item .seta { margin-left: auto; color: #6f6d92; font-size: 1.15rem; }

.pf-sair { width: 100%; margin-top: 20px; padding: 15px 20px; border-radius: 999px;
           background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.18); color: #e8e6f5;
           font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .2s ease; }
.pf-sair:hover { background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.32); }

.pf-excluir { width: 100%; margin-top: 10px; padding: 15px 20px; border-radius: 999px;
              background: transparent; border: 1px solid rgba(244,63,94,.55); color: #fb7185;
              font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .2s ease; }
.pf-excluir:hover { background: rgba(244,63,94,.10); border-color: #f43f5e; color: #fda4af; }

/* --- Modal de confirmação --- */
.pf-modal { display: none; position: fixed; inset: 0; z-index: 3000; padding: 20px;
            background: rgba(5,4,14,.72); backdrop-filter: blur(4px);
            align-items: center; justify-content: center; }
.pf-modal.aberto { display: flex; }
.pf-modal-card { width: 100%; max-width: 440px; background: #14132b;
                 border: 1px solid rgba(255,255,255,.1); border-radius: 20px; padding: 26px;
                 box-shadow: 0 30px 80px rgba(0,0,0,.6); }
.pf-modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.pf-modal-head h2 { margin: 0; color: #fff; font-size: 1.2rem; font-weight: 800; }
.pf-modal-x { width: 32px; height: 32px; border-radius: 50%; border: none; background: none;
              color: #cfcde6; font-size: 1.2rem; line-height: 1; cursor: pointer; }
.pf-modal-x:hover { background: rgba(255,255,255,.12); color: #fff; }
.pf-modal-txt { color: #a5a3c4; font-size: .87rem; line-height: 1.55; margin: 0 0 6px; }
.pf-modal-txt b { color: #fda4af; font-weight: 700; }
.pf-erro { display: none; margin-top: 12px; color: #fb7185; font-size: .8rem; line-height: 1.4; }
.pf-erro.show { display: block; }
.pf-acoes { display: flex; justify-content: flex-end; gap: 10px; margin-top: 22px; flex-wrap: wrap; }
.pf-btn-ghost, .pf-btn-perigo { padding: 10px 18px; border-radius: 999px; font-size: .87rem;
                                font-weight: 700; cursor: pointer; border: 1px solid transparent; }
.pf-btn-ghost { background: transparent; border-color: rgba(255,255,255,.16); color: #cfcde6; }
.pf-btn-ghost:hover { background: rgba(255,255,255,.06); }
.pf-btn-perigo { background: #f43f5e; color: #fff; }
.pf-btn-perigo:hover { background: #e11d48; }

/* --- Aviso "em breve" --- */
.em-breve-toast {
    position: fixed;
    left: 50%;
    bottom: 30px;
    z-index: 5000;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 22px;
    border-radius: 14px;
    background: #1a1833;
    border: 1px solid rgba(139, 92, 246, .45);
    box-shadow: 0 18px 44px rgba(0, 0, 0, .55);
    opacity: 0;
    transform: translate(-50%, 14px);
    transition: opacity .25s ease, transform .25s ease;
    pointer-events: none;
}
.em-breve-toast.mostrar { opacity: 1; transform: translate(-50%, 0); }
.em-breve-estrela { display: flex; color: #c4b5fd; }
.em-breve-estrela svg { width: 18px; height: 18px; fill: currentColor; }
.em-breve-txt b { display: block; color: #fff; font-size: .88rem; font-weight: 700; }
.em-breve-txt span { display: block; color: #a5a3c4; font-size: .76rem; margin-top: 2px; }

@media (max-width: 1100px) {
    .pf-grid { grid-template-columns: 1fr; }
    .pf-equips { grid-template-columns: 1fr; }
}
"""
CSS += CSS_PERFIL

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

    <div class="botoes-inicio">
      <button class="btn-hero-primario" onclick="window.astrologClicar('btn-criar-conta')">
        Criar uma conta
      </button>
      <button class="btn-hero-secundario" onclick="window.astrologClicar('btn-ja-tenho-conta')">
        Já tenho conta
      </button>
    </div>
  </div>
</div>
"""

HTML_CADASTRO = """
<div class="hero">
  <div class="topo">
    <div class="marca">🌙 AstroLog</div>
    <div class="titulo-bemvindo">Crie sua conta</div>
    <div class="slogan">Comece seu diário do céu<br>gratuitamente</div>
  </div>

  <div class="lua-area"></div>

  <div class="cad-painel" id="cad-painel">
    <div style="margin-bottom: 12px;">
      <a onclick="window.astrologClicar('btn-voltar-inicio')" style="color: #a5a3c4; font-size: 0.85rem; text-decoration: none; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">‹ Voltar para o início</a>
    </div>

    <div class="cad-alerta" id="alerta-cad" role="alert" aria-live="polite"></div>

    <div class="cad-campo">
      <label for="cad-nome">Nome</label>
      <input type="text" id="cad-nome" name="nome" placeholder="Como quer ser chamado"
             autocomplete="name" maxlength="120" aria-describedby="erro-cad-nome">
      <div class="cad-erro" id="erro-cad-nome" aria-live="polite"></div>
    </div>

    <div class="cad-campo">
      <label for="cad-email">E-mail</label>
      <input type="email" id="cad-email" name="email" placeholder="voce@email.com"
             autocomplete="email" maxlength="180" inputmode="email" spellcheck="false"
             aria-describedby="erro-cad-email">
      <div class="cad-erro" id="erro-cad-email" aria-live="polite"></div>
    </div>

    <div class="cad-campo">
      <label for="cad-senha">Senha</label>
      <div class="cad-senha-wrap">
        <input type="password" id="cad-senha" name="senha" placeholder="Mínimo de 6 caracteres"
               autocomplete="new-password" maxlength="128" aria-describedby="erro-cad-senha"
               onkeydown="if (event.key === 'Enter') { event.preventDefault(); window.realizarCadastro(); }">
        <button type="button" class="cad-olho" onclick="window.astrologAlternarSenha('cad-senha', this)"
                aria-label="Mostrar senha" title="Mostrar senha" tabindex="0">
          <svg class="olho-aberto" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M1.8 12S5.4 5.5 12 5.5 22.2 12 22.2 12 18.6 18.5 12 18.5 1.8 12 1.8 12Z"/>
            <circle cx="12" cy="12" r="3.2"/>
          </svg>
          <svg class="olho-fechado" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 3l18 18"/>
            <path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c6.6 0 10.2 6 10.2 6a17.6 17.6 0 0 1-3.5 4.1"/>
            <path d="M6.2 7.2A17.4 17.4 0 0 0 1.8 12S5.4 18 12 18a9.8 9.8 0 0 0 4-.8"/>
            <path d="M9.9 9.9a3.2 3.2 0 0 0 4.2 4.2"/>
          </svg>
        </button>
      </div>
      <div class="cad-erro" id="erro-cad-senha" aria-live="polite"></div>
    </div>

    <button class="btn-cad-primario" type="button" onclick="window.realizarCadastro()">
      Criar uma conta
    </button>

    <div class="cad-divisor">ou</div>

    <button class="btn-cad-google" type="button" onclick="window.avisoGoogle('cad')">
      Continuar com Google
    </button>

    <div class="cad-rodape">
      Já tem conta? <a onclick="window.astrologClicar('btn-ir-entrar')">Entrar</a>
    </div>
  </div>
</div>
"""

HTML_LOGIN = """
<div class="hero">
  <div class="topo">
    <div class="marca">🌙 AstroLog</div>
    <div class="titulo-bemvindo" style="font-size: 3.8rem; line-height: 1.1;">Bem-vindo<br>de volta</div>
    <div class="slogan" style="margin-top: 14px;">Entre para acessar seu<br>diário de observações</div>
  </div>

  <div class="lua-area"></div>

  <div class="cad-painel" id="login-painel">
    <div style="margin-bottom: 12px;">
      <a onclick="window.astrologClicar('btn-voltar-inicio-login')" style="color: #a5a3c4; font-size: 0.85rem; text-decoration: none; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">‹ Voltar para o início</a>
    </div>

    <div class="cad-alerta" id="alerta-login" role="alert" aria-live="polite"></div>

    <div class="cad-campo">
      <label for="login-email">E-mail</label>
      <input type="email" id="login-email" name="email" placeholder="astronomo@email.com"
             autocomplete="username" maxlength="180" inputmode="email" spellcheck="false"
             aria-describedby="erro-login-email">
      <div class="cad-erro" id="erro-login-email" aria-live="polite"></div>
    </div>

    <div class="cad-campo" style="margin-bottom: 6px;">
      <label for="login-senha">Senha</label>
      <div class="cad-senha-wrap">
        <input type="password" id="login-senha" name="senha" placeholder="••••••••••••"
               autocomplete="current-password" maxlength="128" aria-describedby="erro-login-senha"
               onkeydown="if (event.key === 'Enter') { event.preventDefault(); window.realizarLogin(); }">
        <button type="button" class="cad-olho" onclick="window.astrologAlternarSenha('login-senha', this)"
                aria-label="Mostrar senha" title="Mostrar senha" tabindex="0">
          <svg class="olho-aberto" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M1.8 12S5.4 5.5 12 5.5 22.2 12 22.2 12 18.6 18.5 12 18.5 1.8 12 1.8 12Z"/>
            <circle cx="12" cy="12" r="3.2"/>
          </svg>
          <svg class="olho-fechado" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 3l18 18"/>
            <path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c6.6 0 10.2 6 10.2 6a17.6 17.6 0 0 1-3.5 4.1"/>
            <path d="M6.2 7.2A17.4 17.4 0 0 0 1.8 12S5.4 18 12 18a9.8 9.8 0 0 0 4-.8"/>
            <path d="M9.9 9.9a3.2 3.2 0 0 0 4.2 4.2"/>
          </svg>
        </button>
      </div>
      <div class="cad-erro" id="erro-login-senha" aria-live="polite"></div>
    </div>

    <div style="text-align: right; margin-bottom: 14px;">
      <a href="#" onclick="return false;" style="color: #8b5cf6; font-size: 0.78rem; text-decoration: none; font-weight: 600;">Esqueci minha senha</a>
    </div>

    <button class="btn-cad-primario" type="button" onclick="window.realizarLogin()">
      Entrar
    </button>

    <div class="cad-divisor">ou</div>

    <button class="btn-cad-google" type="button" onclick="window.avisoGoogle('login')">
      Continuar com Google
    </button>

    <div class="cad-rodape">
      Ainda não tem conta? <a onclick="window.astrologClicar('btn-ir-cadastro')">Cadastre-se</a>
    </div>
  </div>
</div>
"""

# Troca dos emojis por ícones vetoriais nas telas de entrada
HTML_HERO = (HTML_HERO.replace("🌙", ICONE_LUA)
                      .replace("🔭", ICONE_TELESCOPIO)
                      .replace("📍", ICONE_PIN)
                      .replace("📒", ICONE_DIARIO))
HTML_CADASTRO = HTML_CADASTRO.replace("🌙", ICONE_LUA)
HTML_LOGIN = HTML_LOGIN.replace("🌙", ICONE_LUA)

def voltar_ao_inicio():
    return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)

def abrir_cadastro():
    return gr.update(visible=False), gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)

def abrir_login():
    return gr.update(visible=False), gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)

def entrar_no_app():
    return gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=True)

# ---------------------------------------------------------------------------
# Autenticação: validação no cliente + no servidor e chamadas à API
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _validar_campos_cadastro(nome, email, senha):
    """Mesmas regras da API, para dar retorno imediato sem ida ao servidor."""
    erros = {}
    if not nome:
        erros["nome"] = "Informe o seu nome."
    elif len(nome) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    elif len(nome) > 120:
        erros["nome"] = "O nome deve ter no máximo 120 caracteres."

    if not email:
        erros["email"] = "Informe o seu e-mail."
    elif len(email) > 180 or not EMAIL_RE.match(email):
        erros["email"] = "Informe um e-mail válido (ex.: voce@email.com)."

    if not senha:
        erros["senha"] = "Informe uma senha."
    elif len(senha) < 6:
        erros["senha"] = "A senha deve ter pelo menos 6 caracteres."
    elif len(senha) > 128:
        erros["senha"] = "A senha deve ter no máximo 128 caracteres."
    return erros


def _corpo_erro_api(r, rota=""):
    """Converte a resposta de erro da API no JSON de campos usado pelo frontend."""
    onde = f" ({rota})" if rota else ""
    if r.status_code == 404:
        # 404 aqui quase sempre significa API antiga em execução, sem as rotas /api/auth/*
        return json.dumps({"geral": (
            f"A API respondeu 404{onde}: esta rota não existe na API que está rodando. "
            "Reinicie o servidor da API para carregar o app.py atualizado: pare o processo "
            "com Ctrl+C e rode de novo 'flask --app app run'."
        )}, ensure_ascii=False)
    try:
        dados = r.json()
    except ValueError:
        return json.dumps({"geral": f"A API respondeu com erro {r.status_code}{onde}."})
    if isinstance(dados, dict):
        campos = dados.get("campos")
        if isinstance(campos, dict) and campos:
            return json.dumps(campos, ensure_ascii=False)
        if dados.get("erro"):
            return json.dumps({"geral": str(dados["erro"])}, ensure_ascii=False)
    return json.dumps({"geral": f"A API respondeu com erro {r.status_code}{onde}."})


def _sem_mudanca():
    """Quatro atualizações vazias (nenhuma tela muda de visibilidade)."""
    return gr.update(), gr.update(), gr.update(), gr.update()


def concluir_cadastro(nome, email, senha):
    """Valida o formulário, cria a conta na API e leva para a tela de login."""
    nome = (nome or "").strip()
    email = (email or "").strip().lower()
    senha = senha or ""

    erros = _validar_campos_cadastro(nome, email, senha)
    if erros:
        return json.dumps(erros, ensure_ascii=False), "", *_sem_mudanca()

    try:
        r = requests.post(
            f"{API_BASE}/api/auth/cadastro",
            json={"nome": nome, "email": email, "senha": senha},
            timeout=TIMEOUT,
        )
    except requests.RequestException as erro:
        return json.dumps({"geral": motivo_falha(erro)}), "", *_sem_mudanca()

    if r.status_code == 201:
        gr.Info("Conta criada com sucesso! Faça login para continuar.")
        # Cadastro NÃO autentica: segue para o login, com o e-mail já preenchido.
        return (
            "",
            email,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
        )
    if r.status_code in (400, 409):
        return _corpo_erro_api(r, "/api/auth/cadastro"), "", *_sem_mudanca()
    return _corpo_erro_api(r, "/api/auth/cadastro"), "", *_sem_mudanca()


def concluir_login(email, senha):
    """Valida e autentica na API; em sucesso leva para o dashboard."""
    email = (email or "").strip().lower()
    senha = senha or ""

    erros = {}
    if not email:
        erros["email"] = "Informe o seu e-mail."
    elif not EMAIL_RE.match(email):
        erros["email"] = "Informe um e-mail válido."
    if not senha:
        erros["senha"] = "Informe a sua senha."
    if erros:
        return json.dumps(erros, ensure_ascii=False), "", "", gr.update(), *_sem_mudanca()

    try:
        r = requests.post(
            f"{API_BASE}/api/auth/login",
            json={"email": email, "senha": senha},
            timeout=TIMEOUT,
        )
    except requests.RequestException as erro:
        return json.dumps({"geral": motivo_falha(erro)}), "", "", gr.update(), *_sem_mudanca()

    if r.status_code == 200:
        try:
            dados = r.json()
            token = dados["token"]
            usuario = dados["usuario"]
        except (ValueError, KeyError):
            return json.dumps({"geral": "Resposta inesperada da API ao entrar."}), "", "", gr.update(), *_sem_mudanca()
        nome = usuario.get("nome") or ""
        primeiro = nome.split()[0] if nome.split() else ""
        gr.Info(f"Bem-vindo(a){', ' + primeiro if primeiro else ''}!")
        return (
            "",
            token,
            nome,
            montar_dashboard(nome),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=True),
        )
    if r.status_code == 401:
        return json.dumps({"geral": "E-mail ou senha incorretos."}), "", "", gr.update(), *_sem_mudanca()
    if r.status_code == 400:
        return _corpo_erro_api(r, "/api/auth/login"), "", "", gr.update(), *_sem_mudanca()
    return _corpo_erro_api(r, "/api/auth/login"), "", "", gr.update(), *_sem_mudanca()


def sair(token):
    """Encerra a sessão na API e volta para a tela de login."""
    token = (token or "").strip()
    if token:
        try:
            requests.post(
                f"{API_BASE}/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            pass
    gr.Info("Sessão encerrada.")
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False),
        "",
        "",
    )


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
        return f"Erro: {erro}", None

FORM_NOVO_HTML = ('<div class="diario-head"><h1>Registrar observação</h1>'
                  '<p>Anote o que você viu no céu.</p></div>')


def _form_titulo_edicao(obs_id):
    return ('<div class="diario-head">'
            f'<h1>Editar observação #{escape(str(obs_id))}</h1>'
            '<p>Altere os dados abaixo e clique em Salvar alterações.</p></div>')


def _data_para_form(valor):
    """ISO-8601 da API → dd/mm/aaaa hh:mm usado no formulário."""
    if not valor:
        return ""
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(valor)


def _id_numerico(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return 0


def _payload_observacao(astro, tipo, equipamento, data_hora, local,
                        poluicao, visibilidade, anotacoes):
    """Valida e converte os campos do formulário. Devolve (payload, erro)."""
    astro = (astro or "").strip()
    if not astro:
        return None, "Informe o astro observado."

    data_hora_iso = data_hora
    if data_hora:
        try:
            dt = datetime.strptime(data_hora, "%d/%m/%Y %H:%M")
            data_hora_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None, "Data inválida. Use o formato dd/mm/aaaa 00:00"

    return {
        "astro_observado": astro,
        "tipo_astro": tipo,
        "equipamento": equipamento,
        "data_hora": data_hora_iso,
        "local": local,
        "poluicao_luminosa": poluicao,
        "visibilidade": visibilidade,
        "anotacoes": anotacoes,
    }, None


def salvar_observacao(astro, tipo, equipamento, data_hora, local,
                      poluicao, visibilidade, anotacoes, editando_id):
    """Cria (POST) ou atualiza (PATCH) uma observação, conforme o modo de edição."""
    campos = (astro, tipo, equipamento, data_hora, local, poluicao, visibilidade, anotacoes)
    editando_id = str(editando_id or "").strip()

    payload, erro = _payload_observacao(*campos)
    if erro:
        return (erro, *campos, editando_id, gr.update(), gr.update(), gr.update())

    try:
        if editando_id:
            r = requests.patch(f"{API_BASE}/api/observacoes/{_id_numerico(editando_id)}",
                               json=payload, timeout=TIMEOUT)
        else:
            r = requests.post(f"{API_BASE}/api/observacoes", json=payload, timeout=TIMEOUT)
    except requests.RequestException as falha:
        return (motivo_falha(falha), *campos, editando_id, gr.update(), gr.update(), gr.update())

    if editando_id:
        if r.status_code != 200:
            return (f"Erro {r.status_code}: {r.text}", *campos, editando_id,
                    gr.update(), gr.update(), gr.update())
        gr.Info(f"Observação {editando_id} atualizada!")
        mensagem = f"Observação {editando_id} atualizada com sucesso."
    else:
        if r.status_code != 201:
            return (f"Erro {r.status_code}: {r.text}", *campos, editando_id,
                    gr.update(), gr.update(), gr.update())
        novo_id = r.json().get("id", "?")
        gr.Info("Observação registrada!")
        mensagem = f"Observação registrada! ID = {novo_id}"

    # Depois de salvar, volta ao modo "novo registro" com o formulário limpo
    return (
        mensagem,
        "", "planeta", "", "", "", "baixa", "boa", "",
        "",
        FORM_NOVO_HTML,
        gr.update(value="Salvar", variant="primary"),
        gr.update(visible=False),
    )


def preparar_nova_observacao():
    """Botão 'Novo registro': limpa o formulário e sai do modo de edição."""
    return (
        "", "planeta", "", "", "", "baixa", "boa", "",
        "", FORM_NOVO_HTML,
        gr.update(value="Salvar", variant="primary"),
        gr.update(visible=False),
    )


def cancelar_edicao():
    """Cancelar edição: limpa o formulário e volta para a lista do diário."""
    return (
        "", "planeta", "", "", "", "baixa", "boa", "",
        "", FORM_NOVO_HTML,
        gr.update(value="Salvar", variant="primary"),
        gr.update(visible=False),
        gr.update(selected="diario"),
    )


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
        return "Informe um ID numérico.", obs_id
    try:
        r = requests.delete(f"{API_BASE}/api/observacoes/{obs_id}", timeout=TIMEOUT)
        if r.status_code == 204:
            return f"Observação {obs_id} excluída.", ""
        if r.status_code == 404:
            return f"Observação {obs_id} não encontrada.", obs_id
        return f"Erro {r.status_code}: {r.text}", obs_id
    except requests.RequestException as erro:
        return f"{motivo_falha(erro)}", obs_id

LATITUDE, LONGITUDE = -23.55, -46.63
SINODICO = 29.530588853
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

PLANETAS_EXEMPLO = [
    ("Vênus", "Oeste · 18:30", "Baixa", "#f2c94c", get_base64_planeta("venus.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Venus_2_Approach_Image.jpg/240px-Venus_2_Approach_Image.jpg", 28),
    ("Júpiter", "Leste · 20:10", "Alta", "#d9a066", get_base64_planeta("jupiter.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Jupiter.jpg/240px-Jupiter.jpg", 42),
    ("Saturno", "Norte · 19:40", "Média", "#e0b96a", get_base64_planeta("saturno.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/Saturn_during_Equinox.jpg/240px-Saturn_during_Equinox.jpg", 38),
    ("Marte", "Madrugada · 04:15", "Média", "#e5534b", get_base64_planeta("marte.png") or "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/OSIRIS_Mars_true_color.jpg/240px-OSIRIS_Mars_true_color.jpg", 24),
]

def fase_lua():
    jd = datetime.now(timezone.utc).timestamp() / 86400 + 2440587.5
    idade = (jd - 2451550.1) % SINODICO
    p = idade / SINODICO
    ilum = (1 - math.cos(2 * math.pi * p)) / 2
    for limite, nome in [(.03, "Nova"), (.22, "Crescente"), (.28, "Quarto crescente"),
                         (.47, "Crescente gibosa"), (.53, "Cheia"), (.72, "Minguante gibosa"),
                         (.78, "Quarto minguante"), (.97, "Minguante")]:
        if p < limite:
            break
    else:
        nome = "Nova"
    nasce = (6 + p * 24) % 24
    se_poe = (nasce + 12) % 24
    hhmm = lambda h: f"{int(h):02d}:{int((h % 1) * 60):02d}"
    return p, nome, round(ilum * 100), hhmm(nasce), hhmm(se_poe)

def lua_svg(p, r=40):
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

def montar_dashboard(nome_usuario=""):
    agora = datetime.now()
    h = agora.hour
    saudacao = "Bom dia" if 5 <= h < 12 else "Boa tarde" if 12 <= h < 18 else "Boa noite"
    data_txt = f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]}"
    primeiro_nome = (nome_usuario or "").strip().split()
    saudacao_nome = f", {escape(primeiro_nome[0])}" if primeiro_nome else ", Observador"

    p, fase, ilum, nasce, se_poe = fase_lua()
    nuvens, temp, umid = _clima() or (None, None, None)
    fmt = lambda v, un: "—" if v is None else f"{v}{un}"

    planetas = "".join(
        f'<div class="planeta">'
        f'  <img src="{img_url}" class="img-planeta" style="width:{tam}px; height:{tam}px;" alt="{n}">'
        f'  <div class="info"><b>{n}</b><span>{onde}</span></div>'
        f'  <div class="badge b-{vis.lower().replace("é", "e")}">{vis}</div>'
        f'</div>'
        for n, onde, vis, cor, img_url, tam in PLANETAS_EXEMPLO)

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

    obs_html = ""
    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        if r.status_code == 200:
            obs = r.json()
            obs.sort(key=lambda o: o.get("data_hora") or "", reverse=True)
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

    eventos_html = """
        <div class="event-row"><div class="event-date">17 NOV</div><div class="event-desc">Chuva de meteoros Leónidas</div></div>
        <div class="event-row"><div class="event-date">25 NOV</div><div class="event-desc">Conjunção Lua e Júpiter</div></div>
        <div class="event-row"><div class="event-date">04 DEZ</div><div class="event-desc">Lua nova — céu escuro ideal</div></div>
        <div class="event-row"><div class="event-date">14 DEZ</div><div class="event-desc">Pico das Geminídeas</div></div>
    """

    return f"""
<div class="dash">
  <div class="dcol">
    <div><h1>{saudacao}{saudacao_nome}</h1><div class="data">{data_txt}</div></div>
    <div class="dcard lua-card">{lua_svg(p)}
      <div><div class="mini">Fase da Lua</div><div class="lua-nome">{fase}</div>
      <div style="font-weight:600;margin:4px 0">Iluminação: {ilum}%</div>
      <div class="amarelo">Nasce ~{nasce} · Se põe ~{se_poe}</div></div></div>
    <div class="dcard clima">
      <div><b class="verde">{ICONE_NUVEM} {fmt(nuvens, "%")}</b><span>Nuvens</span></div>
      <div><b>{ICONE_TERMOMETRO} {fmt(temp, "°C")}</b><span>Temperatura</span></div>
      <div><b class="azul">{ICONE_GOTA} {fmt(umid, "%")}</b><span>Umidade</span></div></div>
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

def foto_local(arquivo, largura=640):
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
    try:
        with Image.open(os.path.join(pasta, arquivo)) as im:
            im = im.convert("RGB")
            im.thumbnail((largura, largura))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except (FileNotFoundError, OSError):
        return ""

# Ponto de partida do "Você" (o botão de localização do mapa troca pela posição real do navegador)
VOCE_PADRAO = (-23.55, -46.63)
KM_FILTRO = 1500   # raio do filtro de distância

LOCAIS_EXEMPLO = [
    dict(id="serra", nome="Serra do Campo Escuro", cor="verde", foto="serra_do_campo.png", foco="50% 62%", lat=-12.60, lng=-41.45, bortle=2,
         mag="21.9", nuvens=12, qualidade="Excelente", serie=[88, 92, 85, 95, 90, 78, 91]),
    dict(id="vale", nome="Vale das Estrelas", cor="amarelo", foto="vale_das_estrelas.png", foco="50% 50%", lat=-9.40, lng=-40.50, bortle=5,
         mag="20.4", nuvens=28, qualidade="Regular", serie=[58, 64, 52, 70, 61, 48, 66]),
    dict(id="pico", nome="Pico da Neblina", cor="azul", foto="pico_da_neblina.png", foco="50% 30%", lat=-14.10, lng=-47.52, bortle=3,
         mag="21.3", nuvens=18, qualidade="Bom", serie=[72, 78, 69, 82, 75, 63, 80]),
    dict(id="morro", nome="Morro do Horizonte", cor="vermelho", foto="morro_do_horizonte.png", foco="50% 52%", lat=-19.92, lng=-43.94, bortle=7,
         mag="18.9", nuvens=45, qualidade="Ruim", serie=[34, 41, 30, 45, 38, 27, 42]),
]

def distancia_km(lat1, lng1, lat2, lng2):
    """Distância em linha reta (fórmula de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))

def tempo_de_carro(km):
    """Estimativa simples: trajeto ~30% maior que a linha reta, a 70 km/h."""
    minutos = round(km * 1.3 / 70 * 60)
    if minutos < 60:
        return f"{minutos} min"
    h, m = divmod(minutos, 60)
    return f"{h} h {m} min" if m else f"{h} h"

for _l in LOCAIS_EXEMPLO:
    _l["km"] = round(distancia_km(VOCE_PADRAO[0], VOCE_PADRAO[1], _l["lat"], _l["lng"]))
    _l["tempo"] = tempo_de_carro(_l["km"])

LEAFLET_HEAD = """
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
"""

MAP_JS = r"""
<script>
(function () {
    var COR = { verde: '#22d3a0', azul: '#2ea8ff', amarelo: '#f5b93a', vermelho: '#f43f5e' };
    var BRASIL = [[-33.8, -73.9], [5.3, -34.8]];

    function distKm(a, b) {
        var R = 6371, rad = Math.PI / 180;
        var dLat = (b[0] - a[0]) * rad, dLng = (b[1] - a[1]) * rad;
        var x = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return R * 2 * Math.asin(Math.sqrt(x));
    }

    function tempoCarro(km) {
        var min = Math.round(km * 1.3 / 70 * 60);
        if (min < 60) return min + ' min';
        var h = Math.floor(min / 60), m = min % 60;
        return h + ' h' + (m ? ' ' + m + ' min' : '');
    }

    function el(tag, cls, txt) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (txt) e.textContent = txt;
        return e;
    }

    function aviso(raiz, msg) {
        var a = el('div', 'mapa-aviso', msg);
        raiz.appendChild(a);
        setTimeout(function () { a.remove(); }, 4000);
    }

    function iniciar(caixa) {
        var locais = JSON.parse(caixa.dataset.locais);
        var voce = JSON.parse(caixa.dataset.voce);
        var kmMax = Number(caixa.dataset.kmmax);
        var raiz = caixa.parentNode;

        var mapa = L.map(caixa, { zoomControl: false, zoomSnap: 0.25, minZoom: 2, worldCopyJump: true,
                                  wheelPxPerZoomLevel: 90 });
        mapa.setView([-14.5, -52], 4, { animate: false });

        // --- Camadas: base escura (padrão) ou satélite; luzes noturnas (NASA) no chip HD ---
        // Base escura da Esri (não exige chave de API) + camada de nomes por cima
        var esriDark = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
        var escuro = L.layerGroup([
            L.tileLayer(esriDark + 'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
                maxNativeZoom: 16, maxZoom: 19,
                attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
            }),
            L.tileLayer(esriDark + 'World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
                maxNativeZoom: 16, maxZoom: 19
            })
        ]).addTo(mapa);
        var satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19, attribution: 'Tiles &copy; Esri'
        });
        var luzes = L.tileLayer('https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_CityLights_2012/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpg', {
            maxNativeZoom: 8, maxZoom: 19, className: 'camada-luzes', opacity: 0.95,
            bounds: L.latLngBounds([-85, -720], [85, 720]),
            attribution: 'Luzes noturnas: NASA GIBS / VIIRS'
        });

        L.control.zoom({ position: 'bottomright' }).addTo(mapa);
        L.control.layers({ 'Escuro': escuro, 'Satélite': satelite }, null, { position: 'bottomright' }).addTo(mapa);
        L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(mapa);

        var chipHd = document.getElementById('flt-hd');
        function sincronizarHd() {
            if (chipHd && chipHd.checked) { luzes.addTo(mapa); } else { mapa.removeLayer(luzes); }
        }
        if (chipHd) chipHd.addEventListener('change', sincronizarHd);
        sincronizarHd();

        // --- "Você" ---
        var vm = el('div', 'vm');
        vm.appendChild(el('div', 'halo'));
        vm.appendChild(el('div', 'ponto'));
        vm.appendChild(el('div', 'nome', 'Você'));
        var marcaVoce = L.marker(voce, {
            icon: L.divIcon({ className: 'astro-pin', html: vm, iconSize: [0, 0] }),
            interactive: false, keyboard: false, zIndexOffset: 500
        }).addTo(mapa);

        // --- Locais: bolhas de cor (qualidade do céu) + pinos clicáveis ---
        function selecionar(id) {
            var radio = document.getElementById('loc-' + id);
            if (radio && !radio.checked) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        var pinos = {};
        locais.forEach(function (l) {
            var cor = COR[l.cor] || '#8b5cf6';
            L.circle([l.lat, l.lng], { radius: 140000, stroke: false, fillColor: cor, fillOpacity: 0.12, interactive: false }).addTo(mapa);
            L.circle([l.lat, l.lng], { radius: 70000, stroke: false, fillColor: cor, fillOpacity: 0.22, interactive: false }).addTo(mapa);

            var pin = el('div', 'mk mk-' + l.id + ' c-' + l.cor + (l.ideal ? ' ideal' : '') + (l.b13 ? ' b13' : ''));
            pin.appendChild(el('span', 'glow'));
            pin.appendChild(el('span', 'ring'));
            pin.appendChild(el('span', 'core'));
            pin.appendChild(el('span', 'mk-nome', l.nome));
            pin.appendChild(el('span', 'mk-tag', 'Bortle ' + l.bortle));
            var marca = L.marker([l.lat, l.lng], {
                icon: L.divIcon({ className: 'astro-pin', html: pin, iconSize: [0, 0] }), title: l.nome
            }).addTo(mapa);
            marca.on('click', function () {
                selecionar(l.id);
                mapa.flyTo([l.lat, l.lng], Math.max(mapa.getZoom(), 6), { duration: 0.8 });
            });
            pinos[l.id] = pin;
        });

        // --- Distâncias a partir de "Você" (cartões e filtro de distância) ---
        var anel1 = L.circle(voce, { radius: 60000, stroke: false, fillColor: '#8b5cf6', fillOpacity: 0.2, interactive: false }).addTo(mapa);
        function atualizarVoce(pos) {
            voce = pos;
            marcaVoce.setLatLng(pos);
            anel1.setLatLng(pos);
            locais.forEach(function (l) {
                var d = distKm(pos, [l.lat, l.lng]);
                pinos[l.id].classList.toggle('kmax', d <= kmMax);
                var sub = document.querySelector('[data-sub="' + l.id + '"]');
                if (sub) sub.textContent = Math.round(d) + ' km de você · ' + tempoCarro(d) + ' de carro';
            });
        }
        atualizarVoce(voce);

        // --- Botão "Minha localização" ---
        var Localizar = L.Control.extend({
            options: { position: 'bottomright' },
            onAdd: function () {
                var c = L.DomUtil.create('div', 'leaflet-bar');
                var a = L.DomUtil.create('a', '', c);
                a.href = '#';
                a.title = 'Minha localização';
                a.setAttribute('role', 'button');
                a.innerHTML = '<svg class="ico-loc" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3.5"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg>';
                L.DomEvent.disableClickPropagation(c);
                L.DomEvent.on(a, 'click', function (e) {
                    L.DomEvent.preventDefault(e);
                    if (!navigator.geolocation) { aviso(raiz, 'Seu navegador não permite obter a localização.'); return; }
                    navigator.geolocation.getCurrentPosition(function (p) {
                        var pos = [p.coords.latitude, p.coords.longitude];
                        atualizarVoce(pos);
                        mapa.flyTo(pos, 7, { duration: 1 });
                    }, function () {
                        aviso(raiz, 'Não foi possível obter sua localização.');
                    }, { timeout: 10000 });
                });
                return c;
            }
        });
        new Localizar().addTo(mapa);

        // --- Detalhes de interação ---
        function aplicarZoom() { caixa.classList.toggle('zoom-baixo', mapa.getZoom() < 5); }
        mapa.on('zoomend', aplicarZoom);
        aplicarZoom();

        var voltar = document.getElementById('mapa-brasil');
        if (voltar) voltar.addEventListener('click', function () {
            mapa.flyToBounds(BRASIL, { padding: [24, 24], duration: 1.2 });
        });

        // A página do mapa começa escondida: enquadra o Brasil quando ganhar tamanho de verdade
        var enquadrado = false;
        new ResizeObserver(function () {
            mapa.invalidateSize();
            if (!enquadrado && caixa.clientWidth > 0 && caixa.clientHeight > 0) {
                enquadrado = true;
                mapa.fitBounds(BRASIL, { padding: [24, 24], animate: false });
            }
        }).observe(caixa);
    }

    function verificar() {
        var caixa = document.getElementById('astro-map');
        if (!caixa || caixa._astro || !window.L) return;
        caixa._astro = true;
        try { iniciar(caixa); } catch (e) { console.error('Mapa AstroLog:', e); }
    }

    new MutationObserver(verificar).observe(document.documentElement, { childList: true, subtree: true });
    verificar();
})();
</script>
"""

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
    hoje = datetime.now()

    filtros = [("ideal", "Ideais", "ideal", True), ("bortle", "Bortle 1-3", "b13", False),
               ("km", f"≤ {KM_FILTRO} km", "kmax", False), ("hd", "HD", None, False)]
    checks = "".join(f'<input type="checkbox" id="flt-{f}" class="loc-radio"{" checked" if on else ""}>'
                     for f, _, _, on in filtros)
    chips = "".join(f'<label for="flt-{f}">{n}</label>' for f, n, _, _ in filtros)
    regras = ""
    for f, _, cls, _ in filtros:
        regras += f'#flt-{f}:checked ~ .mp-grid label[for=flt-{f}]{{background:#8b5cf6;color:#fff;border-color:#8b5cf6}}'
        if cls:
            regras += f'#flt-{f}:checked ~ .mp-grid .mk:not(.{cls}){{opacity:.25;filter:grayscale(.7)}}'

    radios = "".join(f'<input type="radio" name="loc" id="loc-{l["id"]}" class="loc-radio"'
                     f'{" checked" if i == 0 else ""}>' for i, l in enumerate(LOCAIS_EXEMPLO))
    for l in LOCAIS_EXEMPLO:
        i = l["id"]
        regras += (f'#loc-{i}:checked ~ .mp-grid .card-{i},#loc-{i}:checked ~ .mp-grid .graf-{i}{{display:block}}'
                   f'#loc-{i}:checked ~ .mp-grid .rota-{i}{{display:inline-block}}'
                   f'#loc-{i}:checked ~ .mp-grid .mk-{i} .ring{{transform:translate(-50%,-50%) scale(1.2);box-shadow:0 0 18px var(--c)}}'
                   f'#loc-{i}:checked ~ .mp-grid .mk-{i} .mk-tag{{display:inline-block}}')

    link = lambda l: f'https://www.google.com/maps/dir/?api=1&destination={l["lat"]},{l["lng"]}'
    rotas = "".join(f'<a class="rota-btn rota-{l["id"]}" target="_blank" href="{link(l)}">Rota</a>' for l in LOCAIS_EXEMPLO)

    cards = "".join(
        f'<div class="mp-card card-{l["id"]} c-{l["cor"]}">{_cabecalho_popup(l)}'
        f'<div class="p-body"><div class="p-head"><b>{escape(l["nome"])}</b>'
        f'<span class="bortle">Bortle {l["bortle"]}</span></div>'
        f'<div class="p-sub" data-sub="{l["id"]}">{l["km"]} km de você · {l["tempo"]} de carro</div>'
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

    # O JavaScript (MAP_JS) lê estes dados e desenha o mapa interativo (Leaflet)
    dados = [dict(id=l["id"], nome=l["nome"], cor=l["cor"], lat=l["lat"], lng=l["lng"], bortle=l["bortle"],
                  ideal=l["qualidade"] in ("Excelente", "Bom"), b13=l["bortle"] <= 3)
             for l in LOCAIS_EXEMPLO]
    mapa = (f'<div id="astro-map" data-locais="{escape(json.dumps(dados, ensure_ascii=False), quote=True)}" '
            f'data-voce="{escape(json.dumps(list(VOCE_PADRAO)), quote=True)}" data-kmmax="{KM_FILTRO}"></div>')
    bussola = ('<button type="button" class="bussola" id="mapa-brasil" title="Voltar ao Brasil">N'
               '<svg width="14" height="14" viewBox="0 0 14 14"><polygon points="7,1 12,13 7,10 2,13" fill="#fff"/></svg></button>')

    return (f'<style>{regras}</style><div class="mp-wrap">{radios}{checks}<div class="mp-grid">'
            f'<div class="mapa">{mapa}<div class="mp-chips">{chips}</div>{rotas}{bussola}'
            f'<div class="faixa">{faixa}</div></div>'
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


# ---------------------------------------------------------------------------
# Fotos reais dos astros (Wikipédia) para o Diário
# ---------------------------------------------------------------------------
import unicodedata
from concurrent.futures import ThreadPoolExecutor

WIKI_API = "https://pt.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "AstroLog/1.0 (projeto escolar; diario de observacao astronomica)"}
CACHE_FOTOS_ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "astros_cache.json")
DICA_TIPO = {"planeta": "planeta", "estrela": "estrela", "nebula": "nebulosa",
             "galaxia": "galáxia", "lua": "Lua", "outro": "astronomia"}
# A página precisa falar de astronomia (evita foto de pessoa, música, filme com o mesmo nome)
TERMOS_ASTRO = ("astronom", "astro ", "astros", "planeta", "eclipse", "estrela", "estelar", "galaxia", "nebulos",
                "cometa", "meteor", "asteroide", "constelac", "sistema solar", "universo", "telescop",
                "satelite natural", "lunar", "orbita", "cosmic", "cosmos", "supernova", "aurora")
# Palavras genéricas não bastam para confirmar que a foto é do astro digitado
GENERICAS = {"nebulosa", "galaxia", "estrela", "planeta", "aglomerado", "cometa", "chuva", "meteoros"}
LIGACOES = {"de", "da", "do", "das", "dos", "com", "para", "por", "uma", "que", "the", "and"}

def _sem_acento(txt):
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn").lower()

def _palavras(txt):
    return {p for p in re.findall(r"[a-z0-9]+", _sem_acento(txt)) if len(p) >= 2 and p not in LIGACOES}

try:
    with open(CACHE_FOTOS_ARQ, encoding="utf-8") as _f:
        FOTOS_CACHE = json.load(_f)
except (OSError, ValueError):
    FOTOS_CACHE = {}

def _salvar_cache_fotos():
    try:
        with open(CACHE_FOTOS_ARQ, "w", encoding="utf-8") as f:
            json.dump(FOTOS_CACHE, f, ensure_ascii=False)
    except OSError:
        pass

def _foto_na_pasta(nome):
    """Foto sua em img/astros/<nome>.jpg (ex.: marte.jpg) tem prioridade e funciona sem internet."""
    slug = "_".join(re.findall(r"[a-z0-9]+", _sem_acento(nome)))
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        uri = foto_local(f"astros/{slug}{ext}", 900)
        if uri:
            return {"url": uri, "pagina": "", "fonte": "Foto local"}
    return None

def _fala_de_astronomia(pagina):
    texto = _sem_acento(f'{pagina.get("title", "")} {pagina.get("extract", "")}')
    return any(t in texto for t in TERMOS_ASTRO)

def _buscar_wikipedia(consulta, palavras_do_nome):
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": consulta,
              "gsrlimit": 4, "prop": "pageimages|info|extracts", "piprop": "thumbnail", "pithumbsize": 900,
              "inprop": "url", "exintro": 1, "explaintext": 1, "exchars": 700, "exlimit": "max"}
    r = requests.get(WIKI_API, params=params, headers=WIKI_HEADERS, timeout=6)
    r.raise_for_status()
    paginas = sorted((r.json().get("query", {}).get("pages", {})).values(), key=lambda p: p.get("index", 99))
    significativas = (palavras_do_nome - GENERICAS) or palavras_do_nome
    for p in paginas:
        thumb = (p.get("thumbnail") or {}).get("source")
        if thumb and significativas & _palavras(p.get("title", "")) and _fala_de_astronomia(p):
            return {"url": thumb, "pagina": p.get("fullurl", ""), "fonte": "Wikipédia"}
    return None

def foto_astro(nome, tipo):
    """Devolve {'url', 'pagina', 'fonte'} com a foto real do astro, ou None se não achar."""
    nome = re.sub(r"\s+", " ", str(nome or "")).strip()
    if len(nome) < 2:
        return None
    chave = "v2|" + _sem_acento(nome) + "|" + str(tipo)   # v2: ignora fotos guardadas antes da checagem de astronomia
    if chave in FOTOS_CACHE:
        return FOTOS_CACHE[chave]

    # Variações do que foi digitado: "Júpiter e luas galileanas" -> "Júpiter"; "Nebulosa de Órion (M42)" -> sem parênteses
    sem_par = re.sub(r"[()]", " ", nome).strip()
    partes = re.split(r"\s+(?:e|-|–|—|/)\s+|\s*\(", nome)
    variacoes = []
    for v in [sem_par, partes[0].strip()]:
        if v and v not in variacoes:
            variacoes.append(v)

    achou, falha_de_rede = None, False
    for v in variacoes:
        achou = _foto_na_pasta(v)
        if achou:
            break
    if not achou:
        dica = DICA_TIPO.get(tipo, "")
        for v in variacoes:
            palavras = _palavras(v)
            consultas = [f"{v} {dica}".strip()] if dica and _sem_acento(dica) not in _sem_acento(v) else []
            consultas.append(v)
            for c in consultas:
                try:
                    achou = _buscar_wikipedia(c, palavras)
                except (requests.RequestException, ValueError):
                    falha_de_rede = True
                    achou = None
                if achou:
                    break
            if achou:
                break

    if achou or not falha_de_rede:       # não guarda "sem foto" quando foi só a internet que falhou
        FOTOS_CACHE[chave] = achou
        if achou:
            _salvar_cache_fotos()
    return achou

def buscar_fotos(observacoes):
    """{id_da_observação: foto} — consulta os astros diferentes em paralelo."""
    unicos = {}
    for o in observacoes:
        unicos.setdefault((o.get("astro_observado") or "", o.get("tipo_astro") or ""), None)
    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = dict(zip(unicos, pool.map(lambda k: foto_astro(*k), unicos)))
    return {o["id"]: resultados[(o.get("astro_observado") or "", o.get("tipo_astro") or "")] for o in observacoes}

def _img_astro(foto, nome):
    return (f'<img src="{escape(foto["url"], quote=True)}" alt="{escape(str(nome or ""), quote=True)}" '
            f'loading="lazy" referrerpolicy="no-referrer">')

def _credito_foto(foto):
    if foto.get("pagina"):
        return (f'<a class="foto-credito" href="{escape(foto["pagina"], quote=True)}" target="_blank" '
                f'rel="noopener">Foto: {foto["fonte"]}</a>')
    return f'<span class="foto-credito">{foto["fonte"]}</span>'

CSS_FOTOS = """
.d-item .ic.com-foto { overflow: hidden; background: #0b0b24; }
.d-item .ic.com-foto img { width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 0; margin: 0; }
.d-banner.com-foto { background: #05061a; }
.d-banner.com-foto::before, .d-banner.com-foto::after { display: none; }
.d-banner.com-foto > img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
                           display: block; margin: 0; border-radius: 0; }
.foto-credito { position: absolute; right: 10px; bottom: 8px; z-index: 2; padding: 3px 10px; border-radius: 999px;
                font-size: .68rem; color: #e8e6f5 !important; text-decoration: none; background: rgba(5,6,26,.7);
                border: 1px solid rgba(255,255,255,.12); }
a.foto-credito:hover { background: rgba(139,92,246,.6); }
"""
CSS += CSS_FOTOS

CSS_TIPOS = """
.d-tipos { margin-top: 18px; padding: 22px 26px; border-radius: 22px; background: rgba(20,22,48,.9);
           border: 1px solid rgba(255,255,255,.06); }
.d-tipos .d-tipos-titulo { color: #8d8bb5; font-size: .72rem; font-weight: 700; letter-spacing: .12em;
                           text-transform: uppercase; margin-bottom: 12px; }
.d-tipos .linha { display: flex; align-items: center; gap: 14px; padding: 9px 0; color: #fff; font-size: 1rem; }
.d-tipos .ponto { width: 13px; height: 13px; border-radius: 50%; flex: none; background: var(--c); }
.d-tipos .linha b { margin-left: auto; color: #9a98bd; font-weight: 500; }
.tp-planeta { --c: #e8b06a; } .tp-estrela { --c: #38bdf8; } .tp-nebula { --c: #f783c0; }
.tp-galaxia { --c: #3ecbf3; } .tp-lua { --c: #e8e2c8; } .tp-outro { --c: #fbc65a; }
"""
CSS += CSS_TIPOS

def bloco_por_tipo(observacoes):
    """Contagem real de registros por tipo de astro (só os tipos que têm registros)."""
    contagem = {}
    for o in observacoes:
        tipo = o.get("tipo_astro") if o.get("tipo_astro") in TIPO_ROTULO else "outro"
        contagem[tipo] = contagem.get(tipo, 0) + 1
    ordem = list(TIPO_ROTULO)
    tipos = sorted(contagem, key=lambda t: (-contagem[t], ordem.index(t)))
    linhas = "".join(f'<div class="linha tp-{t}"><span class="ponto"></span>{TIPO_ROTULO[t]}<b>{contagem[t]}</b></div>'
                     for t in tipos)
    return f'<div class="d-tipos"><div class="d-tipos-titulo">Por tipo de astro</div>{linhas}</div>'

CABECALHO_DIARIO = ('<div class="diario-head"><h1>Diário de observações</h1>'
                    '<p>Seus registros do céu, organizados em um só lugar.</p></div>')

def carregar_observacao(obs_id):
    """Abre a observação no formulário em modo de edição."""
    nada = gr.update()
    try:
        obs_id = int(obs_id)
    except (TypeError, ValueError):
        gr.Warning("Selecione uma observação válida para editar.")
        return [nada] * 8 + [gr.update(selected="registrar"), nada, nada, nada]

    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        r.raise_for_status()
        obs = next((o for o in r.json() if o.get("id") == obs_id), None)

        if not obs:
            gr.Warning(f"Observação {obs_id} não encontrada.")
            return [nada] * 8 + [gr.update(selected="registrar"), nada, nada, nada]

        return (
            obs.get("astro_observado", ""),
            obs.get("tipo_astro", "planeta"),
            obs.get("equipamento", ""),
            _data_para_form(obs.get("data_hora")),
            obs.get("local", ""),
            obs.get("poluicao_luminosa", "baixa"),
            obs.get("visibilidade", "boa"),
            obs.get("anotacoes", ""),
            gr.update(selected="registrar"),
            _form_titulo_edicao(obs_id),
            gr.update(value="Salvar alterações", variant="primary"),
            gr.update(visible=True),
        )
    except (requests.RequestException, ValueError) as erro:
        gr.Warning(f"Erro ao carregar observação: {motivo_falha(erro)}")
        return [nada] * 8 + [gr.update(selected="registrar"), nada, nada, nada]

def montar_diario():
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
    fotos = buscar_fotos(obs)    # foto real de cada astro pelo nome digitado (cai na arte se não achar)
    txt = lambda o, k: escape(str(o.get(k) or "—"))
    
    radios = "".join(f'<input type="radio" name="filtro" id="f-{c}" class="d-radio"{" checked" if c == "todos" else ""}>'
                     for c, _ in CHIPS)
    radios += "".join(f'<input type="radio" name="obs" id="o-{o["id"]}" class="d-radio"{" checked" if i == 0 else ""}>'
                      for i, o in enumerate(obs))
    
    regras = ""
    for c, _ in CHIPS:
        regras += f'#f-{c}:checked ~ .d-grid label[for=f-{c}]{{background:#8b5cf6;color:#fff}}'
        if c != "todos":
            regras += f'#f-{c}:checked ~ .d-grid .timeline-item:not(.t-{c}){{display:none}}'
    chips = "".join(f'<label for="f-{c}" class="chip">{n}</label>' for c, n in CHIPS)

    grupos = {}
    for o in obs:
        try:
            dt = datetime.fromisoformat(o.get("data_hora"))
            mes_ano = f"{MESES[dt.month - 1].upper()} {dt.year}"
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
            dia_mes = dt.strftime("%d %b").upper() if dt else "—"
            longa = (f"{DIAS[dt.weekday()]}, {dt.day} de {MESES[dt.month - 1]} de {dt.year} • {dt:%H:%M}"
                     if dt else "Data não informada")
            notas = escape(o.get("anotacoes") or "Sem anotações.").replace("\n", "<br>")
            foto = fotos.get(i)
            if foto:
                cls_ic, cls_ban = " com-foto", " com-foto"
                icone = _img_astro(foto, o.get("astro_observado"))
                banner = icone + _credito_foto(foto)
            else:
                cls_ic = cls_ban = ""
                icone = banner = _arte(tipo)
            
            regras += (f'#o-{i}:checked ~ .d-grid .det-{i}{{display:block}}'
                       f'#o-{i}:checked ~ .d-grid label[for=o-{i}] .d-item{{border-color:#8b5cf6;box-shadow:0 0 0 1px #8b5cf6;background:rgba(139,92,246,.1)}}')
            
            itens_html += (
                f'<div class="timeline-item t-{tipo}">'
                f'  <div class="tl-dot"></div>'
                f'  <div style="flex:1">'
                f'    <div class="tl-date">{dia_mes}</div>'
                f'    <label for="o-{i}" class="d-item">'
                f'      <span class="ic{cls_ic}">{icone}</span>'
                f'      <span style="flex:1"><b>{txt(o, "astro_observado")}</b><small>{txt(o, "local")} • {txt(o, "visibilidade").capitalize()}</small></span>'
                f'      <span class="tag-t">{TIPO_ROTULO[tipo]}</span>'
                f'    </label>'
                f'  </div>'
                f'</div>'
            )
            
            detalhes += (
                f'<div class="d-det det-{i}">'
                f'  <div class="d-banner{cls_ban}">{banner}</div>'
                f'  <div class="d-det-header">'
                f'    <h2>{txt(o, "astro_observado")}</h2>'
                f'    <button class="btn-edit" onclick="window.editObs({i})">{ICONE_LAPIS} Editar</button>'
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
            
        itens_html += '</div>'

    return (f'<svg width="0" height="0" style="position:absolute">{DIARIO_DEFS}</svg><style>{regras}</style>'
            f'<div class="d-wrap">{radios}<div class="d-grid"><div class="d-esq">{CABECALHO_DIARIO}<div class="chips">{chips}</div>'
            f'<div class="d-lista">{itens_html}</div>{bloco_por_tipo(obs)}</div><div class="d-dir">{detalhes}</div></div></div>')

MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
ROSA, CIANO, ROXO, VERDE, LARANJA, AMARELO = "#f783c0", "#3ecbf3", "#9d7bfb", "#3fd69b", "#fb9547", "#f6c453"

def _l(nome, meses, cor, ra=None, dec=None):
    return dict(nome=nome, meses=meses, cor=cor, ra=ra, dec=dec)

NOTA_PONTO = "O ponto indica o mês atual dentro da janela ideal."
EPOCA = {
    "planeta": dict(rotulo="Planetas", nota=NOTA_PONTO + " Janelas aproximadas para 2026; mudam a cada ano.", linhas=[
        _l("Vênus", [4, 5, 6, 7, 8, 9], AMARELO), _l("Júpiter", [1, 2, 3, 12], ROSA),
        _l("Saturno", [8, 9, 10, 11, 12], ROXO), _l("Marte", [11, 12], LARANJA),
        _l("Urano", [1, 10, 11, 12], CIANO), _l("Netuno", [8, 9, 10], VERDE)]),
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

PICOS = [(1, 3, "Quadrantídeas", 110), (4, 22, "Líridas", 18), (5, 6, "Eta Aquáridas", 50),
         (8, 12, "Perseidas", 100), (10, 21, "Oriônidas", 20), (11, 17, "Leônidas", 15),
         (12, 14, "Geminídeas", 120), (12, 22, "Úrsidas", 10)]

def _culminacao(ra_h, dec_g):
    from datetime import timedelta
    agora = datetime.now().astimezone()
    d = agora.timestamp() / 86400 + 2440587.5 - 2451545.0
    lst = (18.697374558 + 24.06570982441908 * d + LONGITUDE / 15) % 24
    quando = agora + timedelta(hours=((ra_h - lst) % 24) * 0.9972696)
    return quando, 90 - abs(LATITUDE - dec_g)

def _proximas_chuvas():
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
                return (alt < 30, min(h, 24 - h))
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


PERFIL_HTML = """
<div class="perfil-wrap">
  <button type="button" class="perfil-btn" id="perfil-btn"
          onclick="window.astrologPerfilToggle(event)"
          aria-label="Abrir perfil" aria-haspopup="menu" aria-expanded="false"
          title="Perfil">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="8" r="3.6" fill="currentColor" stroke="none"/>
      <path d="M4.5 20.2c0-3.8 3.4-6.2 7.5-6.2s7.5 2.4 7.5 6.2" fill="currentColor" stroke="none"/>
    </svg>
  </button>

  <div class="perfil-menu" id="perfil-menu" role="menu" aria-labelledby="perfil-btn">
    <div class="perfil-nome" id="perfil-nome">Observador</div>
    <div class="perfil-email" id="perfil-email"></div>
    <div class="perfil-sep"></div>
    <button type="button" class="perfil-item" role="menuitem" onclick="window.astrologPerfilSair()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        <path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>
      </svg>
      Sair da conta
    </button>
  </div>
</div>
"""

PREMIUM_HTML = """
<div class="prem-wrap">
  <div>
    <div class="prem-header">
      <div class="prem-star-outer">
        <div class="prem-star-inner">
          <svg width="38" height="38" viewBox="0 0 24 24" fill="#f5c956" stroke="#f5c956" stroke-width="1.5" stroke-linejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
        </div>
      </div>
      <div>
        <div class="prem-tag">ASTROLOG PREMIUM</div>
        <h1 class="prem-title">Leve seu diário ao próximo nível</h1>
        <p class="prem-sub">Recursos profissionais para quem leva o céu a sério</p>
      </div>
    </div>

    <div class="prem-features">
      <div class="prem-feat-card">
        <div class="prem-check">✓</div>
        <div>
          <b>Exportar para telescópios</b>
          <span>CSV, JSON e formatos de montagem GoTo</span>
        </div>
      </div>

      <div class="prem-feat-card">
        <div class="prem-check">✓</div>
        <div>
          <b>Mapas HD de poluição luminosa</b>
          <span>Resolução de até 100 m por pixel</span>
        </div>
      </div>

      <div class="prem-feat-card">
        <div class="prem-check">✓</div>
        <div>
          <b>Sem anúncios</b>
          <span>Experiência limpa e focada no céu</span>
        </div>
      </div>

      <div class="prem-feat-card">
        <div class="prem-check">✓</div>
        <div>
          <b>Backup na nuvem</b>
          <span>Observações seguras e sincronizadas</span>
        </div>
      </div>
    </div>
  </div>

  <div class="prem-plan-box">
    <div class="prem-plan-label">ESCOLHA SEU PLANO</div>

    <input type="radio" name="plano_prem" id="plano-mensal" class="prem-radio" checked>
    <input type="radio" name="plano_prem" id="plano-anual" class="prem-radio">

    <div class="prem-plans-grid">
      <label for="plano-mensal" class="prem-plan-card">
        <div class="prem-plan-name">MENSAL</div>
        <div class="prem-plan-price">R$ 14,90</div>
        <div class="prem-plan-period">por mês</div>
      </label>

      <label for="plano-anual" class="prem-plan-card">
        <div class="prem-badge-desconto">-30%</div>
        <div class="prem-plan-name">ANUAL</div>
        <div class="prem-plan-price">R$ 124,90</div>
        <div class="prem-plan-period">por ano</div>
      </label>
    </div>

    <button class="prem-cta-btn" onclick="alert('Redirecionando para o checkout do AstroLog Premium...')">
      Assinar Premium
    </button>

    <div class="prem-footer-note">Plano grátis: registros ilimitados e mapa básico</div>
    <a href="#" class="prem-b2b-link" onclick="return false;">Equipes e escolas? Fale com o plano B2B</a>
  </div>
</div>
"""
PREMIUM_HTML = PREMIUM_HTML.replace("✓", ICONE_CHECK)


SESSION_JS = """
<script>
(function () {
    var PAGINA = {'nav-inicio': 'inicio', 'nav-mapa': 'mapa', 'nav-diario': 'diario', 'nav-epoca': 'epoca',
                  'nav-perfil': 'perfil', 'nav-premium': 'premium', 'btn-novo': 'diario',
                  'btn-comecar': 'inicio', 'hidden-edit-btn': 'diario'};
    var ABA = {'nav-diario': 'diario', 'btn-novo': 'registrar', 'hidden-edit-btn': 'registrar'};
    document.addEventListener('click', function (e) {
        var alvo = e.target.closest('#nav-inicio,#nav-mapa,#nav-diario,#nav-epoca,#nav-perfil,#nav-premium,#btn-novo,#btn-comecar,#hidden-edit-btn');
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

# ---------------------------------------------------------------------------
# Página de Perfil
# ---------------------------------------------------------------------------
PESSOA_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<circle cx="12" cy="8" r="3.6" fill="currentColor" stroke="none"/>'
              '<path d="M4.5 20.2c0-3.8 3.4-6.2 7.5-6.2s7.5 2.4 7.5 6.2" fill="currentColor" stroke="none"/>'
              '</svg>')

def _perfil_numeros():
    """Conta observações, astros distintos e locais distintos para o perfil."""
    total = astros = locais = 0
    try:
        r = requests.get(f"{API_BASE}/api/observacoes", timeout=TIMEOUT)
        if r.status_code == 200:
            obs = r.json() or []
            total = len(obs)
            astros = len({(o.get("astro_observado") or "").strip().lower()
                          for o in obs if (o.get("astro_observado") or "").strip()})
            locais = len({(o.get("local") or "").strip().lower()
                          for o in obs if (o.get("local") or "").strip()})
    except (requests.RequestException, ValueError):
        pass
    try:
        r = requests.get(f"{API_BASE}/api/locais", timeout=TIMEOUT)
        if r.status_code == 200:
            locais = max(locais, len(r.json() or []))
    except (requests.RequestException, ValueError):
        pass
    return total, astros, locais


def montar_perfil(nome_usuario="", email_usuario=""):
    """Monta a página de Perfil (dados reais da conta + atalhos)."""
    nome = escape((nome_usuario or "").strip() or "Observador")
    email = escape((email_usuario or "").strip())
    total, astros, locais = _perfil_numeros()

    email_html = f'<div class="pf-email">{email}</div>' if email else ""

    equips = (
        ('Telescópio 130mm f/5', 'Newtoniano · oculares 25mm e 10mm'),
        ('Binóculos 10x50', 'Observação rápida'),
    )
    equips_html = "".join(
        f'<button type="button" class="pf-card pf-equip" onclick="window.astrologEmBreve(\'Meus equipamentos\')" aria-label="Meus equipamentos (em breve)">'
        f'  <span><b>{escape(titulo)}</b><span>{escape(sub)}</span></span>'
        f'  <span class="seta">&#8250;</span>'
        f'</button>'
        for titulo, sub in equips
    )

    conta = (
        ('star', "Exportar meus dados"),
        ('sino', "Notificações de eventos"),
        ('engrenagem', "Configurações"),
        ('ajuda', "Ajuda e suporte"),
    )
    icones = {
        "star": '<svg viewBox="0 0 24 24" fill="#f2c94c" stroke="#f2c94c" stroke-width="1.4" '
                'stroke-linejoin="round"><polygon points="12 2 15.1 8.3 22 9.3 17 14.1 18.2 21 '
                '12 17.8 5.8 21 7 14.1 2 9.3 8.9 8.3 12 2"/></svg>',
        "sino": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
                'stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/>'
                '<path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>',
        "engrenagem": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
                'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/>'
                '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 '
                '1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.11a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06'
                'a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.11'
                'a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06'
                'a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.11a1.7 1.7 0 0 0 1 1.55 '
                '1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9'
                'a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.11a1.7 1.7 0 0 0-1.55 1z"/></svg>',
        "ajuda": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
                 'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/>'
                 '<path d="M9.6 9.2a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.9"/><circle cx="12" cy="17.4" r=".9" fill="currentColor" stroke="none"/></svg>',
    }
    conta_html = ""
    for icone, rotulo in conta:
        conta_html += (
            f'<button type="button" class="pf-item" onclick="window.astrologEmBreve(\'{escape(rotulo)}\')"'
            f' aria-label="{escape(rotulo)} (em breve)">'
            f'  <span class="ico">{icones[icone]}</span>'
            f'  <span>{escape(rotulo)}</span>'
            f'  <span class="seta">&#8250;</span>'
            f'</button>'
        )

    return f"""
<div class="perfil-page">
  <div class="pf-head">
    <h1 class="pf-titulo">Perfil</h1>
  </div>

  <div class="pf-grid">
    <div class="pf-col">
      <div class="pf-card pf-side">
        <div class="pf-avatar">{PESSOA_SVG}</div>
        <div class="pf-nome" data-perfil-nome>{nome}</div>
        {email_html}
        <div class="pf-plano">Plano Gratuito</div>
        <div class="pf-stats">
          <div><b>{total}</b><span>Observações</span></div>
          <div><b>{astros}</b><span>Astros</span></div>
          <div><b>{locais}</b><span>Locais</span></div>
        </div>
      </div>

      <button type="button" class="pf-premium" onclick="window.astrologClicar('nav-premium')">
        <span class="pf-premium-ico">
          <svg viewBox="0 0 24 24" fill="#f2c94c" stroke="#f2c94c" stroke-width="1.4" stroke-linejoin="round">
            <polygon points="12 2 15.1 8.3 22 9.3 17 14.1 18.2 21 12 17.8 5.8 21 7 14.1 2 9.3 8.9 8.3 12 2"/>
          </svg>
        </span>
        <span><b>Seja Premium</b><span>Mapas HD, backup e exportação</span></span>
        <span class="seta">&#8250;</span>
      </button>
    </div>

    <div class="pf-main">
      <section>
        <div class="pf-secao">Meus equipamentos</div>
        <div class="pf-equips">{equips_html}</div>
      </section>

      <section>
        <div class="pf-secao">Conta</div>
        <div class="pf-card pf-lista">{conta_html}</div>
        <button type="button" class="pf-sair" onclick="window.astrologPerfilSair()">Sair da conta</button>
        <button type="button" class="pf-excluir" onclick="window.astrologAbrirExcluirConta()">Excluir conta</button>
      </section>
    </div>
  </div>
</div>

<div class="pf-modal" id="pf-excluir-modal" role="dialog" aria-modal="true"
     aria-labelledby="pf-excluir-titulo"
     onclick="if (event.target === this) window.astrologFecharExcluirConta()">
  <div class="pf-modal-card">
    <div class="pf-modal-head">
      <h2 id="pf-excluir-titulo">Excluir conta</h2>
      <button type="button" class="pf-modal-x" onclick="window.astrologFecharExcluirConta()"
              aria-label="Fechar">&times;</button>
    </div>
    <p class="pf-modal-txt">
      Esta ação é <b>permanente</b>. Sua conta, seus dados de acesso e suas sessões
      serão removidos e não poderão ser recuperados.
    </p>
    <div class="pf-erro" id="pf-excluir-erro" role="alert" aria-live="polite"></div>
    <div class="pf-acoes">
      <button type="button" class="pf-btn-ghost" onclick="window.astrologFecharExcluirConta()">Cancelar</button>
      <button type="button" class="pf-btn-perigo" onclick="window.astrologConfirmarExcluirConta()">
        Excluir definitivamente
      </button>
    </div>
  </div>
</div>
"""


def excluir_conta(token):
    """Exclui a conta na API e volta para a tela inicial."""
    nada = gr.update()
    token = (token or "").strip()
    if not token:
        return ("Sua sessão expirou. Entre novamente.", nada, nada, nada, nada, nada, nada, nada)

    try:
        r = requests.delete(
            f"{API_BASE}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as erro:
        return (motivo_falha(erro), nada, nada, nada, nada, nada, nada, nada)

    if r.status_code == 204:
        gr.Info("Sua conta foi excluída.")
        return (
            "",
            gr.update(visible=True), gr.update(visible=False),
            gr.update(visible=False), gr.update(visible=False),
            "", "", "",
        )
    if r.status_code == 401:
        return ("Sua sessão expirou. Entre novamente.", nada, nada, nada, nada, nada, nada, nada)
    return (f"Não foi possível excluir a conta (erro {r.status_code}).", nada, nada, nada, nada, nada, nada, nada)


PAGINAS = ["inicio", "mapa", "diario", "epoca", "perfil", "premium"]

MENU = ["inicio", "mapa", "diario", "epoca", "perfil"]

def ir_para(pagina):
    return ([gr.update(visible=(p == pagina)) for p in PAGINAS]
            + [gr.update(variant="primary" if p == pagina else "secondary") for p in MENU])

def ir_para_diario(aba):
    return ir_para("diario") + [gr.update(selected=aba)]

def restaurar_sessao(pagina, aba, token):
    """Restaura a sessão guardada no navegador.

    O token é validado em /api/auth/me: sem sessão válida o app abre no login.
    """
    token = (token or "").strip()
    usuario = None
    if token:
        try:
            r = requests.get(
                f"{API_BASE}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                usuario = r.json()
        except (requests.RequestException, ValueError):
            usuario = None

    if usuario is None:
        # Nenhuma sessão válida → volta para a tela inicial (landing)
        return (
            [gr.update(visible=True), gr.update(visible=False),
             gr.update(visible=False), gr.update(visible=False)]
            + [gr.update() for _ in range(len(PAGINAS) + len(MENU) + 1)]
            + ["", "", ""]
        )

    if pagina not in PAGINAS:
        pagina = "inicio"
    aba = aba if aba in ("diario", "registrar", "historico") else "diario"
    return (
        [gr.update(visible=False), gr.update(visible=False),
         gr.update(visible=False), gr.update(visible=True)]
        + ir_para(pagina)
        + [gr.update(selected=aba), token, usuario.get("nome") or "",
           usuario.get("email") or ""]
    )

def carregar_dados_da_pagina(pagina, nome_usuario="", email_usuario=""):
    nada = gr.update()
    if pagina == "inicio":
        return montar_dashboard(nome_usuario), nada, nada, nada, nada, nada
    if pagina == "mapa":
        return nada, listar_locais(""), nada, nada, nada, nada
    if pagina == "diario":
        return nada, nada, montar_diario(), listar_observacoes(), nada, nada
    if pagina == "epoca":
        return nada, nada, nada, nada, montar_melhor_epoca(), nada
    if pagina == "perfil":
        return nada, nada, nada, nada, nada, montar_perfil(nome_usuario, email_usuario)
    return nada, nada, nada, nada, nada, nada

with gr.Blocks(title="AstroLog") as demo:

    with gr.Column(visible=True, elem_id="tela-inicio") as tela_inicio:
        gr.HTML(HTML_HERO)
        btn_criar_conta = gr.Button("Criar uma conta", elem_id="btn-criar-conta")
        btn_ja_tenho_conta = gr.Button("Já tenho conta", elem_id="btn-ja-tenho-conta")

    with gr.Column(visible=False, elem_id="tela-cadastro") as tela_cadastro:
        gr.HTML(HTML_CADASTRO)
        # Componentes ocultos por CSS (visible=True garante que existam no DOM)
        hidden_cad_nome = gr.Textbox(elem_id="hidden-cad-nome", visible=True)
        hidden_cad_email = gr.Textbox(elem_id="hidden-cad-email", visible=True)
        hidden_cad_senha = gr.Textbox(elem_id="hidden-cad-senha", visible=True, type="password")
        hidden_cad_btn = gr.Button("Concluir Cadastro Oculto", elem_id="hidden-cad-btn", visible=True)

        btn_concluir_cadastro = gr.Button("Concluir", elem_id="btn-concluir-cadastro")
        btn_ir_entrar = gr.Button("Entrar", elem_id="btn-ir-entrar")
        btn_voltar_inicio = gr.Button("Voltar", elem_id="btn-voltar-inicio")

    with gr.Column(visible=False, elem_id="tela-login") as tela_login:
        gr.HTML(HTML_LOGIN)
        hidden_login_email = gr.Textbox(elem_id="hidden-login-email", visible=True)
        hidden_login_senha = gr.Textbox(elem_id="hidden-login-senha", visible=True, type="password")
        hidden_login_btn = gr.Button("Entrar (oculto)", elem_id="hidden-login-btn", visible=True)

        btn_concluir_login = gr.Button("Login Concluído", elem_id="btn-concluir-login")
        btn_ir_cadastro = gr.Button("Ir Cadastro", elem_id="btn-ir-cadastro")
        btn_voltar_inicio_login = gr.Button("Voltar Início", elem_id="btn-voltar-inicio-login")

    # Saídas ocultas usadas pelo fluxo de autenticação
    cad_erro = gr.Textbox(visible=False)
    cad_email_novo = gr.Textbox(visible=False)
    login_erro = gr.Textbox(visible=False)
    sessao_token = gr.Textbox(visible=False)
    usuario_nome = gr.Textbox(visible=False)
    usuario_email = gr.Textbox(visible=False)

    with gr.Column(visible=False, elem_id="tela-app") as tela_app:
        with gr.Row(elem_id="topbar"):
            gr.HTML(f'<div class="logo">{ICONE_LUA} AstroLog</div>', elem_id="topbar-logo")
            busca = gr.Textbox(show_label=False, container=False, elem_id="busca",
                               scale=0, min_width=0,
                               placeholder="Buscar local de observação...")
            btn_novo = gr.Button("Novo registro", elem_id="btn-novo", scale=0, min_width=0)
            gr.HTML(PERFIL_HTML, elem_id="topbar-perfil")

        with gr.Row(elem_id="corpo", equal_height=False):
            with gr.Column(scale=0, min_width=210, elem_id="sidebar"):
                nav_inicio = gr.Button("Início", variant="primary",
                                       elem_id="nav-inicio", elem_classes="nav-btn")
                nav_mapa = gr.Button("Mapa", variant="secondary",
                                     elem_id="nav-mapa", elem_classes="nav-btn")
                nav_diario = gr.Button("Diário", variant="secondary",
                                       elem_id="nav-diario", elem_classes="nav-btn")
                nav_epoca = gr.Button("Melhor época", variant="secondary",
                                      elem_id="nav-epoca", elem_classes="nav-btn")
                nav_perfil = gr.Button("Perfil", variant="secondary",
                                       elem_id="nav-perfil", elem_classes="nav-btn")

                nav_premium = gr.Button("Premium", elem_id="nav-premium")

                gr.HTML("""
                <div class="premium-side-card" id="btn-premium-card" onclick="document.getElementById('nav-premium').click()">
                  <div class="premium-side-title">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f2c94c" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/>
                    </svg>
                    <span>AstroLog Premium</span>
                  </div>
                  <p class="premium-side-desc">Mapas HD, backup e exportação para telescópios.</p>
                </div>
                """, elem_id="side-premium")

            with gr.Column(scale=1, elem_id="conteudo"):
                with gr.Column(visible=True) as pg_inicio:
                    dash_html = gr.HTML()

                with gr.Column(visible=False) as pg_mapa:
                    gr.HTML(MAPA_HTML)
                    with gr.Accordion("Locais cadastrados (API)", open=False):
                        df_locais = gr.Dataframe(label="Locais cadastrados")

                with gr.Column(visible=False) as pg_premium:
                    gr.HTML(PREMIUM_HTML)

                with gr.Column(visible=False) as pg_diario:
                    with gr.Tabs(selected="diario", elem_id="diario-tabs") as abas_diario:
                        with gr.Tab("Meu diário", id="diario"):
                            diario_html = gr.HTML()

                        with gr.Tab("Registrar Observação", id="registrar"):
                            form_titulo = gr.HTML(FORM_NOVO_HTML)
                            with gr.Row():
                                astro = gr.Textbox(label="Astro observado", placeholder="Ex.: Júpiter")
                                tipo = gr.Dropdown(TIPOS_ASTRO, label="Tipo de astro", value="planeta")
                            equipamento = gr.Textbox(label="Equipamento", placeholder="Ex.: Telescópio Refletor 114mm")
                            data_hora = gr.Textbox(label="Data e hora (dd/mm/aaaa 00:00)", placeholder="dd/mm/aaaa 00:00", elem_id="data-hora")
                            local = gr.Textbox(label="Local", placeholder="Cidade ou coordenadas")
                            with gr.Row():
                                poluicao = gr.Dropdown(POLUICAO, label="Poluição luminosa", value="baixa")
                                visibilidade = gr.Dropdown(VISIBILIDADE, label="Visibilidade", value="boa")
                            anotacoes = gr.Textbox(label="Anotações", lines=3)
                            with gr.Row():
                                btn_salvar = gr.Button("Salvar", variant="primary", scale=2, min_width=0)
                                btn_cancelar_edicao = gr.Button("Cancelar edição", variant="stop",
                                                                visible=False, scale=1, min_width=0)
                            msg_salvar = gr.Markdown()

                        with gr.Tab("Histórico de Observações", id="historico"):
                            gr.HTML('<div class="diario-head"><h1>Histórico de observações</h1>'
                                    '<p>Todos os seus registros em formato de tabela.</p></div>')
                            btn_listar = gr.Button("Listar", variant="primary")
                            df_hist = gr.Dataframe(label="Observações registradas")
                            with gr.Row():
                                id_excluir = gr.Textbox(label="ID para excluir", scale=1, elem_id="id-excluir")
                                btn_excluir = gr.Button("Excluir", variant="stop", scale=1)
                            msg_excluir = gr.Markdown()

                    hidden_edit_id = gr.Textbox(elem_id="hidden-edit-id")
                    hidden_edit_btn = gr.Button(elem_id="hidden-edit-btn")

                    campos_observacao = [astro, tipo, equipamento, data_hora, local,
                                         poluicao, visibilidade, anotacoes]

                    hidden_edit_btn.click(
                        carregar_observacao,
                        inputs=hidden_edit_id,
                        outputs=campos_observacao + [abas_diario, form_titulo,
                                                     btn_salvar, btn_cancelar_edicao],
                    )

                    btn_salvar.click(
                        salvar_observacao,
                        inputs=campos_observacao + [hidden_edit_id],
                        outputs=[msg_salvar] + campos_observacao
                                + [hidden_edit_id, form_titulo, btn_salvar, btn_cancelar_edicao],
                    ).then(montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)

                    btn_cancelar_edicao.click(
                        cancelar_edicao,
                        inputs=None,
                        outputs=campos_observacao
                                + [hidden_edit_id, form_titulo, btn_salvar,
                                   btn_cancelar_edicao, abas_diario],
                    ).then(montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)

                    btn_listar.click(listar_observacoes, inputs=None, outputs=df_hist)

                    btn_excluir.click(excluir_observacao, inputs=id_excluir, outputs=[msg_excluir, id_excluir]
                    ).then(montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)

                with gr.Column(visible=False) as pg_epoca:
                    epoca_html = gr.HTML()

                with gr.Column(visible=False, elem_id="pg-perfil") as pg_perfil:
                    perfil_html = gr.HTML()

                # Botões fora do menu: usados pelo menu do avatar e pela página de Perfil
                btn_sair = gr.Button("Sair da conta", elem_id="btn-sair", visible=True)
                btn_excluir_conta = gr.Button("Excluir conta", elem_id="btn-excluir-conta", visible=True)
                excluir_erro = gr.Textbox(visible=False)

    saidas_nav = [pg_inicio, pg_mapa, pg_diario, pg_epoca, pg_perfil, pg_premium,
                  nav_inicio, nav_mapa, nav_diario, nav_epoca, nav_perfil]

    salva_pagina = gr.Textbox(visible=False)
    salva_aba = gr.Textbox(visible=False)
    salva_token = gr.Textbox(visible=False)
    salva_nome = gr.Textbox(visible=False)
    salva_email = gr.Textbox(visible=False)
    nav_inicio.click(lambda: ir_para("inicio"), None, saidas_nav).then(
        montar_dashboard, None, dash_html)
    nav_mapa.click(lambda: ir_para("mapa"), None, saidas_nav).then(
        listar_locais, busca, df_locais)
    saidas_diario = saidas_nav + [abas_diario]
    nav_diario.click(lambda: ir_para_diario("diario"), None, saidas_diario).then(
        montar_diario, None, diario_html).then(listar_observacoes, None, df_hist)
    nav_epoca.click(lambda: ir_para("epoca"), None, saidas_nav).then(
        montar_melhor_epoca, None, epoca_html)
    nav_perfil.click(lambda: ir_para("perfil"), None, saidas_nav).then(
        montar_perfil, inputs=[salva_nome, salva_email], outputs=perfil_html,
        js="() => [localStorage.getItem('astrolog_nome') || '', "
           "localStorage.getItem('astrolog_email') || '']",
    )
    nav_premium.click(lambda: ir_para("premium"), None, saidas_nav)
    btn_novo.click(lambda: ir_para_diario("registrar"), None, saidas_diario).then(
        preparar_nova_observacao, None,
        outputs=campos_observacao + [hidden_edit_id, form_titulo, btn_salvar, btn_cancelar_edicao],
    )
    busca.submit(lambda: ir_para("mapa"), None, saidas_nav).then(
        listar_locais, busca, df_locais)

    # --- Navegação entre as telas de entrada ---
    btn_criar_conta.click(abrir_cadastro, inputs=None,
                          outputs=[tela_inicio, tela_cadastro, tela_login, tela_app])
    btn_ja_tenho_conta.click(abrir_login, inputs=None,
                             outputs=[tela_inicio, tela_cadastro, tela_login, tela_app])
    btn_ir_entrar.click(abrir_login, inputs=None,
                        outputs=[tela_inicio, tela_cadastro, tela_login, tela_app])
    btn_ir_cadastro.click(abrir_cadastro, inputs=None,
                          outputs=[tela_inicio, tela_cadastro, tela_login, tela_app])
    btn_voltar_inicio.click(voltar_ao_inicio, inputs=None,
                            outputs=[tela_inicio, tela_cadastro, tela_login, tela_app])
    btn_voltar_inicio_login.click(voltar_ao_inicio, inputs=None,
                                  outputs=[tela_inicio, tela_cadastro, tela_login, tela_app])

    # --- Cadastro: valida no cliente, cria a conta na API e leva para o login ---
    hidden_cad_btn.click(
        concluir_cadastro,
        inputs=[hidden_cad_nome, hidden_cad_email, hidden_cad_senha],
        outputs=[cad_erro, cad_email_novo, tela_inicio, tela_cadastro, tela_login, tela_app],
    ).then(
        None,
        inputs=[cad_erro, cad_email_novo],
        js="(erro, email) => { if (erro) { window.astrologErrosCadastro(erro); } "
           "else if (email) { window.astrologIrParaLogin(email); } }",
    )

    # --- Login: valida, autentica na API e abre o dashboard ---
    hidden_login_btn.click(
        concluir_login,
        inputs=[hidden_login_email, hidden_login_senha],
        outputs=[login_erro, sessao_token, usuario_nome, dash_html,
                 tela_inicio, tela_cadastro, tela_login, tela_app],
    ).then(
        None,
        inputs=[login_erro, sessao_token, usuario_nome, hidden_login_email],
        js="(erro, token, nome, email) => { if (erro) { window.astrologErrosLogin(erro); return; } "
           "if (token) { window.astrologSalvarSessao(token, nome, email); } }",
    ).then(
        listar_observacoes, inputs=None, outputs=df_hist
    )

    # --- Excluir conta: confirma no modal, apaga na API e volta ao início ---
    btn_excluir_conta.click(
        excluir_conta,
        inputs=[sessao_token],
        outputs=[excluir_erro, tela_inicio, tela_cadastro, tela_login, tela_app,
                 sessao_token, usuario_nome, usuario_email],
    ).then(
        None,
        inputs=[excluir_erro],
        js="(erro) => { if (erro) { window.astrologExcluirErro(erro); } "
           "else { window.astrologLimparSessao(); window.astrologFecharExcluirConta(); } }",
    )

    # --- Sair: encerra a sessão na API e volta para o login ---
    btn_sair.click(
        sair,
        inputs=[sessao_token],
        outputs=[tela_inicio, tela_cadastro, tela_login, tela_app, sessao_token, usuario_nome],
    ).then(
        None,
        inputs=None,
        js="() => { window.astrologLimparSessao(); }",
    )

    demo.load(
        restaurar_sessao, inputs=[salva_pagina, salva_aba, salva_token],
        outputs=[tela_inicio, tela_cadastro, tela_login, tela_app] + saidas_nav
                + [abas_diario, sessao_token, usuario_nome, usuario_email],
        js="() => [sessionStorage.getItem('astrolog_pagina') || '', "
           "sessionStorage.getItem('astrolog_aba') || '', "
           "localStorage.getItem('astrolog_token') || '']",
    ).then(
        None,
        inputs=[sessao_token, usuario_nome, usuario_email],
        js="(token, nome, email) => { "
           "if (!token) { window.astrologLimparSessao(); return; } "
           "if (nome) localStorage.setItem('astrolog_nome', nome); "
           "if (email) localStorage.setItem('astrolog_email', email); }",
    ).then(
        carregar_dados_da_pagina, inputs=[salva_pagina, salva_nome, salva_email],
        outputs=[dash_html, df_locais, diario_html, df_hist, epoca_html, perfil_html],
        js="() => [sessionStorage.getItem('astrolog_pagina') || 'inicio', "
           "localStorage.getItem('astrolog_nome') || '', "
           "localStorage.getItem('astrolog_email') || '']",
    )

if __name__ == "__main__":

    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.abspath(os.path.join(current_dir, "..", "img"))
    demo.launch(css=CSS, allowed_paths=[img_path], head=LEAFLET_HEAD + INPUT_MASK_JS + EDIT_JS + AUTH_JS + SESSION_JS + MAP_JS)