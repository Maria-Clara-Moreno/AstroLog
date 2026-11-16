# AstroLog — Diário de Observação Astronômica

Um aplicativo para astrônomos amadores e entusiastas. Permite registrar observações do céu, calcular a melhor época para observar certos astros e mapear áreas com baixa poluição luminosa para sessões de observação.

## Stack

- **Backend:** Python + Flask + SQLAlchemy
- **Banco de Dados:** MariaDB (via Docker Compose)
- **Documentação:** OpenAPI 3.0.3 + Swagger UI
- **Frontend:** Gradio
- **Testes:** pytest

## Estrutura do Projeto

```text
AstroLog/
├── __pycache__/           # Arquivos compilados do Python (gerado automaticamente)
├── frontend/
│   ├── astros_cache.json  # Cache local para otimizar requisições de astros
│   └── gradio_app.py      # Interface web (Gradio) com design customizado
├── img/                   # Imagens e assets visuais do projeto (ex: lua.png)
├── tests/
│   ├── __pycache__/
│   └── test_api.py        # Testes automatizados com pytest
├── venv/                  # Ambiente virtual Python
├── app.py                 # API Flask (rotas, auth e lógica principal)
├── config.py              # Configurações (DATABASE_URL, NASA API)
├── docker-compose.yml     # Configuração do container do MariaDB
├── models.py              # Modelos ORM (Observacao, Local, Usuario, Sessao)
├── openapi.yaml           # Contrato OpenAPI (documentação Swagger)
├── README.md              # Este arquivo
└── requirements.txt       # Dependências do projeto
```

## Guia Rápido (Passo a Passo)

1. Criar e ativar o ambiente virtual (Apenas na primeira vez)

# Cria a pasta venv
python -m venv venv

# Ativa a venv no Windows (PowerShell)
.\venv\Scripts\Activate.ps1

| Nota: Se aparecer erro de "execução de scripts desabilitada", rode antes: Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned.

2. Instalar as dependências

Com a venv ativada (você verá (venv) no início da linha do terminal), instale as bibliotecas necessárias:

pip install -r requirements.txt

3. Subir o Banco de Dados (Docker)

docker compose up -d

| Nota: Este projeto está configurado para usar a porta 3307 no seu computador (mapeada para a 3306 do container) para evitar conflitos com MySQLs locais.

4. Inicializar as tabelas do banco

flask --app app init-db

5. Rodar a API (Backend)

flask --app app run

| A API estará disponível em http://127.0.0.1:5000. Deixe este terminal aberto.

6. Rodar a Interface (Frontend)

.\venv\Scripts\Activate.ps1
python frontend/gradio_app.py

| A interface estará disponível em http://127.0.0.1:7860.

## Autenticação

O cadastro e o login são validados no formulário (JavaScript, com mensagens embaixo de cada campo) e no servidor (funções Python do Gradio e rotas da API).

Método	  Rota	                      Descrição
POST	     /api/auth/cadastro	          Cria a conta. 201 sucesso, 400 campos inválidos, 409 e-mail já cadastrado.
POST	     /api/auth/login	             Valida e-mail/senha e devolve token. 401 se as credenciais estiverem erradas.
GET	     /api/auth/me	                Retorna o usuário do token (Authorization: Bearer <token>).
PATCH	     /api/auth/me	                Atualiza o nome de exibição do usuário autenticado.
DELETE	  /api/auth/me	                Exclui a conta do usuário e todas as suas sessões.
POST	    /api/auth/                    logout	Invalida o token da sessão.

As senhas são guardadas apenas como hash (werkzeug.security) na tabela usuarios; os tokens ficam em sessoes e expiram em 7 dias.

## Página de perfil

Acessível pelo item Perfil no menu lateral ou pelo avatar no canto superior direito. Ela mostra:

avatar, nome, e-mail e plano;

contadores reais de observações, astros distintos e locais;

atalhos para Equipamentos, Premium e Configurações;

botões para Sair da conta e Excluir conta (com modal de confirmação).

Nota: Nesta etapa, o restante da página é somente visual: a única ação funcional é Sair da conta. Clicar nos itens sem backend exibe o aviso “Em breve”.

## Edição de observações

No Diário, cada registro tem o botão Editar. Ele abre o formulário no modo de edição, já preenchido (inclusive a data no formato dd/mm/aaaa hh:mm). Ao salvar:

o app envia PATCH /api/observacoes/{id} e atualiza o registro;

Cancelar edição descarta as mudanças;

Novo registro limpa o formulário.

## Documentação da API (Swagger)

Com a API rodando, acesse no navegador:

Swagger UI: http://127.0.0.1:5000/swagger

OpenAPI JSON/YAML: http://127.0.0.1:5000/openapi.yaml

## Rodando os testes

pytest -q

| Os testes de autenticação usam um SQLite temporário (DATABASE_URL), sem precisar do MariaDB rodando.

## Problemas Comuns

"A API respondeu com erro 404" ao criar conta ou entrar
O app.py tem as rotas /api/auth/*, mas a API em execução pode ser uma versão antiga. O Flask não recarrega o código sozinho se você não estiver no modo debug. Pare o terminal da API com Ctrl+C e suba de novo:

flask --app app run

Reinicie também o Gradio para carregar o gradio_app.py novo.

## Erro de conexão com o banco (Access denied ou porta em uso)

Se o Docker reclamar que a porta 3307 (ou 3306) está em uso, verifique se há um MySQL local rodando. Você pode parar o serviço do MySQL no Windows ou alterar a porta no docker-compose.yml e no config.py.

Para recriar o container do banco do zero (apaga os dados locais):

docker compose down -v
docker compose up -d

