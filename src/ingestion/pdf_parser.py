"""
BCEAO RAG — Étape 2 : Ingestion
Parsing des documents (PDF, HTML) -> Chunking -> Vector Store (ChromaDB)
"""

import os
import json
from pathlib import Path
from loguru import logger
from tqdm import tqdm

from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from settings import (
    RAW_DIR, VECTORSTORE_DIR, EMBEDDING_MODEL, OLLAMA_BASE_URL,
    CHUNK_SIZE, CHUNK_OVERLAP
)
from src.rag.pipeline import OllamaEmbeddingsDirect

def _is_valid_chunk(text: str) -> bool:
    """Filtre les chunks inutilisables pour le RAG."""
    t = text.strip()
    if len(t) < 80:
        return False  # trop court (numéro de page, entête vide)
    # Trop de points consécutifs → table des matières
    if t.count("..") / max(len(t), 1) > 0.15:
        return False
    # Trop de chiffres → tableau statistique sans texte
    digits = sum(c.isdigit() for c in t)
    if digits / max(len(t), 1) > 0.5:
        return False
    # Trop peu de lettres → bruit (symboles, tableaux purs)
    letters = sum(c.isalpha() for c in t)
    if letters / max(len(t), 1) < 0.3:
        return False
    return True


def run_ingestion():
    """Charge les documents de data/raw/, les découpe et les indexe dans ChromaDB."""
    
    raw_dir = Path(RAW_DIR)
    index_file = raw_dir / "index.json"
    
    if not index_file.exists():
        logger.error(f"Fichier index.json non trouvé dans {raw_dir}. Lancez le scraping d'abord.")
        return

    # 1. Charger l'index des documents
    with open(index_file, "r", encoding="utf-8") as f:
        docs_metadata = json.load(f)
    
    logger.info(f"Démarrage de l'ingestion de {len(docs_metadata)} documents...")

    # 2. Initialiser les outils LangChain
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", ", ", " ", ""]
    )
    
    embeddings = OllamaEmbeddingsDirect(model=EMBEDDING_MODEL)

    all_chunks = []
    seen_urls = set()  # Déduplication par URL

    # 3. Traiter chaque document
    for filename, info in tqdm(docs_metadata.items(), desc="Parsing documents"):
        # Dédupliquer : ignorer les entrées pointant vers la même URL
        doc_url = info.get("url", "")
        if doc_url in seen_urls:
            logger.debug(f"Doublon ignoré (même URL) : {filename}")
            continue
        seen_urls.add(doc_url)

        # Rechercher le fichier dans plusieurs sous-dossiers possibles
        section = info.get("section_key", "")
        candidates = []
        if section:
            candidates.append(raw_dir / section / filename)
        candidates += [
            raw_dir / "rapports" / filename,
            raw_dir / filename,
        ]

        file_path = None
        for candidate in candidates:
            if candidate.exists():
                file_path = candidate
                break

        if file_path is None:
            logger.warning(f"Fichier manquant (testé: {[str(c) for c in candidates]})")
            continue

        try:
            # Charger selon le type
            loaded_docs = []
            if filename.lower().endswith(".pdf"):
                loader = PyMuPDFLoader(str(file_path))
                loaded_docs = loader.load()
            elif filename.lower().endswith(".html"):
                loader = TextLoader(str(file_path), encoding="utf-8")
                loaded_docs = loader.load()
            else:
                # Autres types (excel, docx) - à améliorer plus tard si besoin
                logger.debug(f"Type non supporté pour parsing profond : {filename}")
                continue

            # Ajouter les métadonnées de l'index aux documents LangChain
            for d in loaded_docs:
                d.metadata.update({
                    "source_url": info.get("url"),
                    "title": info.get("title"),
                    "category": info.get("category"),
                    "filename": filename,
                    "downloaded_at": info.get("downloaded_at")
                })
            
            # Découpage en chunks + filtrage des chunks parasites
            chunks = text_splitter.split_documents(loaded_docs)
            chunks = [c for c in chunks if _is_valid_chunk(c.page_content)]
            all_chunks.extend(chunks)
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement de {filename}: {e}")

    if not all_chunks:
        logger.warning("Aucun contenu n'a pu être extrait.")
        return

    logger.info(f"Extraction terminée : {len(all_chunks)} segments créés.")

    # 4. Stockage dans ChromaDB
    logger.info(f"Indexation dans ChromaDB ({VECTORSTORE_DIR})...")
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=VECTORSTORE_DIR,
        collection_name="bceao_rag"
    )
    
    # vectorstore.persist() # Plus nécessaire dans les versions récentes de Chroma, c'est auto-persistant
    
    logger.success(f"Ingestion terminée avec succès ! {len(all_chunks)} segments indexés.")

if __name__ == "__main__":
    run_ingestion()
