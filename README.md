# Instagram DM Bot com FastAPI 🤖📱

Um bot simples, rápido e escalável construído em Python com FastAPI para interagir automaticamente com Mensagens Diretas (DMs) do Instagram através da API oficial da Meta (Graph API).

## 🚀 Funcionalidades

* **Webhooks em Tempo Real:** Recebe e processa mensagens enviadas para a conta do Instagram instantaneamente.
* **Respostas Automáticas:** Envia mensagens de volta para o usuário utilizando a Graph API da Meta.
* **Proteção contra Loop:** Lógica integrada para identificar e ignorar mensagens enviadas pelo próprio bot, evitando o "efeito eco" e bloqueios da API.

## 🛠️ Tecnologias Utilizadas

* **Python 3.x**
* **FastAPI:** Framework web moderno e rápido para construção de APIs.
* **Uvicorn:** Servidor web ASGI ultra-rápido.
* **Requests:** Para facilitar as requisições HTTP para os servidores da Meta.
* **python-dotenv:** Para manter chaves e tokens seguros fora do código fonte.
* **Ngrok:** Utilizado no ambiente de desenvolvimento para expor o servidor local para a web.

## ⚙️ Pré-requisitos

Para rodar este projeto, você precisará ter:
1. Uma conta no [Meta for Developers](https://developers.facebook.com/).
2. Um Aplicativo criado no painel da Meta com o produto **Webhooks** e **Instagram** configurados.
3. Uma conta do **Instagram Profissional** (Empresa ou Criador de Conteúdo).
4. Uma **Página do Facebook** vinculada a essa conta do Instagram.

## 📦 Como Instalar e Rodar Localmente

1. **Clone este repositório:**
   ```bash
   git clone [https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git](https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git)
   cd SEU_REPOSITORIO