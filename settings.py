from dotenv import load_dotenv
import os

load_dotenv()

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL       = os.getenv("LLM_MODEL", "qwen2.5:1.5b")
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Chemins
DATA_DIR         = os.getenv("DATA_DIR", "./data")
RAW_DIR          = os.getenv("RAW_DIR", "./data/raw")
PROCESSED_DIR    = os.getenv("PROCESSED_DIR", "./data/processed")
VECTORSTORE_DIR  = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")

# RAG
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE", 300))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP", 30))
TOP_K_RETRIEVAL  = int(os.getenv("TOP_K_RETRIEVAL", 2))

# Scraping
BCEAO_BASE_URL   = os.getenv("BCEAO_BASE_URL", "https://www.bceao.int")
REQUEST_DELAY    = int(os.getenv("REQUEST_DELAY", 2))
