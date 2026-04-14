# Instagram DM Bot - FastAPI 🤖

Este projeto é um bot de automação para Instagram utilizando a API oficial da Meta (Graph API) e inteligência artificial para responder mensagens de forma automática e inteligente.

## 🚀 Funcionalidades

- **Integração com a Meta:** Rota de verificação de Webhook (handshake) pronta para uso.
- **Recebimento de Mensagens:** Processa eventos de DM (Direct Messages) em tempo real.
- **Cérebro com IA:** Integração com o modelo **Gemini 2.5 Flash** para gerar respostas naturais e contextualizadas.
- **Processamento em Background:** Utiliza `BackgroundTasks` do FastAPI para responder à Meta instantaneamente (evitando timeouts de 20s e mensagens duplicadas) enquanto a IA processa a resposta em segundo plano.
- **Proteção contra Loop:** Lógica de segurança para ignorar o próprio ID do bot, evitando respostas infinitas.

## 🛠️ Tecnologias

- [Python 3.10+](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/) - Framework web de alta performance.
- [Uvicorn](https://www.uvicorn.org/) - Servidor ASGI.
- [Google GenAI](https://pypi.org/project/google-genai/) - SDK oficial para os modelos Gemini.
- [Requests](https://requests.readthedocs.io/) - Para chamadas na Graph API da Meta.
- [Python-dotenv](https://pypi.org/project/python-dotenv/) - Gestão de variáveis de ambiente.

## ⚙️ Configuração do Ambiente

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/bruno-romeu/seu-repositorio.git](https://github.com/bruno-romeu/seu-repositorio.git)
   cd seu-repositorio
   ```

2. **Crie um arquivo `.env` na raiz do projeto:**
   ```env
   VERIFY_TOKEN="sua_senha_do_painel_da_meta"
   PAGE_ACCESS_TOKEN="seu_token_gigante_gerado_pela_meta"
   IG_BOT_ID="seu_id_do_instagram_bot"
   GEMINI_API_KEY="sua_chave_do_google_ai_studio"
   ```

3. **Instale as dependências:**
   ```bash
   pip install fastapi uvicorn requests python-dotenv google-genai
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