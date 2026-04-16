import os
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from dotenv import load_dotenv
from google import genai
from google.genai import types
from contextlib import asynccontextmanager
from database import engine, Base, AsyncSessionLocal
import models
import crud
import asyncio

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

# Credenciais
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
IG_BOT_ID = os.getenv("IG_BOT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Inicializa o cliente novo do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------- A ALMA DO BOT ----------------
SYSTEM_PROMPT = """
Você é o assistente virtual premium da equipe do Daniel Fabiano (@eusoudanielfabiano).
Sua missão é atender os seguidores do Instagram com excelência, tirar dúvidas básicas e, principalmente, qualificar e direcionar empresários para as mentorias e para o Mastermind Embaixadores.

CONTEXTO SOBRE O DANIEL FABIANO:
- Empresário, Mentor e Investidor.
- CVO de 19 empresas (sendo 6 multimilionárias).
- Ecossistema presente em 96 cidades.
- Foco principal: Ajudar empresários a multiplicar patrimônio de forma sólida.
- Valores da marca: Negócios de alto nível, família, princípios cristãos, excelência e execução estratégica (o que é útil x importante x urgente).

TOM DE VOZ E ESTILO:
- Profissional, elegante, respeitoso, encorajador e direto ao ponto.
- Você conversa de igual para igual com empresários. Não use gírias excessivas ou linguagem infantil.
- Use emojis de forma moderada e estratégica (ex: 🚀, 💼, 🤝, 📊).
- Respostas curtas e escaneáveis (é um chat de Instagram, ninguém lê textões).

DIRETRIZES DE ATENDIMENTO E VENDAS:
1. Se a pessoa perguntar sobre mentorias ou o Mastermind Embaixadores, elogie a decisão de buscar crescimento e envie o link de aplicação: {TYPEFORM_LINK}. Explique que é um grupo exclusivo e que a equipe fará uma seleção.
2. NUNCA invente preços, datas ou promessas de ganhos financeiros. Se não souber a resposta exata, diga: "Para essa questão específica, vou pedir para um dos nossos assessores humanos entrar em contato com você por aqui. Pode aguardar um instante?"
3. Se o usuário for desrespeitoso ou fizer perguntas fora do escopo (ex: piadas, fofocas), redirecione o assunto para negócios de forma polida ou encerre o assunto elegantemente.
4. Lembre-se do histórico da conversa para não repetir saudações ou fazer as mesmas perguntas.

Sua meta final é sempre gerar valor e facilitar a ponte entre os seguidores qualificados e os produtos do Daniel.
"""

# ---------------- CÉREBRO DA IA ----------------
async def pensar_com_ia(historico_mensagens, max_tentativas=3):
        # Transforma as mensagens do banco de dados em um texto de roteiro de teatro
        texto_historico = "Histórico recente da conversa:\n"
        for msg in historico_mensagens:
            quem = "Cliente" if msg.remetente == "user" else "Você"
            texto_historico += f"{quem}: {msg.conteudo}\n"
            
        texto_historico += "Você: " # Deixa a "deixa" para a IA responder

        # O novo SDK do Google tem um método .aio para rodar de forma assíncrona
        for tentativa in range(max_tentativas):
            try:
                response = await client.aio.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=texto_historico,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                    )
                )
                return response.text
                
            except Exception as e:
                erro_str = str(e).upper()
                # Se for erro de servidor ocupado (503), tentamos novamente
                if "503" in erro_str or "UNAVAILABLE" in erro_str:
                    tempo_espera = 2 ** tentativa # Espera 1s, depois 2s, depois 4s...
                    print(f"⚠️ API do Google ocupada. Tentativa {tentativa + 1} de {max_tentativas}. Aguardando {tempo_espera}s...")
                    await asyncio.sleep(tempo_espera)
                else:
                    # Se for outro erro (ex: chave inválida, sem internet), para de tentar e printa o erro
                    print(f"❌ Erro grave na IA: {e}")
                    break

        # Se esgotar as tentativas ou der um erro grave, manda a mensagem de fallback elegante
        return "Para essa questão, vou pedir para nossa equipe humana te auxiliar por aqui. Aguarde um instante, por favor."

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

# ---------------- FLUXO PRINCIPAL ----------------
async def processar_mensagem_em_background(sender_id, message_text):
    print(f"🧠 Abrindo conexão com o banco para {sender_id}...")
    
    async with AsyncSessionLocal() as db:
        # 1. Reconhece o cliente (cria ou busca no banco)
        usuario = await crud.get_or_create_user(db, sender_id)
        
        # 2. Salva a mensagem que o cliente acabou de mandar
        await crud.save_message(db, usuario.id, "user", message_text)
        
        # 3. Resgata o histórico (que agora JÁ INCLUI a mensagem do passo 2)
        historico = await crud.get_historico_mensagens(db, usuario.id)
        
        # 4. Envia o histórico para a IA ler e formular a resposta
        print(f"🤖 Lendo contexto e pensando...")
        resposta_ia = await pensar_com_ia(historico)
        
        # 5. Salva a resposta da IA no banco de dados para a memória não se perder
        await crud.save_message(db, usuario.id, "ai", resposta_ia)
        
        # 6. Manda a resposta lá pro Instagram via API da Meta
        send_reply(sender_id, resposta_ia)

# ---------------- ROTAS FASTAPI ----------------
@app.get("/")
def home():
    return {"status": "Servidor rodando!"}

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
                        continue 
                    
                    message_text = messaging_event.get("message", {}).get("text", "")
                    
                    if message_text:
                        print(f"👤 Usuário disse: {message_text}")
                        # Joga o processo para o background
                        background_tasks.add_task(processar_mensagem_em_background, sender_id, message_text)

        # Retorna o 200 OK instantaneamente para a Meta
        return Response(content="EVENT_RECEIVED", status_code=200)
        
    except Exception as e:
        print(f"Erro ao processar o webhook: {e}")
        return Response(content="Erro interno", status_code=500)