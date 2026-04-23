import requests
import json
import os
from dotenv import load_dotenv
from fastapi import Request

load_dotenv()

# Substitua pelas suas chaves (o ideal no futuro é colocar isso num arquivo .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def enviar_para_aprovacao_telegram(caminhos_imagens, legenda):
    print("📲 Preparando envio para o Telegram...")
    
    # PASSO 1: Enviar o Carrossel (Álbum de imagens)
    url_media = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
    media_group = []
    arquivos_abertos = {}
    
    # Preparamos as imagens para o upload
    for i, caminho in enumerate(caminhos_imagens):
        nome_arquivo = f"imagem_{i}"
        arquivos_abertos[nome_arquivo] = open(caminho, 'rb')
        media_group.append({
            'type': 'photo',
            'media': f'attach://{nome_arquivo}'
        })
        
    try:
        # Dispara as fotos para o seu chat
        requests.post(url_media, data={'chat_id': CHAT_ID, 'media': json.dumps(media_group)}, files=arquivos_abertos)
    finally:
        # Boa prática: sempre fechar os arquivos abertos
        for f in arquivos_abertos.values():
            f.close()

    # PASSO 2: Enviar a Legenda e os Botões
    url_mensagem = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Criando os botões interativos
    botoes = {
        "inline_keyboard": [
            [
                {"text": "✅ Aprovar e Postar", "callback_data": "aprovar_post"},
                {"text": "❌ Recusar", "callback_data": "recusar_post"}
            ]
        ]
    }
    
    texto_mensagem = f"🔥 *Novo Post Pronto para Aprovação:*\n\n{legenda}"
    
    dados_mensagem = {
        'chat_id': CHAT_ID,
        'text': texto_mensagem,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(botoes)
    }
    
    resposta = requests.post(url_mensagem, data=dados_mensagem)
    
    if resposta.status_code == 200:
        print("✅ Post enviado com sucesso para o seu celular!")
    else:
        print(f"❌ Erro ao enviar mensagem: {resposta.text}")