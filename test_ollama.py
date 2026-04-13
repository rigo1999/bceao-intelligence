import ollama
import time

def test_ollama():
    print("Testing Ollama direct...")
    start = time.time()
    try:
        response = ollama.chat(model='qwen2.5:1.5b', messages=[
            {'role': 'user', 'content': 'Salut, comment vas-tu ?'},
        ])
        print(f"Response: {response['message']['content']}")
        print(f"Time: {time.time() - start:.4f}s")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ollama()
