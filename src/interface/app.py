import streamlit as st
import sys
from pathlib import Path

# Ajouter le chemin racine pour les imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rag.pipeline import run_query, run_query_stream, get_retriever, warmup_llm, MARKER_LOCAL, MARKER_WEB, MARKER_CACHE

# Préchargement du VectorStore + warm-up LLM au démarrage (une seule fois)
@st.cache_resource(show_spinner="Initialisation — chargement des modèles en mémoire...")
def initialize():
    get_retriever()   # ChromaDB en mémoire
    warmup_llm()      # Mistral chargé en RAM (keep_alive=-1)
    return True

initialize()

# Configuration de la page
st.set_page_config(
    page_title="BCEAO RAG — Souveraineté Décisionnelle",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Style CSS personnalisé pour un look moderne et "premium"
st.markdown("""
<style>
    /* Thème global et typographie */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Couleurs BCEAO (vert/or stylisé pour mode sombre) */
    :root {
        --primary-color: #0d9488; /* Teal/Vert */
        --accent-color: #fbbf24;  /* Or */
        --bg-color: #0f172a;      /* Bleu nuit profond */
        --card-bg: #1e293b;
        --text-main: #f8fafc;
        --text-muted: #94a3b8;
    }

    /* Top header custom */
    .app-header {
        background: linear-gradient(135deg, var(--card-bg) 0%, #020617 100%);
        padding: 2rem;
        border-radius: 1rem;
        border-bottom: 2px solid var(--primary-color);
        margin-bottom: 2rem;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    
    .app-title {
        margin: 0;
        font-weight: 700;
        color: var(--text-main);
        font-size: 2.2rem;
        letter-spacing: -0.025em;
    }
    
    .app-subtitle {
        color: var(--primary-color);
        font-weight: 600;
        font-size: 1.1rem;
        margin-top: 0.2rem;
    }

    /* Style des messages de chat */
    .stChatMessage {
        background-color: var(--card-bg) !important;
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 0.75rem;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    [data-testid="chatAvatarIcon-user"] {
        background-color: var(--primary-color) !important;
    }
    
    [data-testid="chatAvatarIcon-assistant"] {
        background-color: var(--accent-color) !important;
        color: #000 !important;
    }

    /* Sidebar modifiée */
    [data-testid="stSidebar"] {
        background-color: var(--card-bg) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    .sidebar-info {
        background: rgba(13, 148, 136, 0.1);
        border-left: 4px solid var(--primary-color);
        padding: 1rem;
        border-radius: 0.5rem;
        color: var(--text-muted);
        font-size: 0.9rem;
    }
    
    /* Input chat */
    .stChatInputContainer {
        border-radius: 1rem !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5) !important;
    }
</style>
""", unsafe_allow_html=True)

# En-tête personnalisé
st.markdown("""
<div class="app-header">
    <div style="font-size: 3rem;">🏦</div>
    <div>
        <h1 class="app-title">BCEAO <span style="color: var(--primary-color);">Intelligence</span></h1>
        <div class="app-subtitle">Souveraineté Décisionnelle & Analyse Stratégique</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Barre latérale (Sidebar)
with st.sidebar:
    try:
        st.image("https://www.bceao.int/themes/custom/bceao/logo.svg", width=150)
    except Exception:
        st.markdown("### 🏦 BCEAO")
    st.markdown("### 🔍 Paramètres")
    st.markdown("""
    <div class="sidebar-info">
        <strong>Agent RAG Local</strong><br/>
        Propulsé par <i>Ollama</i> (Mistral 7B) et ChromaDB.<br/>
        Données : <i>Rapports, Bulletins, Communiqués</i> de la BCEAO.
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    if st.button("🗑️ Effacer l'historique"):
        st.session_state.messages = []
        st.rerun()
        
    st.markdown("---")
    st.caption("v1.0.0 - 100% Local / Zéro fuite de données")


# Initialisation de l'historique du chat
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Bonjour. Je suis votre assistant stratégique pour l'analyse des documents publics de la BCEAO. Comment puis-je vous aider aujourd'hui ?"}
    ]

# Affichage des messages existants
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Gestion de la saisie utilisateur
if prompt := st.chat_input("Posez votre question sur la politique monétaire, les notes de la BCEAO, etc."):
    # Ajouter la question de l'utilisateur
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Réponse de l'assistant — streaming token par token via subprocess curl
    with st.chat_message("assistant"):
        try:
            badge_placeholder  = st.empty()   # Badge de source (LOCAL / WEB)
            message_placeholder = st.empty()  # Texte streamé

            full_response = ""
            current_source = None             # "local" | "web" | None

            BADGE_LOCAL = (
                '<span style="background:#0d9488;color:white;padding:2px 10px;'
                'border-radius:12px;font-size:0.78rem;font-weight:600;">'
                '📚 Base BCEAO locale</span>'
            )
            BADGE_WEB = (
                '<span style="background:#6366f1;color:white;padding:2px 10px;'
                'border-radius:12px;font-size:0.78rem;font-weight:600;">'
                '🌐 Complément web (DuckDuckGo)</span>'
            )
            BADGE_CACHE = (
                '<span style="background:#f59e0b;color:white;padding:2px 10px;'
                'border-radius:12px;font-size:0.78rem;font-weight:600;">'
                '⚡ Cache (réponse instantanée)</span>'
            )

            for token in run_query_stream(prompt):
                # Intercepter les marqueurs de source
                if token == MARKER_LOCAL:
                    current_source = "local"
                    badge_placeholder.markdown(BADGE_LOCAL, unsafe_allow_html=True)
                    continue
                if token == MARKER_WEB:
                    current_source = "web"
                    badge_placeholder.markdown(
                        BADGE_LOCAL + "&nbsp;&nbsp;" + BADGE_WEB,
                        unsafe_allow_html=True
                    )
                    full_response += "\n\n---\n**🌐 Complément via recherche web :**\n\n"
                    continue
                if token == MARKER_CACHE:
                    current_source = "cache"
                    badge_placeholder.markdown(BADGE_CACHE, unsafe_allow_html=True)
                    continue

                full_response += token
                message_placeholder.markdown(full_response + "▌")

            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            error_msg = f"Désolé, une erreur technique est survenue : {str(e)}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
