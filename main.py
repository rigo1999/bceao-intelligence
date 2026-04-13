"""
BCEAO RAG — Point d'entrée principal
Usage:
  python main.py scrape       → Lance le scraping des documents BCEAO
  python main.py ingest       → Ingère les PDFs dans ChromaDB
  python main.py query "..."  → Pose une question via CLI
  python main.py app          → Lance l'interface Streamlit
"""

import sys
from loguru import logger

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "scrape":
        from src.scraper.scraper import run_scraper
        logger.info("Démarrage du scraping BCEAO...")
        run_scraper()

    elif command == "ingest":
        from src.ingestion.pdf_parser import run_ingestion
        logger.info("Démarrage de l'ingestion des PDFs...")
        run_ingestion()

    elif command == "query":
        if len(sys.argv) < 3:
            print("Usage: python main.py query \"ta question\"")
            return
        from src.rag.pipeline import run_query
        question = sys.argv[2]
        result = run_query(question)
        print(f"\n{result}\n")

    elif command == "app":
        import subprocess
        subprocess.run(["streamlit", "run", "src/interface/app.py"])

    else:
        print(f"Commande inconnue: {command}")
        print(__doc__)

if __name__ == "__main__":
    main()
