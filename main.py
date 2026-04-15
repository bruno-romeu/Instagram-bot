import os
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from dotenv import load_dotenv
from google import genai
from google.genai import types
from contextlib import asynccontextmanager
from database import engine, Base
import models
from database import AsyncSessionLocal
import crud


load_dotenv()
app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

# Substitua o seu app = FastAPI() por esta linha:
app = FastAPI(lifespan=lifespan)

#usar essa mesma senha lá no painel da Meta.
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
IG_BOT_ID = os.getenv("IG_BOT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------- CÉREBRO DA IA ----------------
async def pensar_com_ia(historico_mensagens):
    try:
        personalidade = """Você é um assistente virtual de atendimento para um perfil do Instagram. 
        Seja sempre muito educado, prestativo e use emojis. 
        Mantenha suas respostas curtas, pois estão sendo lidas em uma DM de celular."""

        # Transforma as mensagens do banco de dados em um texto de roteiro de teatro
        texto_historico = "Histórico recente da conversa:\n"
        for msg in historico_mensagens:
            quem = "Cliente" if msg.remetente == "user" else "Você"
            texto_historico += f"{quem}: {msg.conteudo}\n"
            
        texto_historico += "Você: " # Deixa a "deixa" para a IA responder

        # O novo SDK do Google tem um método .aio para rodar de forma assíncrona
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=texto_historico,
            config=types.GenerateContentConfig(
                system_instruction=personalidade,
            )
        )
        return response.text
    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return "Ops, tive um pequeno problema técnico! 🤯 Podes repetir?"
    

# ---------------- BOCA DO BOT (META API) ----------------
def send_reply(recipient_id, text_message):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text_message}
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print("✅ Resposta enviada com sucesso pro direct!")
    else:
        print(f"❌ Erro ao enviar resposta: {response.text}")

# ---------------------------------------------------------
# FUNÇÃO QUE JUNTA O RECEBIMENTO DA MENSAGEM, O PENSAR DA IA E O ENVIO DA RESPOSTA
# ---------------------------------------------------------
async def processar_mensagem_em_background(sender_id, message_text):
    print(f"🧠 Abrindo conexão com o banco para {sender_id}...")
    
    # Abre a sessão com o PostgreSQL
    async with AsyncSessionLocal() as db:
        
        # 1. Reconhece o cliente (cria ou busca no banco)
        usuario = await crud.get_or_create_user(db, sender_id)
        
        # 2. Salva a mensagem que o cliente acabou de mandar
        await crud.save_message(db, usuario.id, "user", message_text)
        
        # 3. Resgata o histórico das últimas mensagens
        historico = await crud.get_historico_mensagens(db, usuario.id)
        
        # 4. Envia o histórico para a IA ler e formular a resposta
        print(f"🤖 Lendo contexto e pensando...")
        resposta_ia = await pensar_com_ia(historico)
        
        # 5. Salva a resposta da IA no banco de dados para a memória não se perder
        await crud.save_message(db, usuario.id, "ai", resposta_ia)
        
        # 6. Manda a resposta lá pro Instagram via API da Meta
        send_reply(sender_id, resposta_ia)




@app.get("/")
def home():
    return {"status": "Servidor rodando!"}

# ---------------------------------------------------------
# ROTA GET: Usada apenas uma vez para a Meta validar seu App
# ---------------------------------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verificado com sucesso pela Meta!")
        return Response(content=challenge, status_code=200)
    else:
        return Response(content="Token de verificação inválido", status_code=403)
    

# ---------------------------------------------------------
# ROTA POST: Onde as mensagens do Instagram vão chegar
# ---------------------------------------------------------
@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
        
        if payload.get("object") == "instagram":
            for entry in payload.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    
                    sender_id = messaging_event["sender"]["id"]
                    
                    # Ignora as mensagens que o próprio bot enviou
                    if sender_id == IG_BOT_ID:
                        continue # Usa continue para não travar o loop de eventos
                    
                    message_text = messaging_event.get("message", {}).get("text", "")
                    
                    if message_text:
                        print(f"👤 Usuário disse: {message_text}")
                        
                        # EM VEZ DE ESPERAR A IA AQUI, JOGAMOS PARA O BACKGROUND!
                        background_tasks.add_task(processar_mensagem_em_background, sender_id, message_text)

        # Retorna o 200 OK instantaneamente para a Meta não encher o saco!
        return Response(content="EVENT_RECEIVED", status_code=200)
        
    except Exception as e:
        print(f"Erro ao processar o webhook: {e}")
        return Response(content="Erro interno", status_code=500)
    

# --- FUNÇÃO QUE ENVIA A MENSAGEM DE VOLTA PARA A META ---
def send_reply(recipient_id, text_message):
    # A URL da API da Meta (Graph API)
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    headers = {"Content-Type": "application/json"}
    
    # O corpinho da mensagem que vai pro usuário
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text_message}
    }
    
    # Faz o POST mandando a resposta
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        print("✅ Resposta enviada com sucesso pro direct!")
    else:
        print(f"❌ Erro ao enviar resposta: {response.text}")