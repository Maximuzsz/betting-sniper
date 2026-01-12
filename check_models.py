import os
import google.generativeai as genai
from dotenv import load_dotenv

# Carrega a chave do arquivo .env
load_dotenv()
api_key = os.getenv("GEMINI_KEY")

if not api_key:
    print("❌ Erro: Chave GEMINI_API_KEY não encontrada no arquivo .env")
    exit()

print(f"🔑 Usando chave: {api_key[:5]}...{api_key[-3:]}")
print("CONNECTING TO GOOGLE AI STUDIO...")

try:
    genai.configure(api_key=api_key)
    
    print("\n📋 MODELOS DISPONÍVEIS PARA VOCÊ:")
    print("-" * 40)
    
    # Lista apenas modelos que suportam geração de texto (generateContent)
    count = 0
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ {m.name}")
            # Mostra detalhes extras se for um modelo Flash ou Pro
            if 'flash' in m.name or 'pro' in m.name:
                print(f"   L Input Limit: {m.input_token_limit}")
            count += 1
            
    print("-" * 40)
    print(f"Total de modelos encontrados: {count}")

except Exception as e:
    print(f"\n❌ Erro ao listar modelos: {e}")
    print("Verifique se sua chave está ativa em https://aistudio.google.com/")