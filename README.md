# BCEAO Intelligence — RAG local sur documents officiels

Assistant IA local permettant d'interroger les documents officiels de la BCEAO (rapports de politique monétaire, bulletins statistiques, communiqués) en langage naturel.

**Zéro fuite de données — tout tourne en local avec Ollama.**

---

## Architecture

```
[PDF / HTML]  →  PyMuPDF  →  Chunking (400 chars)  →  Filtre qualité
              →  all-minilm (Ollama batch embed)  →  ChromaDB

[Question]  →  Cache sémantique (SQLite)
            →  Query expansion + Static facts
            →  ChromaDB similarity search (TOP_K=4)
            →  qwen2.5:1.5b (Ollama)  →  Réponse sourcée (SSE stream)
```

## Stack

| Composant | Technologie |
|-----------|-------------|
| LLM | `qwen2.5:1.5b` via Ollama (local, CPU) |
| Embeddings | `all-minilm` via Ollama batch `/api/embed` |
| Vector store | ChromaDB |
| Backend | FastAPI + Server-Sent Events |
| Frontend | React + Vite |
| PDF parsing | PyMuPDF |
| Scraping | BeautifulSoup + Requests |
| Cache | SQLite (exact SHA256 + cosine similarity ≥ 0.92) |

> **Note :** Ce projet tourne sur CPU sans GPU dédié. Les appels Ollama utilisent des sockets TCP directs (contournement d'un bug Python 3.14 / urllib3). Voir `RECOMMENDATIONS.md` pour le contexte.

---

## Installation

### Prérequis

- Python 3.10–3.12 recommandé (3.14 fonctionne avec contournements)
- [Ollama](https://ollama.com) installé et en cours d'exécution
- Node.js 18+

### 1. Cloner et installer les dépendances Python

```bash
git clone <repo>
cd bceao-rag

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Télécharger les modèles Ollama

```bash
ollama pull qwen2.5:1.5b
ollama pull all-minilm
```

### 3. Configurer l'environnement

```bash
cp .env.example .env
# Éditer .env si besoin (les valeurs par défaut fonctionnent en local)
```

### 4. Installer le frontend

```bash
cd frontend
npm install
cd ..
```

---

## Utilisation

### Lancer le système complet

```bash
# Option 1 — script Windows
start.bat

# Option 2 — manuellement
# Terminal 1 : backend
python main.py app

# Terminal 2 : frontend
cd frontend && npm run dev
```

L'interface est accessible sur **http://localhost:5173**

### Scraper et indexer les documents BCEAO

```bash
# Scraper les documents depuis bceao.int
python main.py scrape

# Indexer dans ChromaDB (à relancer après chaque scraping)
python main.py ingest
```

---

## Structure du projet

```
bceao-rag/
├── src/
│   ├── scraper/          # Scraping bceao.int (BeautifulSoup)
│   ├── ingestion/        # PDF parsing + chunking + indexation ChromaDB
│   ├── rag/              # Pipeline RAG (pipeline.py — cœur du système)
│   └── interface/        # Interface Streamlit (legacy)
├── frontend/             # Interface React + Vite
├── data/                 # (non versionné)
│   ├── raw/              # PDFs téléchargés
│   ├── vectorstore/      # Base ChromaDB
│   └── response_cache.db # Cache sémantique SQLite
├── prompts.py            # Prompts système, détection salutations
├── settings.py           # Chargement .env
├── main.py               # Point d'entrée CLI
├── api.py                # Routes FastAPI
├── .env.example          # Template configuration
└── RECOMMENDATIONS.md    # Défis techniques et recommandations
```

---

## Configuration (`.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen2.5:1.5b
EMBEDDING_MODEL=all-minilm

DATA_DIR=./data
RAW_DIR=./data/raw
VECTORSTORE_DIR=./data/vectorstore

CHUNK_SIZE=400
CHUNK_OVERLAP=40
TOP_K_RETRIEVAL=4

BCEAO_BASE_URL=https://www.bceao.int
REQUEST_DELAY=2
```

---

## Performances (sur CPU, sans GPU)

| Métrique | Valeur |
|----------|--------|
| Temps de réponse (première question) | 15–25 secondes |
| Temps de réponse (cache) | < 1 seconde |
| Chunks indexés | 7 234 |
| Temps d'indexation complète | ~12 minutes |

---

## Limites connues

- **Python 3.14** : LangChain/Ollama non fonctionnel → sockets TCP directs en place
- **Sans GPU** : `qwen2.5:1.5b` uniquement viable → hallucinations possibles (~15%)
- **Recherche dense uniquement** : vocabulary mismatch atténué par query expansion + faits statiques
- Migration recommandée : Python 3.12 + GPU RTX 3060 ou cloud (voir `RECOMMENDATIONS.md`)

---

## Licence

Usage interne. Les documents indexés sont des publications officielles publiques de la [BCEAO](https://www.bceao.int).
