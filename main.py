from fastapi import FastAPI, Request, Response
import requests
import os

app = FastAPI()

#usar essa mesma senha lá no painel da Meta.
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
IG_BOT_ID = os.getenv("IG_BOT_ID")


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
async def receive_message(request: Request):
    try:
        payload = await request.json()
        
        if payload.get("object") == "instagram":
            for entry in payload.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    
                    sender_id = messaging_event["sender"]["id"]
                    
                    # --- A TRAVA DE SEGURANÇA AQUI ---
                    # Se quem mandou a mensagem foi o próprio bot, a gente ignora!
                    if sender_id == IG_BOT_ID:
                        return Response(content="EVENT_RECEIVED", status_code=200)
                    
                    message_text = messaging_event.get("message", {}).get("text", "")
                    
                    print(f"Mensagem recebida de {sender_id}: {message_text}")
                    
                    if message_text:
                        send_reply(sender_id, f"Recebi sua mensagem: '{message_text}'. Meu bot tá vivo e não fala mais sozinho! 🤖")

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