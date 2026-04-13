import ollama
import time

SYSTEM_PROMPT = """Tu es BCEAO Intelligence, analyste UEMOA.
Règles : réponds UNIQUEMENT depuis le contexte fourni. Si absent, dis exactement : "Je ne trouve pas cette information dans les documents BCEAO disponibles." Ne jamais inventer. Réponds en français. Cite la source : 📄 [Titre] — [année]."""

CONTEXT = "Le Gouverneur de la BCEAO est chargé de la direction des services de la Banque centrale. Il préside le Conseil d'Administration et le Comité de Politique Monétaire."

def test_ollama_rag():
    print("Testing Ollama with Context...")
    user_message = f"Contexte BCEAO :\n{CONTEXT}\n\nQuestion : Explique moi le rôle du gouverneur.\nRéponse directe et sourcée :"
    
    start = time.time()
    try:
        response = ollama.chat(model='qwen2.5:1.5b', messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_message},
        ])
        print(f"Response: {response['message']['content']}")
        print(f"Time: {time.time() - start:.4f}s")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ollama_rag()
