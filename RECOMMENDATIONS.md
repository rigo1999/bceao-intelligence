# Recommandations Techniques — Projet BCEAO RAG
**DITOMA / Direction Informatique**  
Date : Avril 2026  
Statut : Document de travail interne

---

## 1. Contexte du projet

Ce document retrace les défis techniques rencontrés lors du développement du système **BCEAO Intelligence**, un assistant RAG (Retrieval-Augmented Generation) permettant d'interroger les documents officiels de la BCEAO en langage naturel.

L'objectif était de construire un pipeline complet :
- Ingestion de documents PDF officiels (rapports monétaires, bulletins, communiqués)
- Indexation vectorielle pour la recherche sémantique
- Génération de réponses via un LLM local (Ollama)
- Interface utilisateur React + API FastAPI

Le système a été développé et déployé **entièrement en local**, sur un PC Windows 11 sans GPU dédié, avec Python 3.14.

---

## 2. Défis rencontrés

### 2.1 Incompatibilité Python 3.14 avec l'écosystème LangChain/Ollama

**Problème :**  
Python 3.14 a cassé la compatibilité avec Pydantic v1, utilisé en interne par `langchain_ollama`. Les appels au LLM via `ChatOllama` et `OllamaEmbeddings` échouaient silencieusement ou retournaient des erreurs de streaming.

**Décision prise :**  
Remplacement de toutes les dépendances LangChain pour les appels Ollama par des **sockets TCP directs** (HTTP/1.1 manuel via le module `socket`). Cette approche contourne entièrement urllib3 et httpx, qui sont les couches impactées par le bug Python 3.14.

**Impact :**  
- Gain de ~270ms par requête (suppression de l'overhead subprocess)
- Code plus fragile et plus verbeux qu'un client HTTP standard
- Maintenance accrue en cas d'évolution de l'API Ollama

**Recommandation :**  
Migrer vers Python 3.12 ou 3.11 (LTS stables) dès que possible. La totalité de l'écosystème IA Python (LangChain, LlamaIndex, Hugging Face) cible Python 3.10–3.12. Python 3.14 est encore en phase de test et non recommandé pour la production.

---

### 2.2 Absence de GPU — Choix du modèle LLM

**Problème :**  
Le modèle initialement prévu, **Mistral 7B**, s'est avéré trop lourd pour le matériel disponible :
- Temps de première réponse : **169 secondes**
- Surchauffe du processeur
- Déchargement du modèle entre chaque requête faute de RAM suffisante

**Décisions prises (par ordre chronologique) :**
1. `mistral:7b` → `phi3:mini` (3.8B) → `qwen2.5:1.5b` (1.5B)
2. Ajout du paramètre `keep_alive: -1` pour maintenir le modèle en RAM
3. Warm-up automatique du modèle au démarrage de l'API

**Résultat obtenu :**  
- Temps de réponse moyen : **15–25 secondes** (hors cache)
- Réponses en cache : **< 1 seconde**

**Impact négatif du choix qwen2.5:1.5b :**  
Un modèle de 1.5B paramètres présente des hallucinations fréquentes, notamment :
- Confusion "Afrique de l'Ouest" / "Afrique du Sud"
- Incapacité à déduire des faits implicites dans le contexte
- Réponses parfois incohérentes sur des questions complexes

**Recommandation :**  
- **Court terme :** Ajouter un GPU d'entrée de gamme (ex. NVIDIA RTX 3060, 12 Go VRAM). Cela permettrait d'utiliser `mistral:7b-q4` ou `qwen2.5:7b` avec des temps de réponse de 3–5 secondes.
- **Moyen terme :** Déployer le système sur un serveur cloud avec GPU (ex. RunPod, Modal, ou une VM GCP/Azure avec T4). Le coût est de l'ordre de 0,20–0,50 $/heure.
- **Long terme :** Évaluer des modèles fine-tunés sur corpus financiers francophones (ex. CroissantLLM, Vigogne).

---

### 2.3 Lenteur de l'indexation vectorielle

**Problème :**  
Le modèle d'embedding `nomic-embed-text` (274 Mo) prenait **~2,1 secondes par chunk** sur CPU. Avec 8 805 chunks initiaux, l'indexation complète aurait duré **5,2 heures**.

**Causes identifiées :**
1. Appels séquentiels (un embedding à la fois) via HTTP
2. Modèle trop lourd pour le CPU disponible
3. Présence de chunks parasites (tables de matières, tableaux statistiques, numéros de page) déclenchant des erreurs d'embedding en cascade

**Décisions prises :**
1. Passage au modèle `all-minilm` (23 Mo) → même vitesse (~2,1s), mais dimensions réduites (384 vs 768)
2. Migration vers l'endpoint batch `/api/embed` d'Ollama → **50 chunks par appel** → gain théorique de ~40x
3. Implémentation d'un filtre de qualité sur les chunks :
   - Suppression des chunks < 80 caractères
   - Suppression des chunks avec > 15% de points consécutifs (tables des matières)
   - Suppression des chunks avec > 50% de chiffres (tableaux statistiques)
   - Suppression des chunks avec < 30% de lettres (bruit pur)
4. Résultat : **7 234 chunks propres** indexés en ~12 minutes

**Recommandation :**  
- Utiliser `sentence-transformers` directement en Python (sans passer par Ollama HTTP) pour l'embedding. Cela élimine l'overhead réseau et divise le temps d'embedding par 3–5.
- Modèle recommandé : `paraphrase-multilingual-MiniLM-L12-v2` (optimisé pour le français)
- Implémenter un pipeline d'ingestion **incrémental** : ne réindexer que les nouveaux documents, pas toute la base.

---

### 2.4 Qualité du chunking

**Problème :**  
Le splitter `RecursiveCharacterTextSplitter` ne respectait pas le `CHUNK_SIZE=500` configuré. Les chunks réels avaient une taille moyenne de **839 caractères** (quasi le double), car les PDFs extraits par PyMuPDF n'ont pas de double-saut de ligne (`\n\n`) pour guider le splitter.

De plus, la fonction `format_docs()` tronquait les chunks à 400 caractères pour le contexte LLM, jetant ~55% du contenu récupéré.

**Décision prise :**  
- `CHUNK_SIZE` ramené à 400 caractères
- `CHUNK_OVERLAP` à 40 caractères (10% — minimum acceptable)
- Suppression de la troncature dans `format_docs()`
- Ajout de `length_function=len` et séparateurs améliorés

**Recommandation :**  
- Adopter un chunking **document-aware** : détecter les titres de section (regex sur numérotation, majuscules, taille de police via PyMuPDF) et préfixer chaque chunk avec son titre de section. Ex : `[Section: 2.3 Politique de taux directeur] Le Comité a décidé...`
- Augmenter `CHUNK_OVERLAP` à 60–80 caractères (15–20% de CHUNK_SIZE)
- Évaluer `CHUNK_SIZE=600–800` pour les documents financiers longs

---

### 2.5 Précision de la recherche sémantique

**Problème :**  
Le modèle `all-minilm` ne faisait pas le lien entre les termes utilisateur ("directeur", "siège") et les termes des documents BCEAO ("Gouverneur", "Siège à Dakar"). La recherche dense seule est insuffisante face à ce **vocabulary mismatch**.

**Décisions prises (solutions de contournement) :**
1. **Expansion de requête** : dictionnaire de synonymes BCEAO ("directeur" → "gouverneur", "siège" → "siège Dakar") appliqué avant l'embedding
2. **Faits statiques** : dictionnaire Python interceptant les questions sur le Gouverneur, le siège et la date de création, avant toute recherche vectorielle
3. **TOP_K passé de 2 à 4** pour augmenter la probabilité de trouver le bon chunk

**Limitations de ces solutions :**  
Les faits statiques sont maintenus manuellement et deviendront obsolètes (ex. changement de Gouverneur). L'expansion de requête est incomplète et ne couvre que les cas connus.

**Recommandation (approche senior) :**
- **Hybrid Search (BM25 + Dense)** : combiner la recherche par mots-clés exacts (BM25) et la recherche sémantique (vecteurs). BM25 capture "BCEAO", "Gouverneur" exactement. Dense capture les synonymes. La fusion Reciprocal Rank Fusion (RRF) combine les scores.
- **Cross-encoder reranker** : après récupération de 10–20 chunks candidates, utiliser un cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) pour rescorer chaque paire (question, chunk) et ne garder que les 3–4 meilleurs. Précision nettement supérieure à la similarité cosinus.
- Supprimer les faits statiques hardcodés une fois le hybrid search + reranker en place.

---

### 2.6 Qualité des réponses et hallucinations

**Problème :**  
`qwen2.5:1.5b` a produit plusieurs hallucinations notables :
- "Banque centrale des États de l'Afrique **du Sud**" au lieu de "de l'Ouest"
- Invention d'un "Maman Laouali Abdou Rafa" comme directeur (issu d'un article web hors-sujet)
- Incapacité à déduire "siège à Dakar" depuis "son Siège à Dakar" dans le texte

**Décision prise :**  
- Prompt système renforcé avec règle anti-invention
- Faits statiques pour les informations institutionnelles clés
- Réduction de `num_predict` à 250 tokens pour forcer des réponses concises

**Recommandation :**  
- Utiliser un modèle plus grand dès que le matériel le permet (voir §2.2)
- Implémenter une **vérification de grounding** : après génération, vérifier que chaque fait de la réponse apparaît bien dans les chunks récupérés (pattern matching simple)
- Ajouter un signal explicite dans le prompt : injecter le titre et l'année du document source dans chaque chunk de contexte

---

### 2.7 Cache sémantique

**Ce qui a été fait :**  
Cache SQLite à deux niveaux :
1. Hash SHA-256 exact (correspondance parfaite)
2. Similarité cosinus ≥ 0.92 (questions paraphrasées)

**Résultat :** Réponses en cache en ~1 seconde au lieu de 15–25 secondes.

**Problème rencontré :**  
Le cache avait des entrées parasites (questions courtes type "Hello") qui polluaient les résultats de similarité cosinus. Résolu en filtrant les entrées de longueur ≤ 10 caractères.

**Recommandation :**  
- Passer à **Redis** pour le cache en production (TTL automatique, partage entre instances, persistance)
- Ajouter un TTL (Time-To-Live) de 7–30 jours selon la fréquence de mise à jour des documents
- Invalider le cache automatiquement lors d'une nouvelle ingestion

---

## 3. Architecture actuelle vs architecture recommandée

### Architecture actuelle (contraintes CPU)

```
[PDF] → PyMuPDF → RecursiveTextSplitter (400 chars)
     → Filtre qualité → all-minilm (batch /api/embed)
     → ChromaDB (dense search uniquement)

[Query] → all-minilm embed → ChromaDB similarity search (TOP_K=4)
        → Static facts check → format_docs → qwen2.5:1.5b
        → SQLite cache
```

### Architecture recommandée (avec ressources adéquates)

```
[PDF] → unstructured (layout-aware) → Section-aware chunker (600 chars, overlap 80)
     → Filtre qualité → sentence-transformers (batch, direct Python)
     → ChromaDB (dense) + BM25 index (sparse)

[Query] → Reformulation LLM (optionnel)
        → Dense embed + BM25 (parallel)
        → Reciprocal Rank Fusion → top 20 candidates
        → Cross-encoder reranker → top 4 chunks
        → Grounding-aware prompt → mistral:7b-q4 ou API Claude
        → Redis cache (TTL 7j)
        → Grounding verification
```

---

## 4. Recommandations prioritaires

### Priorité 1 — Infrastructure (bloquant pour la qualité)
| Action | Impact | Effort |
|--------|--------|--------|
| Migrer vers Python 3.12 | Débloque tout l'écosystème IA | Faible |
| Ajouter un GPU (RTX 3060 ou cloud) | Temps de réponse 3–5s, modèles plus puissants | Moyen |
| Passer à `mistral:7b-q4` ou `qwen2.5:7b` | Réduit les hallucinations de 80% | Faible (si GPU) |

### Priorité 2 — Qualité de récupération
| Action | Impact | Effort |
|--------|--------|--------|
| Hybrid Search BM25 + Dense | Résout vocabulary mismatch | Moyen |
| Cross-encoder reranker | Améliore le ranking des chunks | Faible |
| Section-aware chunking | Meilleure cohérence du contexte | Moyen |
| Supprimer les faits statiques hardcodés | Moins de maintenance | Faible (après hybrid search) |

### Priorité 3 — Évaluation et monitoring
| Action | Impact | Effort |
|--------|--------|--------|
| Construire un golden test set (50–100 Q&A) | Mesure objective de chaque changement | Moyen |
| Script d'évaluation automatique | CI/CD pour le RAG | Moyen |
| Logs structurés (question, chunks récupérés, réponse, latence) | Debugging et amélioration continue | Faible |
| Dashboard de monitoring (Grafana ou simple SQLite) | Visibilité en production | Moyen |

### Priorité 4 — Maintenabilité
| Action | Impact | Effort |
|--------|--------|--------|
| Pipeline d'ingestion incrémental | Re-indexer seulement les nouveaux docs | Moyen |
| Redis pour le cache | TTL, partage entre instances | Faible |
| Containerisation Docker | Reproductibilité, déploiement | Moyen |
| Tests unitaires sur le pipeline | Évite les régressions | Moyen |

---

## 5. Métriques cibles

| Métrique | Actuel | Cible (avec GPU) |
|----------|--------|------------------|
| Temps de réponse (première question) | 15–25s | 3–5s |
| Temps de réponse (cache) | ~1s | ~200ms |
| Retrieval recall @4 | ~60% (estimé) | >85% |
| Taux d'hallucination | ~15% (estimé) | <3% |
| Temps d'indexation complète | ~12 min | <2 min |
| Couverture des documents | 7 234 chunks | Maintenu + incrémental |

---

## 6. Conclusion

Le système BCEAO Intelligence est fonctionnel et répond aux besoins de base. Cependant, la contrainte matérielle (absence de GPU, Python 3.14) a forcé une série de compromis qui limitent la qualité et la robustesse des réponses.

Les solutions de contournement mises en place (faits statiques, expansion de requête, sockets TCP manuels) sont **acceptables pour un prototype** mais ne doivent pas être conservées en production sans les remplacer par les approches recommandées.

**La priorité absolue pour la prochaine itération est l'ajout d'un GPU et la migration vers Python 3.12.** Ces deux actions débloquent la majorité des recommandations techniques sans changement majeur d'architecture.

---

*Document rédigé suite au développement du prototype BCEAO Intelligence, avril 2026.*  
*Toute modification de l'architecture doit être validée par une exécution du golden test set.*
