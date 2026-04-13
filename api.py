"""
BCEAO RAG — FastAPI backend
POST /chat  → Server-Sent Events streaming
"""

import sys, json, asyncio, threading
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.rag.pipeline import run_query_stream, warmup_llm

app = FastAPI(title="BCEAO RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class HistoryMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    question: str
    history: list[HistoryMessage] = []


@app.on_event("startup")
async def startup_event():
    # Warm-up en arrière-plan (ne bloque pas le démarrage)
    threading.Thread(target=warmup_llm, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest):
    logger.info(f"Question reçue : {req.question}")

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        # Convertir l'historique en format pipeline
        history = [{"role": m.role, "content": m.content} for m in req.history]

        # Exécuter le générateur bloquant dans un thread dédié
        def run_pipeline():
            try:
                for token in run_query_stream(req.question, history=history):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            except Exception as e:
                logger.error(f"Erreur pipeline : {e}")
                loop.call_soon_threadsafe(queue.put_nowait, f"⚠️ Erreur : {e}")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        # Ping immédiat → le client sait que la connexion est vivante
        yield ": ping\n\n"

        while True:
            try:
                token = await asyncio.wait_for(queue.get(), timeout=120)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps('⏱️ Délai dépassé — le modèle ne répond plus.')}\n\n"
                break

            if token is None:
                break

            # JSON-encode pour éviter que les \n dans les tokens cassent le SSE
            yield f"data: {json.dumps(token)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
