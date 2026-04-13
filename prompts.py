# Mots-clés qui indiquent une salutation ou message hors-sujet
GREETINGS = {
    "hi", "hello", "helo", "helo", "hell", "helo", "hllo",
    "bonjour", "bnjour", "bonour", "bonjou",
    "bonsoir", "salut", "slt", "hey", "heyy",
    "coucou", "yo", "allo", "allô", "hola",
    "salam", "bjr", "bsr", "cc", "wesh",
}

CHITCHAT_RESPONSES = {
    "fr": "Bonjour ! Je suis BCEAO Intelligence, votre assistant pour l'analyse des documents officiels de la BCEAO. Posez-moi une question sur la politique monétaire, les rapports, les bulletins ou les données économiques de l'UEMOA.",
    "en": "Hello! I'm BCEAO Intelligence. Please ask me a question about BCEAO official documents, monetary policy, or UEMOA economic data.",
}

def _fuzzy_is_greeting(word: str) -> bool:
    """Vérifie si un mot ressemble à une salutation (distance de Levenshtein ≤ 1)."""
    if word in GREETINGS:
        return True
    # Distance de Levenshtein simplifiée : 1 caractère de différence
    for g in GREETINGS:
        if abs(len(word) - len(g)) > 1:
            continue
        # Substitution / suppression d'1 caractère
        diffs = sum(1 for a, b in zip(word.ljust(len(g)), g.ljust(len(word))) if a != b)
        if diffs <= 1:
            return True
    return False

def is_greeting(text: str) -> bool:
    """Détecte si le message est une salutation, même avec fautes de frappe."""
    cleaned = text.strip().lower().rstrip("!.,? ")
    words = cleaned.split()
    if not words:
        return True
    # Message d'un seul mot qui ressemble à une salutation
    if len(words) == 1 and _fuzzy_is_greeting(cleaned):
        return True
    # Message court (≤ 5 mots) dont le premier mot ressemble à une salutation
    if len(words) <= 5 and _fuzzy_is_greeting(words[0]):
        return True
    return False


SYSTEM_PROMPT = """Tu es BCEAO Intelligence, analyste UEMOA.
Règles : réponds à partir du contexte fourni. Tu peux déduire des faits clairement implicites dans le contexte (ex: si le texte dit "son Siège à Dakar", le siège est à Dakar). Si l'information est vraiment absente, dis exactement : "Je ne trouve pas cette information dans les documents BCEAO disponibles." Ne jamais inventer de chiffres ou faits non mentionnés. Réponds en français. Cite la source : 📄 [Titre] — [année]."""

RAG_PROMPT_TEMPLATE = """Contexte BCEAO :
{context}

Question : {question}
Réponse directe et sourcée :"""

WEB_PROMPT_TEMPLATE = """Résultats web (sources publiques) :
{context}

Question : {question}
Synthèse concise avec sources web :"""
