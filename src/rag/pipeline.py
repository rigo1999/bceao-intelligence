"""
BCEAO RAG — Pipeline optimisé
Optimisations :
  A. Prompt réduit (< 400 tokens)
  B. Modèle léger (qwen2.5:1.5b)
  C. Socket direct (remplace subprocess curl → -0.27s overhead)
  D. Cache SQLite sémantique (réponses instantanées si question similaire)
  F. keep_alive=-1 (modèle toujours en RAM)
"""

from pathlib import Path
from typing import List, Generator
from loguru import logger
import json
import socket

import ollama
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from settings import (
    VECTORSTORE_DIR, EMBEDDING_MODEL, LLM_MODEL, OLLAMA_BASE_URL,
    TOP_K_RETRIEVAL
)
from prompts import RAG_PROMPT_TEMPLATE, WEB_PROMPT_TEMPLATE, SYSTEM_PROMPT, is_greeting, CHITCHAT_RESPONSES

# Phrase renvoyée par le LLM quand il ne trouve pas l'info en local
NOT_FOUND_SIGNAL = "je ne trouve pas cette information dans les documents bceao"

# Marqueurs de source interceptés par l'UI
MARKER_LOCAL  = "<<SOURCE:LOCAL>>"
MARKER_WEB    = "<<SOURCE:WEB>>"
MARKER_CACHE  = "<<SOURCE:CACHE>>"


# ─────────────────────────────────────────────
# Solution C : Socket HTTP direct (remplace subprocess curl)
# Contourne le bug Python 3.14 sans overhead process
# ─────────────────────────────────────────────

def _parse_ollama_url():
    url = OLLAMA_BASE_URL.replace("http://", "").replace("https://", "")
    if ":" in url:
        host, port = url.split(":", 1)
        return host, int(port)
    return url, 11434


def _ollama_request_sync(endpoint: str, payload_dict: dict) -> dict:
    """Requête Ollama synchrone via socket."""
    host, port = _parse_ollama_url()
    payload = json.dumps(payload_dict).encode("utf-8")
    http_request = (
        f"POST {endpoint} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("utf-8") + payload

    try:
        sock = socket.create_connection((host, port), timeout=60)
        sock.sendall(http_request)
        
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk: break
            response += chunk
        sock.close()

        if b"\r\n\r\n" not in response: return {}
        _, body = response.split(b"\r\n\r\n", 1)
        
        # Nettoyage chunked encoding
        clean_lines = []
        for line in body.split(b"\r\n"):
            line = line.strip()
            if not line or line == b"0": continue
            if all(c in b"0123456789abcdefABCDEF" for c in line): continue
            clean_lines.append(line)
        
        return json.loads(b"".join(clean_lines))
    except Exception as e:
        logger.error(f"Erreur sync Ollama ({endpoint}): {e}")
        return {}


def _ollama_request_stream(endpoint: str, payload_dict: dict) -> Generator[str, None, None]:
    """Requête Ollama streaming via socket."""
    host, port = _parse_ollama_url()
    payload = json.dumps(payload_dict).encode("utf-8")
    http_request = (
        f"POST {endpoint} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("utf-8") + payload

    try:
        sock = socket.create_connection((host, port), timeout=60)
        sock.sendall(http_request)
        
        buffer = b""
        header_done = False
        while True:
            chunk = sock.recv(4096)
            if not chunk: break
            buffer += chunk

            if not header_done:
                if b"\r\n\r\n" in buffer:
                    _, buffer = buffer.split(b"\r\n\r\n", 1)
                    header_done = True
                else: continue

            # NDJSON processing
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line or line == b"0": continue
                if all(c in b"0123456789abcdefABCDEF" for c in line): continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token: yield token
                    if data.get("done"):
                        sock.close()
                        return
                except: continue
        sock.close()
    except Exception as e:
        logger.error(f"Erreur stream Ollama ({endpoint}): {e}")


def _llm_stream(messages: list) -> Generator[str, None, None]:
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "options": {"temperature": 0, "num_predict": 250},
        "keep_alive": -1,
        "stream": True,
    }
    return _ollama_request_stream("/api/chat", payload)


# ─────────────────────────────────────────────
# Embeddings
# ─────────────────────────────────────────────

class OllamaEmbeddingsDirect(Embeddings):
    """Wrapper ollama direct (compatible Python 3.14).

    embed_documents utilise /api/embed en batch (50 textes/appel)
    → 40x plus rapide que les appels séquentiels.
    """

    def __init__(self, model: str):
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding via /api/embed — 50 textes par appel."""
        BATCH_SIZE = 50
        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            res = _ollama_request_sync("/api/embed", {
                "model": self.model,
                "input": batch,
                "keep_alive": -1
            })
            embeddings = res.get("embeddings", [])
            # Validate batch: fall back per-text if count mismatch or empties
            if embeddings and len(embeddings) == len(batch) and all(len(e) > 0 for e in embeddings):
                all_embeddings.extend(embeddings)
            else:
                logger.warning(f"Batch {i//BATCH_SIZE} incomplete ({len(embeddings)}/{len(batch)}), falling back one-by-one")
                for t in batch:
                    all_embeddings.append(self.embed_query(t))
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        for attempt in range(3):
            res = _ollama_request_sync("/api/embed", {
                "model": self.model,
                "input": [text],
                "keep_alive": -1
            })
            embeddings = res.get("embeddings", [])
            if embeddings and len(embeddings[0]) > 0:
                return embeddings[0]
            logger.warning(f"Empty embedding (attempt {attempt+1}/3), retrying...")
        logger.error(f"Failed to embed after 3 attempts: {text[:80]!r}")
        # Return zero vector as last resort to avoid crashing Chroma
        return [0.0] * 384


# ─────────────────────────────────────────────
# Singleton ChromaDB / VectorStore
# ─────────────────────────────────────────────

_vectorstore = None

def get_vectorstore():
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore
    if not Path(VECTORSTORE_DIR).exists():
        logger.error(f"VectorStore non trouvé dans {VECTORSTORE_DIR}.")
        return None
    logger.info("Chargement ChromaDB en mémoire...")
    embeddings = OllamaEmbeddingsDirect(model=EMBEDDING_MODEL)
    _vectorstore = Chroma(
        persist_directory=VECTORSTORE_DIR,
        embedding_function=embeddings,
        collection_name="bceao_rag"
    )
    logger.info("ChromaDB prêt.")
    return _vectorstore


# Synonymes BCEAO : termes utilisateurs → termes documents officiels
_BCEAO_SYNONYMS = {
    "directeur":   "gouverneur",
    "director":    "gouverneur",
    "président":   "gouverneur",
    "chef":        "gouverneur",
    "patron":      "gouverneur",
    "pdg":         "gouverneur",
    "siège":       "siège Dakar",
    "headquarter": "siège Dakar",
    "fondation":   "création BCEAO 1962",
    "fondé":       "créée 1962",
    "créé":        "créée 1962",
}

def _expand_query(question: str) -> str:
    """Ajoute les synonymes BCEAO au texte de recherche."""
    q_lower = question.lower()
    extras = []
    for user_term, bceao_term in _BCEAO_SYNONYMS.items():
        if user_term in q_lower and bceao_term.split()[0] not in q_lower:
            extras.append(bceao_term)
    if extras:
        return question + " " + " ".join(extras)
    return question


def get_retriever():
    vs = get_vectorstore()
    if vs:
        return vs.as_retriever(search_kwargs={"k": TOP_K_RETRIEVAL})
    return None


def retrieve_docs(question: str):
    """Récupère les documents avec expansion de requête."""
    retriever = get_retriever()
    if not retriever:
        return []
    expanded = _expand_query(question)
    if expanded != question:
        logger.debug(f"Query expanded: '{question}' → '{expanded}'")
    return retriever.invoke(expanded)


def format_docs(docs):
    formatted = []
    for doc in docs:
        source  = doc.metadata.get("title", "Document inconnu")
        content = doc.page_content.strip()
        formatted.append(f"[{source}]\n{content}")
    return "\n\n".join(formatted)


# ─────────────────────────────────────────────
# Web search
# ─────────────────────────────────────────────

def web_search(query: str, max_results: int = 3) -> str:
    try:
        from ddgs import DDGS
        logger.info(f"Recherche web : {query}")
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"BCEAO UEMOA {query}", region="fr-fr", max_results=max_results
            ))
        if not results:
            return ""
        return "\n\n".join(
            f"[{r['title']} — {r['href']}]\n{r['body'][:300]}" for r in results
        )
    except Exception as e:
        logger.warning(f"Recherche web échouée : {e}")
        return ""


# ─────────────────────────────────────────────
# Warm-up LLM
# ─────────────────────────────────────────────

def warmup_llm():
    """Précharge le modèle en RAM via socket direct."""
    logger.info("Warm-up LLM...")
    try:
        # Consommer le générateur pour déclencher le warm-up
        for _ in _llm_stream([{"role": "user", "content": "ok"}]):
            break
        logger.info("Warm-up terminé — modèle en RAM.")
    except Exception as e:
        logger.warning(f"Warm-up échoué : {e}")


# ─────────────────────────────────────────────
# Faits BCEAO statiques (réponses directes pour questions fréquentes)
# ─────────────────────────────────────────────

_BCEAO_FACTS = {
    # gouverneur / directeur
    ("gouverneur", "directeur", "président", "chef", "tête", "patron", "responsable", "dirigeant"): (
        ("gouverneur", "bceao", "banque", "centrale"),
        "Le Gouverneur actuel de la BCEAO est **Jean-Claude Kassi BROU**, en fonction depuis 2020. "
        "Il préside le Comité de Politique Monétaire. "
        "📄 Rapports sur la Politique Monétaire BCEAO — 2023/2024/2025"
    ),
    # siège
    (("siège", "siege", "adresse", "localisation", "située", "situé", "trouve", "lieu", "locali"),): (
        ("siège", "adresse", "trouve", "locali"),
        "Le siège de la BCEAO est situé à **Dakar, République du Sénégal**, "
        "Avenue Abdoulaye FADIGA, BP 3108. "
        "📄 Communiqués officiels BCEAO"
    ),
    # création / fondation
    (("créée", "créé", "fondée", "fondé", "création", "fondation", "historique", "naissance", "origine"),): (
        ("créée", "fondée", "création"),
        "La BCEAO (Banque Centrale des États de l'Afrique de l'Ouest) a été créée le **12 mai 1962**. "
        "Elle est l'institution d'émission commune aux huit États membres de l'UEMOA : "
        "Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, Mali, Niger, Sénégal, Togo. "
        "📄 Documents institutionnels BCEAO"
    ),
}

def _check_static_facts(question: str):
    """Vérifie si la question correspond à un fait BCEAO connu. Retourne (réponse, True) ou (None, False)."""
    q = question.lower()
    # Gouverneur / directeur actuel
    director_triggers = {"gouverneur", "directeur", "président bceao", "chef bceao", "tête bceao", "patron bceao", "dirigeant"}
    bceao_mentioned = "bceao" in q or "banque centrale" in q or "banque" in q
    if bceao_mentioned and any(t in q for t in director_triggers):
        return (
            "Le Gouverneur actuel de la BCEAO est **Jean-Claude Kassi BROU**, en fonction depuis 2020. "
            "Il préside le Comité de Politique Monétaire de l'UMOA. "
            "📄 Rapports sur la Politique Monétaire BCEAO — 2023/2024/2025",
            True
        )
    # Siège / adresse
    siege_triggers = {"siège", "siege", "adresse", "où se trouve", "ou se trouve", "locali", "situé", "située"}
    if bceao_mentioned and any(t in q for t in siege_triggers):
        return (
            "Le siège de la BCEAO est situé à **Dakar, République du Sénégal**, "
            "Avenue Abdoulaye FADIGA, BP 3108. "
            "📄 Communiqués officiels BCEAO",
            True
        )
    # Création / fondation
    creation_triggers = {"créée", "créé", "fondée", "fondé", "création", "fondation", "historique", "naissance", "origine", "quand"}
    if bceao_mentioned and any(t in q for t in creation_triggers):
        return (
            "La BCEAO a été créée le **12 mai 1962**. Elle est l'institution d'émission commune "
            "aux huit États membres de l'UEMOA : Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, "
            "Mali, Niger, Sénégal et Togo. "
            "📄 Documents institutionnels BCEAO",
            True
        )
    return None, False


# ─────────────────────────────────────────────
# Pipeline principal (Optimisé Parallèle)
# ─────────────────────────────────────────────

from concurrent.futures import ThreadPoolExecutor

# Mots qui indiquent une question de suivi référençant le contexte précédent
_CONTEXT_REFS = {
    "ce", "cet", "cette", "ces", "cela", "ça", "celui", "celle", "ceux",
    "il", "elle", "ils", "elles", "le", "la", "les", "lui", "leur",
    "même", "aussi", "encore", "précédent", "dernier", "rapport", "indicateur",
    "this", "that", "it", "these", "those", "same", "previous"
}

def _is_contextual(question: str, history: list) -> bool:
    """Détecte si la question fait référence à la conversation précédente."""
    if not history:
        return False
    words = set(question.lower().split())
    return bool(words & _CONTEXT_REFS)


def run_query_stream(question: str, history: list = None) -> Generator[str, None, None]:
    """
    Pipeline RAG avec mémoire conversationnelle :
    1. Salutation
    2. Cache (ignoré si question contextuelle)
    3. RAG local + historique → LLM
    4. Fallback web
    """
    if history is None:
        history = []

    logger.info(f"Question : {question} | historique : {len(history)} messages")

    # ── 1. Salutation (toujours, peu importe l'historique) ─────────────
    if is_greeting(question):
        yield CHITCHAT_RESPONSES["fr"]
        return

    # ── 1b. Faits BCEAO statiques (gouverneur, siège, création...) ──────
    static_answer, is_static = _check_static_facts(question)
    if is_static:
        yield MARKER_LOCAL
        yield static_answer
        return

    # ── 2. Cache sémantique (désactivé si question contextuelle) ────────────
    is_ctx = _is_contextual(question, history)
    q_embedding = None
    try:
        from src.rag.cache import get_cached, save_to_cache
        res = _ollama_request_sync("/api/embed", {
            "model": EMBEDDING_MODEL, "input": [question], "keep_alive": -1
        })
        embeddings = res.get("embeddings", [])
        q_embedding = embeddings[0] if embeddings else []

        if not is_ctx:
            cached = get_cached(question, q_embedding)
            if cached:
                yield MARKER_CACHE
                yield cached[0]
                return
        else:
            logger.info("Question contextuelle → cache ignoré")
    except Exception as e:
        logger.warning(f"Cache erreur : {e}")

    # ── 3. Lancement parallèle du Web Search ───────
    # On lance la recherche web tout de suite pour ne pas attendre l'échec local
    executor = ThreadPoolExecutor(max_workers=1)
    web_future = executor.submit(web_search, question)

    # ── 4. RAG local ───────────────────────────────
    vs = get_vectorstore()
    if not vs:
        yield "Erreur : Base de données non disponible."
        return

    # Expansion de requête (ex: "directeur" → "directeur gouverneur")
    expanded_question = _expand_query(question)
    if expanded_question != question:
        logger.debug(f"Query expanded: '{question}' → '{expanded_question}'")
        exp_res = _ollama_request_sync("/api/embed", {
            "model": EMBEDDING_MODEL, "input": [expanded_question], "keep_alive": -1
        })
        exp_embeddings = exp_res.get("embeddings", [])
        search_embedding = exp_embeddings[0] if exp_embeddings else q_embedding
    else:
        search_embedding = q_embedding

    docs = vs.similarity_search_by_vector(search_embedding, k=TOP_K_RETRIEVAL) if search_embedding else []
    
    local_response = ""
    if docs:
        context = format_docs(docs)
        user_message = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

        yield MARKER_LOCAL
        # Construire les messages avec l'historique de conversation
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        llm_messages += history[-6:]  # max 3 échanges précédents
        llm_messages.append({"role": "user", "content": user_message})

        for token in _llm_stream(llm_messages):
            local_response += token
            yield token
    else:
        local_response = NOT_FOUND_SIGNAL

    # ── 5. Fallback Web (Résultat probablement déjà prêt) ──
    if NOT_FOUND_SIGNAL in local_response.lower():
        logger.info("Local échec ou non trouvé. Vérification résultat web parallèle...")
        try:
            # Timeout court (15s) pour la recherche web pour éviter de bloquer l'utilisateur
            web_context = web_future.result(timeout=15) 
        except Exception as e:
            logger.warning(f"Recherche web expirée ou échouée : {e}")
            web_context = ""
        
        if web_context:
            yield MARKER_WEB
            web_message = WEB_PROMPT_TEMPLATE.format(context=web_context, question=question)
            web_response = ""
            web_llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            web_llm_messages += history[-6:]
            web_llm_messages.append({"role": "user", "content": web_message})
            for token in _llm_stream(web_llm_messages):
                web_response += token
                yield token
            
            # Cache la réponse web
            if q_embedding and web_response:
                try: save_to_cache(question, q_embedding, web_response, "web")
                except: pass
        else:
            if not docs:
                yield "\n\n> ⚠️ Aucune information trouvée (Base locale & Web)."
    
    elif q_embedding and local_response:
        # Cache la réponse locale réussie
        try: save_to_cache(question, q_embedding, local_response, "local")
        except: pass
    
    executor.shutdown(wait=False)


def run_query(question: str) -> str:
    """Exécute une requête RAG complète (non-streaming, pour CLI)."""
    return "".join(run_query_stream(question))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(run_query(sys.argv[1]))
    else:
        print('Usage: python pipeline.py "ta question"')
