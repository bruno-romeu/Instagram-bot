import os
from google import genai
from dotenv import load_dotenv

# Carrega as chaves do .env
load_dotenv()

# Inicia o cliente com a nova biblioteca do Google
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("🧠 Pensando...")

try:
    # Passamos o modelo 'gemini-2.5-flash' que está disponível na sua lista
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents="Fale como um pirata e me dê boas-vindas ao mundo da Inteligência Artificial!"
    )
    
    print("\n🤖 Resposta da IA:")
    print(response.text)
    
except Exception as e:
    print(f"\n❌ Erro ao gerar conteúdo: {e}")