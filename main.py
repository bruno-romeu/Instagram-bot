import os
import traceback
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from dotenv import load_dotenv
from google import genai
from google.genai import types
from contextlib import asynccontextmanager
from database import engine, Base, AsyncSessionLocal
from telegram_service import enviar_para_aprovacao_telegram
import crud
import asyncio
import json
import textwrap
import feedparser
from PIL import Image, ImageDraw, ImageFont

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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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


PROMPT_CRIADOR_CARROSSEL = """
Você é um Copywriter e Estrategista de Redes Sociais de alto nível, trabalhando para o empresário Daniel Fabiano.
Sua função é criar scripts magnéticos para posts no formato CARROSSEL DE TEXTO no Instagram.
O foco são empresários que buscam multiplicar patrimônio, princípios cristãos nos negócios e excelência na gestão.

DIRETRIZES DE ESTILO:
- Evite linguagem robótica ou clichês de IA (ex: "desvendar", "mergulhar", "no cenário atual", "divisor de águas").
- Escreva como um empresário experiente conversando com outro empresário de forma direta, madura e sem rodeios.

ESTRUTURA DO CARROSSEL:
1. Uma legenda (Copy) persuasiva que vai na descrição do post, com emojis moderados e hashtags.
2. Um Array de 4 a 5 "slides".
3. O Slide 1 DEVE ser um Título/Hook muito forte (máximo de 15 palavras).
4. Os Slides intermediários devem desenvolver o raciocínio (máximo de 20 palavras por slide para caber bem na arte).
5. O último Slide DEVE ser uma CTA (Call to Action) clara.

REGRAS DE FORMATAÇÃO:
Você DEVE retornar APENAS um objeto JSON válido, sem nenhum texto adicional antes ou depois (sem markdown de ```json), com a seguinte estrutura exata:
{
    "tema": "Resumo do tema",
    "legenda": "A copy completa para a descrição do post do Instagram...",
    "slides": [
        {"numero": 1, "texto": "Hook impactante aqui"},
        {"numero": 2, "texto": "Desenvolvimento parte 1"},
        {"numero": 3, "texto": "Desenvolvimento parte 2"},
        {"numero": 4, "texto": "CTA finalizando o post"}
    ]
}
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



async def gerar_post_ia(noticias_do_dia: str):
    print("🧠 Analisando as notícias para criar um conteúdo original...")
    
    # O comando que instrui a IA a escolher o tema
    comando_dinamico = f"""
    Aqui estão as 5 principais notícias do mundo dos negócios hoje:
    
    {noticias_do_dia}
    
    TAREFA:
    1. Escolha UMA dessas notícias que seja mais relevante para empresários.
    2. Crie um post carrossel conectando essa notícia com a importância de ter excelência na gestão, princípios sólidos ou multiplicação de patrimônio (que são os pilares do Daniel Fabiano).
    3. Retorne no formato JSON exigido.
    """
    
    try:
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=comando_dinamico,
            config=types.GenerateContentConfig(
                system_instruction=PROMPT_CRIADOR_CARROSSEL, 
                response_mime_type="application/json",
            )
        )
        
        post_gerado = json.loads(response.text)
        return post_gerado

    except Exception as e:
        print(f"❌ Erro ao gerar conteúdo: {e}")
        return None
    

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
                    
                    message = messaging_event.get("message", {})
                    
                    if "reaction" in messaging_event:
                        print(f"👍 O usuário reagiu a uma mensagem.")
                        continue # Não precisamos responder a reações de mensagens
                    
                    attachments = message.get("attachments", [])
                    if attachments:
                        tipo_anexo = attachments[0].get("type")
                        print(f"📎 Usuário enviou um anexo do tipo: {tipo_anexo}")
                        
                        # Resposta elegante do Daniel para arquivos não suportados
                        resposta_anexo = "Agradeço o envio, mas por enquanto minha equipe configurou este canal apenas para texto. Poderia escrever sua dúvida ou mensagem para mim, por favor? 🤝"
                        
                        # Manda a resposta imediatamente
                        send_reply(sender_id, resposta_anexo)
                        continue # Pula para o próximo evento, não chama a IA
                    
                    # Se for TEXTO, segue o fluxo normal que criamos
                    message_text = message.get("text", "")
                    
                    if message_text:
                        print(f"👤 Usuário disse: {message_text}")
                        # Joga o processo para o background
                        background_tasks.add_task(processar_mensagem_em_background, sender_id, message_text)

        # Retorna o 200 OK instantaneamente para a Meta
        return Response(content="EVENT_RECEIVED", status_code=200)
        
    except Exception as e:
        print(f"❌ Erro ao processar o webhook: {e}")
        return Response(content="Erro interno", status_code=500)
    


def buscar_tendencias_empresariais():
    print("📰 Varrendo o mercado em busca de tendências quentes...")
    
    # URL do feed de Negócios do InfoMoney (você pode trocar por Forbes, Exame, etc.)
    url_rss = "https://www.infomoney.com.br/negocios/feed/"
    
    feed = feedparser.parse(url_rss)
    
    if not feed.entries:
        return "A importância da adaptabilidade em tempos de crise." # Fallback seguro caso a internet falhe
        
    noticias_do_dia = []
    
    # Pega as 5 notícias mais recentes do topo do portal
    for artigo in feed.entries[:5]:
        noticias_do_dia.append(f"- {artigo.title}")
        
    tendencias_formatadas = "\n".join(noticias_do_dia)
    
    print("✅ Tendências encontradas:")
    print(tendencias_formatadas)
    
    return tendencias_formatadas
    

@app.get("/testar-criacao-autonoma")
async def testar_criacao_autonoma():
    # 1. O código busca as notícias do dia sozinho
    tendencias = buscar_tendencias_empresariais()
    
    # 2. A IA lê as notícias, escolhe uma e gera a copy estruturada
    post_json = await gerar_post_ia(tendencias)
    
    if post_json:
        # 3. O Pillow desenha os slides
        arquivos_gerados = criar_slides_carrossel(post_json)

        enviar_para_aprovacao_telegram(arquivos_gerados, post_json["legenda"])
        
        return {
            "status": "sucesso", 
            "arquivos": arquivos_gerados,
            "mensagem": "Verifique o seu telegram para aprovar"
        }
    else:
        return {"status": "erro", "mensagem": "A IA falhou na criação."}
    


def criar_slides_carrossel(dados_post):
    print("🖌️ Iniciando a criação das imagens do carrossel...")
    
    caminho_template = "template_base.jpg"
    pasta_saida = "carrossel_pronto"
    
    # Cria uma pasta para não bagunçar seus arquivos
    if not os.path.exists(pasta_saida):
        os.makedirs(pasta_saida)

    caminhos_imagens = []

    # Carrega a fonte (Ajuste o nome do arquivo para a fonte que você baixou)
    try:
        fonte_path = "Montserrat-Bold.ttf" 
        fonte = ImageFont.truetype(fonte_path, size=55)
    except IOError:
        print("⚠️ Fonte não encontrada. Usando fonte padrão do sistema.")
        fonte = ImageFont.load_default()

    # O laço mágico: faz isso para cada slide do JSON
    for slide in dados_post["slides"]:
        numero = slide["numero"]
        texto = slide["texto"]

        # 1. Abre a imagem de fundo nova
        try:
            imagem = Image.open(caminho_template)
        except FileNotFoundError:
            print(f"❌ Erro: O arquivo {caminho_template} não foi encontrado.")
            return []

        draw = ImageDraw.Draw(imagem)
        largura_imagem, altura_imagem = imagem.size

        # 2. Quebra o texto em várias linhas (35 caracteres por linha, ajuste se precisar)
        linhas = textwrap.wrap(texto, width=35) 
        
        # 3. Calcula a altura total do bloco de texto para centralizar verticalmente
        bbox_fonte = draw.textbbox((0, 0), "A", font=fonte)
        altura_linha = bbox_fonte[3] - bbox_fonte[1] + 15 # 15px de espaçamento entre linhas
        altura_total_texto = altura_linha * len(linhas)
        
        eixo_y_atual = (altura_imagem - altura_total_texto) / 2

        # 4. Desenha cada linha centralizada horizontalmente
        for linha in linhas:
            bbox_linha = draw.textbbox((0, 0), linha, font=fonte)
            largura_linha = bbox_linha[2] - bbox_linha[0]
            
            eixo_x = (largura_imagem - largura_linha) / 2
            
            # Desenha o texto em branco puro
            draw.text((eixo_x, eixo_y_atual), linha, font=fonte, fill=(255, 255, 255))
            
            eixo_y_atual += altura_linha

        # 5. Salva a imagem finalizada na pasta
        nome_arquivo = f"{pasta_saida}/slide_{numero}.png"
        imagem.save(nome_arquivo)
        caminhos_imagens.append(nome_arquivo)
        
        print(f"✅ Slide {numero} gerado: {nome_arquivo}")

    return caminhos_imagens


@app.post("/webhook-telegram")
async def telegram_webhook(request: Request):
    print("🔔 [RAIO-X] O TELEGRAM BATEU NA PORTA!", flush=True)
    
    try:
        dados = await request.json()
        print(f"📦 [RAIO-X] Pacote recebido: {dados}", flush=True)
        
        if "callback_query" in dados:
            callback = dados["callback_query"]
            acao = callback["data"] 
            chat_id = callback["message"]["chat"]["id"]
            
            print(f"👉 [RAIO-X] Você clicou no botão: {acao}", flush=True)
            
            url_mensagem = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            
            if acao == "aprovar_post":
                print("✅ [RAIO-X] Tentando enviar mensagem de APROVADO...", flush=True)
                resposta = requests.post(url_mensagem, data={
                    'chat_id': chat_id, 
                    'text': "🚀 Post aprovado! Iniciando o protocolo de publicação no Instagram..."
                })
                print(f"📡 Status da resposta do Telegram: {resposta.status_code}", flush=True)
                
            elif acao == "recusar_post":
                print("❌ [RAIO-X] Tentando enviar mensagem de RECUSADO...", flush=True)
                requests.post(url_mensagem, data={
                    'chat_id': chat_id, 
                    'text': "🗑️ Post descartado. Fique à vontade para gerar uma nova opção."
                })
                
            url_answer = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
            requests.post(url_answer, data={'callback_query_id': callback['id']})

        return {"status": "ok"}

    except Exception as e:
        # Se qualquer coisa der errado, ele vai gritar o erro no terminal
        print(f"🚨 [RAIO-X] DEU ERRO NO CÓDIGO: {e}", flush=True)
        traceback.print_exc()
        return {"status": "erro"}