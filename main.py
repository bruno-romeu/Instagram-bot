import os
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from dotenv import load_dotenv
from google import genai
from google.genai import types
from contextlib import asynccontextmanager
from database import engine, Base
import models


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
def pensar_com_ia(mensagem_do_usuario):
    try:
        # Aqui você define QUEM o bot é! Altere esse texto como quiser.
        personalidade = """Você é um assistente virtual de atendimento para um perfil do Instagram. 
        Seja sempre muito educado, prestativo e use emojis. 
        Mantenha suas respostas curtas, pois estão sendo lidas em uma DM de celular."""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=mensagem_do_usuario,
            config=types.GenerateContentConfig(
                system_instruction=personalidade,
            )
        )
        return response.text
    except Exception as e:
        print(f"Erro na IA: {e}")
        return "Ops, meu cérebro deu um curto-circuito! 🤯 Tente novamente em instantes."
    

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
def processar_mensagem_em_background(sender_id, message_text):
    print(f"🧠 Processando em background a mensagem de {sender_id}...")
    # 1. Manda a mensagem pra IA pensar
    resposta_ia = pensar_com_ia(message_text)
    print(f"🤖 IA respondeu: {resposta_ia}")
    
    # 2. Manda a resposta da IA de volta pro Instagram
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