"""
Cache de réponses RAG — SQLite + similarité sémantique
Évite de recalculer les réponses pour des questions déjà posées ou très similaires.
"""

import sqlite3
import hashlib
import json
import math
from pathlib import Path
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CACHE_DB = Path(__file__).resolve().parents[2] / "data" / "response_cache.db"
SIMILARITY_THRESHOLD = 0.92   # Cosine similarity min pour considérer 2 questions identiques


def _cosine(a: list, b: list) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    na    = math.sqrt(sum(x * x for x in a))
    nb    = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _get_db() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            q_hash    TEXT UNIQUE,
            question  TEXT,
            embedding TEXT,
            response  TEXT,
            source    TEXT,
            hits      INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_hit   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def get_cached(question: str, embedding: list) -> tuple[str, str] | None:
    """
    Cherche une réponse en cache.
    1. Match exact par hash (O(1))
    2. Match sémantique par cosine (O(N))
    """
    try:
        q_hash = hashlib.sha256(question.strip().lower().encode()).hexdigest()
        conn = _get_db()
        
        # 1. Match exact
        exact = conn.execute(
            "SELECT response, source FROM cache WHERE q_hash = ?", (q_hash,)
        ).fetchone()
        
        if exact:
            logger.info(f"Cache HIT (exact match) : {question[:60]}...")
            conn.execute(
                "UPDATE cache SET hits = hits + 1, last_hit = CURRENT_TIMESTAMP WHERE q_hash = ?",
                (q_hash,)
            )
            conn.commit()
            conn.close()
            return exact[0], exact[1]

        # 2. Match sémantique (uniquement si embedding fourni)
        if embedding:
            rows = conn.execute(
                "SELECT q_hash, question, embedding, response, source FROM cache"
            ).fetchall()

            best_sim  = 0.0
            best_row  = None

            for row in rows:
                try:
                    cached_emb = json.loads(row[2])
                    sim = _cosine(embedding, cached_emb)
                    if sim > best_sim:
                        best_sim = sim
                        best_row = row
                except: continue

            if best_row and best_sim >= SIMILARITY_THRESHOLD:
                logger.info(f"Cache HIT (sim={best_sim:.3f}) : {best_row[1][:60]}...")
                conn.execute(
                    "UPDATE cache SET hits = hits + 1, last_hit = CURRENT_TIMESTAMP WHERE q_hash = ?",
                    (best_row[0],)
                )
                conn.commit()
                conn.close()
                return best_row[3], best_row[4]

        conn.close()
        return None
    except Exception as e:
        logger.warning(f"Erreur cache lecture : {e}")
        return None


def save_to_cache(question: str, embedding: list, response: str, source: str):
    """Sauvegarde une réponse dans le cache."""
    try:
        q_hash = hashlib.sha256(question.strip().lower().encode()).hexdigest()
        conn = _get_db()
        conn.execute("""
            INSERT OR REPLACE INTO cache (q_hash, question, embedding, response, source)
            VALUES (?, ?, ?, ?, ?)
        """, (q_hash, question, json.dumps(embedding), response, source))
        conn.commit()
        conn.close()
        logger.info(f"Cache SAVE : {question[:60]}...")
    except Exception as e:
        logger.warning(f"Erreur cache écriture : {e}")


def get_cache_stats() -> dict:
    """Retourne les statistiques du cache."""
    try:
        conn = _get_db()
        total  = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        hits   = conn.execute("SELECT SUM(hits) FROM cache").fetchone()[0] or 0
        top    = conn.execute(
            "SELECT question, hits FROM cache ORDER BY hits DESC LIMIT 5"
        ).fetchall()
        conn.close()
        return {"total_entries": total, "total_hits": hits, "top_questions": top}
    except Exception as e:
        logger.warning(f"Erreur stats cache : {e}")
        return {}
