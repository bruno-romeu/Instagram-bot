from glob import glob
import os
import traceback
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
import cloudinary
import cloudinary.uploader

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

pasta_imagens = "carrossel_pronto"
if not os.path.exists(pasta_imagens):
    os.makedirs(pasta_imagens)

# Credenciais
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
IG_BOT_ID = os.getenv("IG_BOT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Inicializa o cliente novo do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Armazena o último post gerado para ser usado na aprovação do Telegram
ultimo_post_gerado = {"legenda": None, "arquivos": []}
_mids_processados: set = set()


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
    if not IG_BOT_ID:
        print("❌ ERRO: IG_BOT_ID não configurado no .env")
        return

    # Retornando ao ID fixo. O erro #3 é resolvido com o toggle 'Allow Access to Messages' no App do Instagram.
    url = f"https://graph.facebook.com/v21.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text_message}
    }
    
    response = requests.post(url, params=params, json=data, headers=headers)
    if response.status_code == 200:
        print(f"✅ Resposta enviada com sucesso para {recipient_id}!")
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


async def responder_comentario_instagram(comment_id: str, texto_usuario: str, username: str):
    print(f"💬 Analisando comentário de @{username}: '{texto_usuario}'")
    
    prompt_comentario = f"""
    Você é o assistente virtual da equipe do empresário e mentor Daniel Fabiano (@eusoudanielfabiano).
    Sua missão é interagir com os seguidores nos comentários das postagens de forma premium, educada e estratégica.
    
    Um usuário chamado @{username} acabou de comentar o seguinte no nosso post: "{texto_usuario}"
    
    DIRETRIZES PARA A RESPOSTA:
    - Seja humano, maduro e direto ao ponto (você fala com outros empresários).
    - Agradeça, concorde ou agregue um pequeno valor ao que a pessoa disse.
    - Resposta curta! No máximo 1 ou 2 frases.
    - Use 1 ou 2 emojis elegantes (ex: 🚀, 🤝, 🎯, 💼, 🔥).
    - Não use hashtags.
    - NUNCA ofereça links de vendas nos comentários a não ser que a pessoa peça explicitamente.
    
    Retorne APENAS o texto da resposta, sem aspas ou textos adicionais.
    """
    
    try:
        resposta_ia = await client.aio.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt_comentario,
        )
        
        texto_resposta = resposta_ia.text.strip()
        print(f"🤖 Resposta gerada para @{username}: {texto_resposta}")
        
        # 2. Envia a resposta para a Meta usando o endpoint correto de replies
        url = f"https://graph.facebook.com/v19.0/{comment_id}/replies"
        payload = {
            "message": texto_resposta,
            "access_token": PAGE_ACCESS_TOKEN
        }
        
        resposta_meta = requests.post(url, data=payload).json()
        
        if "id" in resposta_meta:
            print(f"✅ Comentário de @{username} respondido com sucesso!")
        else:
            print(f"❌ Erro ao responder comentário: {resposta_meta}")
            
    except Exception as e:
        print(f"❌ Erro na IA ao responder comentário: {e}")

# ---------------- ROTAS FASTAPI ----------------
@app.get("/")
def home():
    return {"status": "Servidor rodando!"}

@app.get("/robots.txt")
async def robots():
    return Response(content="User-agent: *\nAllow: /", media_type="text/plain")

@app.get("/imagens/{nome_arquivo}")
async def servir_imagem(nome_arquivo: str):
    caminho_arquivo = os.path.join(pasta_imagens, nome_arquivo)
    
    if os.path.exists(caminho_arquivo):
        return FileResponse(caminho_arquivo, media_type="image/png")
    
    return Response(content="Imagem não encontrada", status_code=404)

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
        print(f"📥 Payload recebido do webhook: {json.dumps(payload, indent=2)}")
        
        if payload.get("object") == "instagram":
            for entry in payload.get("entry", []):
                # Processa DMs
                if "messaging" in entry:
                    for messaging_event in entry.get("messaging", []):
                        # Ignora eventos sem sender (read receipts, echos, etc)
                        if "sender" not in messaging_event:
                            continue
                        
                        sender_id = messaging_event["sender"]["id"]
                        
                        if sender_id == IG_BOT_ID:
                            continue
                        
                        # Ignora echos (mensagens enviadas pelo próprio bot)
                        message = messaging_event.get("message", {})
                        if message.get("is_echo"):
                            continue
                        
                        if "reaction" in messaging_event:
                            continue
                        
                        attachments = message.get("attachments", [])
                        if attachments:
                            send_reply(sender_id, "Agradeço o envio, mas por enquanto minha equipe configurou este canal apenas para texto. Poderia escrever sua dúvida ou mensagem para mim, por favor? 🤝")
                            continue
                        
                        mid = message.get("mid", "")
                        if mid and mid in _mids_processados:
                            print(f"⏭️ Mensagem duplicada ignorada (mid): {mid[:30]}...")
                            continue
                        if mid:
                            _mids_processados.add(mid)
                            if len(_mids_processados) > 500:
                                _mids_processados.pop()

                        message_text = message.get("text", "")
                        if message_text:
                            print(f"👤 Usuário {sender_id} disse: {message_text}")
                            background_tasks.add_task(processar_mensagem_em_background, sender_id, message_text)
                # Processa Comentários
                if "changes" in entry:
                    for change in entry.get("changes", []):
                        if change.get("field") == "comments":
                            valor = change.get("value", {})
                            print(f"💬 Novo comentário detectado: {valor}")
                            
                            comment_id = valor.get("id")
                            texto_comentario = valor.get("text")
                            from_data = valor.get("from", {})
                            username = from_data.get("username", "usuário")
                            from_id = from_data.get("id", "")
                            
                            if from_id == IG_BOT_ID or username == "eusoudanielfabiano":
                                print(f"⏭️ Ignorando comentário do próprio bot/perfil.")
                                continue
                                
                            if texto_comentario and comment_id:
                                background_tasks.add_task(
                                    responder_comentario_instagram, 
                                    comment_id, 
                                    texto_comentario, 
                                    username
                                )
        return Response(content="EVENT_RECEIVED", status_code=200)
    except Exception as e:
        print(f"❌ Erro ao processar o webhook: {traceback.format_exc()}")
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

        # Salva o post atual em memória para ser recuperado na aprovação do Telegram
        ultimo_post_gerado["legenda"] = post_json["legenda"]
        ultimo_post_gerado["arquivos"] = arquivos_gerados

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
        nome_arquivo = f"{pasta_saida}/slide_{numero}.jpg"
        imagem.save(nome_arquivo, "JPEG", quality=85)
        caminhos_imagens.append(nome_arquivo)
        
        print(f"✅ Slide {numero} gerado: {nome_arquivo}")

    return caminhos_imagens


@app.post("/webhook-telegram")
async def telegram_webhook(request: Request):
    print("🔔 [RAIO-X] O TELEGRAM BATEU NA PORTA!", flush=True)
    
    try:
        dados = await request.json()
        
        if "callback_query" in dados:
            callback = dados["callback_query"]
            acao = callback["data"] 
            chat_id = callback["message"]["chat"]["id"]
            
            
            url_mensagem = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            
            if acao == "aprovar_post":
                requests.post(url_mensagem, data={
                    'chat_id': chat_id, 
                    'text': "🚀 Post aprovado! Iniciando o protocolo de publicação no Instagram..."
                })
                
                url_base_ngrok = str(request.base_url).replace("http://", "https://")
                
                # Usa os arquivos e a legenda real do último post gerado
                caminhos_atuais = ultimo_post_gerado["arquivos"]
                legenda_real = ultimo_post_gerado["legenda"] or "🔥 Novo post! #business #sucesso"
                
                asyncio.create_task(publicar_carrossel_instagram(caminhos_atuais, legenda_real, url_base_ngrok))
                
            elif acao == "recusar_post":
                requests.post(url_mensagem, data={
                    'chat_id': chat_id, 
                    'text': "🗑️ Post descartado. Fique à vontade para gerar uma nova opção."
                })
                
                # Limpa os slides da pasta para não acumular arquivos antigos
                for arquivo in glob("carrossel_pronto/*.jpg"):
                    os.remove(arquivo)
                ultimo_post_gerado["legenda"] = None
                ultimo_post_gerado["arquivos"] = []
                print("🧹 Slides antigos removidos da pasta.")
                
            url_answer = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
            requests.post(url_answer, data={'callback_query_id': callback['id']})

        return {"status": "ok"}

    except Exception as e:
        # Se qualquer coisa der errado, ele vai gritar o erro no terminal
        print(f"🚨 [RAIO-X] DEU ERRO NO CÓDIGO: {e}", flush=True)
        traceback.print_exc()
        return {"status": "erro"}
    

def hospedar_imagem_cloudinary(caminho_imagem):
    print(f"Subindo {caminho_imagem} para o Cloudinary...")
    
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET")
    )
    
    try:
        resultado = cloudinary.uploader.upload(caminho_imagem)
        link = resultado.get("secure_url")
        print(f"✅ Link gerado: {link}")
        return link
    except Exception as e:
        print(f"❌ Erro no Cloudinary: {e}")
        return None


async def publicar_carrossel_instagram(caminhos_imagens, legenda, url_base):
    print("Iniciando protocolo de publicação na Meta API...")
    
    # Precisamos do ID da sua conta do Instagram (pode ser o mesmo IG_BOT_ID dependendo de como você pegou, 
    # mas o correto é o Instagram Business Account ID)
    IG_ACCOUNT_ID = os.getenv("IG_BOT_ID") 
    ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
    
    ids_das_imagens = []
    
    # --- PASSO 1: Criar os "Item Containers" (um para cada imagem) ---
    for caminho in caminhos_imagens:
        
        # 1. Fazemos o upload para a nuvem ninja e pegamos o link blindado
        url_imagem_publica = hospedar_imagem_cloudinary(caminho)
        
        if not url_imagem_publica:
            return False # Se falhar, aborta a missão
            
        print(f"📡 Subindo imagem para os servidores da Meta: {url_imagem_publica}")
        
        url_upload = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
        payload_upload = {
            "image_url": url_imagem_publica,
            "is_carousel_item": "true",
            "access_token": ACCESS_TOKEN
        }
        
        resposta_upload = requests.post(url_upload, data=payload_upload).json()
        
        if "id" in resposta_upload:
            ids_das_imagens.append(resposta_upload["id"])
            print("Dando 5 segundos de respiro pro servidor do Instagram e do Catbox...")
            await asyncio.sleep(5)
        else:
            print(f"❌ Erro ao subir imagem: {resposta_upload}")
            return False

    # --- PASSO 2: Criar o "Carousel Container" ---
    url_container = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media"
    payload_container = {
        "media_type": "CAROUSEL",
        "children": ",".join(ids_das_imagens),
        "caption": legenda,
        "access_token": ACCESS_TOKEN
    }
    
    resposta_container = requests.post(url_container, data=payload_container).json()
    
    if "id" not in resposta_container:
        print(f"❌ Erro ao criar o container do carrossel: {resposta_container}")
        return False
        
    container_id = resposta_container["id"]
    print("✅ Carrossel montado! ID:", container_id)

    # --- PASSO 3: Publicar de Verdade ---
    print("Publicando...")
    url_publish = f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish"
    payload_publish = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    
    resposta_publish = requests.post(url_publish, data=payload_publish).json()
    
    if "id" in resposta_publish:
        print("Post publicado!")
        # Limpa os slides da pasta após publicação bem-sucedida
        for arquivo in glob("carrossel_pronto/*.jpg"):
            os.remove(arquivo)
        ultimo_post_gerado["legenda"] = None
        ultimo_post_gerado["arquivos"] = []
        print("🧹 Slides publicados removidos da pasta.")
        return True
    else:
        print(f"❌ Erro na publicação final: {resposta_publish}")
        return False