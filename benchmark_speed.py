import time
import sys
import os

# Measure startup
start_imports = time.time()
from src.rag.pipeline import get_retriever, run_query_stream, MARKER_LOCAL, MARKER_WEB, MARKER_CACHE
import ollama
from settings import EMBEDDING_MODEL
end_imports = time.time()
print(f"Imports took: {end_imports - start_imports:.4f}s")

def measure_pipeline(question):
    print(f"\n--- Testing question: '{question}' ---")
    start_total = time.time()
    
    # 1. Embedding
    start_emb = time.time()
    try:
        q_embedding = ollama.embeddings(model=EMBEDDING_MODEL, prompt=question).embedding
        end_emb = time.time()
        print(f"1. Embedding: {end_emb - start_emb:.4f}s")
    except Exception as e:
        print(f"1. Embedding FAILED: {e}")
        return

    # 2. Retrieval
    start_ret = time.time()
    retriever = get_retriever()
    if retriever:
        docs = retriever.invoke(question)
        end_ret = time.time()
        print(f"2. VectorStore Retrieval: {end_ret - start_ret:.4f}s")
    else:
        print("2. VectorStore Retrieval: SKIPPED (No retriever)")
    
    # 3. LLM Streaming
    print("3. LLM Streaming performance:")
    start_stream = time.time()
    first_token_time = None
    tokens_count = 0
    
    try:
        for token in run_query_stream(question):
            if token in [MARKER_LOCAL, MARKER_WEB, MARKER_CACHE]:
                continue
            if not first_token_time:
                first_token_time = time.time()
                print(f"   - Time to first token: {first_token_time - start_stream:.4f}s")
            tokens_count += 1
            # print(token, end="", flush=True)
    except Exception as e:
        print(f"   - Error during streaming: {e}")
    
    end_total = time.time()
    print(f"\nTotal time: {end_total - start_total:.4f}s")
    if tokens_count > 0:
        print(f"Tokens received: {tokens_count}")

if __name__ == "__main__":
    # Test a unique question to avoid cache (adding timestamp)
    unique_q = f"Explique moi le role du gouverneur de la BCEAO en 3 points précis. (ID:{time.time()})"
    measure_pipeline(unique_q)
