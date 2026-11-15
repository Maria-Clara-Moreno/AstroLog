# AstroLog — Diário de Observação Astronômica

Um app para astrônomos amadores e entusiastas. Permite registrar observações do céu, calcular a melhor época para observar certos astros e mapear áreas com baixa poluição luminosa para sessões de observação.

## Stack

- **Backend:** Python + Flask + SQLAlchemy
- **Banco:** MariaDB (via Docker Compose)
- **Documentação:** OpenAPI 3.0.3 + Swagger UI
- **Frontend:** Gradio
- **Testes:** pytest

## Estrutura
```
AstroLog/
├── app.py               # API Flask (inclui /api/auth/*)
├── config.py            # Configuração (DATABASE_URL, NASA)
├── models.py            # ORM: Observacao, LocalObservacao, Usuario, Sessao
├── openapi.yaml         # Contrato OpenAPI (Swagger em /swagger)
├── docker-compose.yml   # MariaDB
├── frontend/
│   └── gradio_app.py    # Interface (cadastro, login e dashboard)
└── tests/
    ├── test_api.py
    └── test_auth.py
```

## Autenticação

O cadastro e o login são validados **no formulário** (JavaScript, com mensagens
embaixo de cada campo) e **no servidor** (funções Python do Gradio e rotas da API).

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/auth/cadastro` | Cria a conta. `201` sucesso, `400` campos inválidos, `409` e-mail já cadastrado. |
| POST | `/api/auth/login` | Valida e-mail/senha e devolve `token`. `401` se as credenciais estiverem erradas. |
| GET | `/api/auth/me` | Retorna o usuário do token (`Authorization: Bearer <token>`). |
| PATCH | `/api/auth/me` | Atualiza o nome de exibição do usuário autenticado. |
| DELETE | `/api/auth/me` | Exclui a conta do usuário e todas as suas sessões. |
| POST | `/api/auth/logout` | Invalida o token da sessão. |

Fluxo das telas:

1. **Início** → *Criar uma conta*.
2. **Cadastro**: valida nome (2+), e-mail e senha (6+). Se a API criar a conta,
   a tela de **login** abre com o e-mail já preenchido.
3. **Login**: credenciais válidas abrem o **dashboard**; inválidas mostram
   "E-mail ou senha incorretos." sem revelar se o e-mail existe.
   Os dois formulários têm o **olho** para mostrar/ocultar a senha.
4. Ao recarregar, o token salvo no navegador é validado em `/api/auth/me` e a
   sessão é restaurada. **Sair da conta** fica no menu do avatar (canto superior
   direito) e na página de Perfil — não há mais botão "Sair" na barra lateral.

As senhas são guardadas apenas como hash (`werkzeug.security`) na tabela
`usuarios`; os tokens ficam em `sessoes` e expiram em 7 dias.

### Página de Perfil

Acessível pelo item **Perfil** no menu lateral ou pelo avatar no canto superior
direito (menu → nome/e-mail). Ela mostra:

- avatar com o mesmo ícone de usuário da navbar, nome, e-mail e plano;
- contadores reais de **observações**, **astros distintos** e **locais**
  (calculados a partir de `/api/observacoes` e `/api/locais`);
- cartões de equipamentos e atalho para o Premium;
- bloco **Conta** com Exportar meus dados, Notificações de eventos,
  **Configurações** e Ajuda e suporte;
- botão **Sair da conta** (sem a antiga bolinha de configurações no canto).

A página tem **Sair da conta** e, logo abaixo, **Excluir conta** (com modal de
confirmação; a exclusão apaga de verdade o usuário e as sessões na API).

Nesta etapa, o restante da página é **somente visual**: a única ação funcional é **Sair da
conta** (que encerra a sessão na API). Clicar nos equipamentos, nos itens do
bloco Conta ou na engrenagem do canto superior direito apenas exibe o aviso
**“Em breve”** — esses recursos ainda não têm backend.

## Edição de observações

No **Diário**, cada registro tem o botão **Editar**. Ele abre o formulário no
modo de edição (título "Editar observação #N"), já preenchido — inclusive a
data no formato `dd/mm/aaaa hh:mm`. Ao salvar:

- o app envia `PATCH /api/observacoes/{id}` e **atualiza** o registro (não cria
  outro);
- **Cancelar edição** descarta as mudanças e volta para a lista;
- **Novo registro** limpa o formulário e sai do modo de edição.

## Ícones

Todas as telas usam ícones vetoriais (SVG) no lugar de emojis — marca AstroLog,
boas-vindas, menu lateral, barra superior, clima do dashboard, botão Editar,
checks do Premium e aviso "Em breve". O rodapé padrão do Gradio também fica
oculto.

## Rodando os testes

```bash
pip install -r requirements.txt
pytest -q
```

Os testes de autenticação usam um SQLite temporário (`DATABASE_URL`), sem
precisar do MariaDB.

## Problemas comuns

### "A API respondeu com erro 404" ao criar conta ou entrar

O `app.py` já tem as rotas `/api/auth/*`, mas a API **em execução** pode ser uma
versão antiga: `flask --app app run` (sem debug) não recarrega o código quando o
arquivo muda. Pare o terminal da API com `Ctrl+C` e suba de novo:

```bash
flask --app app run
```

Para confirmar em qual estado está a API:

```bash
python diagnostico_auth.py
# ou, apontando para outra porta:
ASTROLOG_API=http://127.0.0.1:5000 python diagnostico_auth.py
```

O script mostra ✓ quando as rotas de cadastro, login e sessão existem. Se
aparecer 404, ainda há um processo antigo atendendo (veja "Address already in
use" no terminal) — encerre-o e suba a API outra vez. Reinicie também o Gradio
para carregar o `gradio_app.py` novo.
