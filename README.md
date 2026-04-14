# Instagram DM Bot - FastAPI 🤖

Este projeto é um ponto de partida para criar bots de automação no Instagram utilizando a API oficial da Meta (Graph API). Ele utiliza o framework **FastAPI** para alta performance e facilidade de desenvolvimento.

## Funcionalidades

- **Integração com a Meta:** Rota de verificação de Webhook pronta.
- **Recebimento de Mensagens:** Processa eventos de DM (Direct Messages) em tempo real.
- **Resposta Automática:** Envia mensagens de volta para o usuário de forma instantânea.
- **Proteção contra Loop:** Lógica implementada para evitar que o bot responda às suas próprias mensagens (o que gera erro na API).

## 🛠️ Tecnologias

- [Python 3.10+](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/) - Framework web.
- [Uvicorn](https://www.uvicorn.org/) - Servidor ASGI.
- [Requests](https://requests.readthedocs.io/) - Para chamadas na Graph API.
- [Python-dotenv](https://pypi.org/project/python-dotenv/) - Gestão de variáveis de ambiente.

## Configuração do Ambiente

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/seu-usuario/seu-repositorio.git](https://github.com/seu-usuario/seu-repositorio.git)
   cd seu-repositorio
   ```

2. **Crie um arquivo `.env` na raiz do projeto:**
   ```env
   VERIFY_TOKEN="sua_senha_do_painel_da_meta"
   PAGE_ACCESS_TOKEN="seu_token_gigante_gerado_pela_meta"
   IG_BOT_ID="seu_id_do_instagram_bot"
   ```

3. **Instale as dependências:**
   ```bash
   pip install fastapi uvicorn requests python-dotenv
   ```

## Como Executar

1. **Inicie o servidor local:**
   ```bash
   uvicorn main:app --reload
   ```

2. **Exponha o servidor com Ngrok (ou similar):**
   ```bash
   ngrok http 8000
   ```

3. **Configure no Painel da Meta:**
   - **URL de callback:** `https://sua-url-ngrok.io/webhook`
   - **Token de verificação:** O mesmo que você colocou no seu `.env` (VERIFY_TOKEN).
   - **Campos de Webhook:** Assine o campo `messages`.

---
Desenvolvido por bruno-romeu