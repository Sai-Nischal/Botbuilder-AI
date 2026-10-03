import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from app.config import INDEX_DIR, EMBEDDING_MODEL_NAME, HIGH_THRESHOLD, LOW_THRESHOLD, PASSAGE_THRESHOLD
from app.models import FAQItem


class EmbeddingBackend(ABC):
    @abstractmethod
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encodes a list of strings into normalized 2D numpy array of embeddings."""
        pass


class SentenceTransformerBackend(EmbeddingBackend):
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        from sentence_transformers import SentenceTransformer
        print(f"Loading SentenceTransformer model: {model_name}...")
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(embeddings, dtype=np.float32)


class SimpleTFIDFBackend(EmbeddingBackend):
    """
    Lightweight fallback embedding backend using character n-grams and TF-IDF
    if SentenceTransformers is unavailable or on low-RAM hosts.
    """
    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
        self.is_fit = False

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 128), dtype=np.float32)
        if not self.is_fit:
            # Fit on incoming batch
            matrix = self.vectorizer.fit_transform(texts).toarray()
            self.is_fit = True
        else:
            try:
                matrix = self.vectorizer.transform(texts).toarray()
            except Exception:
                matrix = self.vectorizer.fit_transform(texts).toarray()
        
        # Normalize
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (matrix / norms).astype(np.float32)


_backend_instance: Optional[EmbeddingBackend] = None


def get_embedding_backend() -> EmbeddingBackend:
    global _backend_instance
    if _backend_instance is None:
        try:
            _backend_instance = SentenceTransformerBackend()
        except Exception as e:
            print(f"Warning: Failed to initialize SentenceTransformer ({e}). Falling back to SimpleTFIDFBackend.")
            _backend_instance = SimpleTFIDFBackend()
    return _backend_instance


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def build_business_index(
    business_id: str,
    faqs: List[FAQItem],
    passages: Optional[List[Dict[str, Any]]] = None
) -> Path:
    """
    Embeds all FAQ questions/alt_questions and document passages for a business,
    saving normalized vectors and metadata to data/index/<business_id>.npz
    """
    backend = get_embedding_backend()
    
    raw_texts: List[str] = []
    item_types: List[str] = []   # 'faq' or 'passage'
    target_ids: List[int] = []   # faq_id or passage_id
    full_texts: List[str] = []   # full text string for context

    # 1. Process FAQs
    for faq in faqs:
        # Main question
        q_norm = normalize_text(faq.q)
        if q_norm:
            raw_texts.append(q_norm)
            item_types.append('faq')
            target_ids.append(faq.id)
            full_texts.append(faq.q)

        # Alt questions
        for alt in faq.alt_questions:
            alt_norm = normalize_text(alt)
            if alt_norm:
                raw_texts.append(alt_norm)
                item_types.append('faq')
                target_ids.append(faq.id)
                full_texts.append(alt)

    # 2. Process Passages
    if passages:
        for p in passages:
            p_content = p.get("content", "").strip()
            p_id = p.get("id", 0)
            if p_content:
                raw_texts.append(normalize_text(p_content))
                item_types.append('passage')
                target_ids.append(p_id)
                full_texts.append(p_content)

    index_path = INDEX_DIR / f"{business_id}.npz"

    if not raw_texts:
        # Save empty index if no content
        np.savez_compressed(
            index_path,
            vectors=np.empty((0, 384), dtype=np.float32),
            item_types=np.array([], dtype=str),
            target_ids=np.array([], dtype=int),
            full_texts=np.array([], dtype=str)
        )
        return index_path

    # Encode all texts
    vectors = backend.encode(raw_texts)

    # Save to .npz file
    np.savez_compressed(
        index_path,
        vectors=vectors,
        item_types=np.array(item_types, dtype=str),
        target_ids=np.array(target_ids, dtype=int),
        full_texts=np.array(full_texts, dtype=str)
    )

    return index_path


def query_business_index(business_id: str, query_text: str) -> Dict[str, Any]:
    """
    Computes cosine similarity of query_text against stored vectors for business_id.
    Logs matching scores and returns structured top matches.
    """
    index_path = INDEX_DIR / f"{business_id}.npz"
    if not index_path.exists():
        return {
            "best_faq": None,
            "top_faqs": [],
            "best_passage": None
        }

    try:
        data = np.load(index_path, allow_pickle=True)
        vectors = data["vectors"]
        item_types = data["item_types"]
        target_ids = data["target_ids"]
        full_texts = data["full_texts"]

        if vectors.shape[0] == 0:
            return {
                "best_faq": None,
                "top_faqs": [],
                "best_passage": None
            }

        backend = get_embedding_backend()
        q_norm = normalize_text(query_text)
        if not q_norm:
            return {
                "best_faq": None,
                "top_faqs": [],
                "best_passage": None
            }

        q_vec = backend.encode([q_norm])[0]  # Shape: (D,)

        # Dot product cosine similarity (since vectors are L2 normalized)
        # Handle matrix dimensionality check
        if q_vec.shape[0] != vectors.shape[1]:
            # Vector shape mismatch (e.g. backend changed), rebuild or handle gracefully
            return {"best_faq": None, "top_faqs": [], "best_passage": None}

        scores = np.dot(vectors, q_vec)

        # Aggregate scores per FAQ ID (taking max score for any alt_question of that FAQ)
        faq_scores: Dict[int, Tuple[float, str]] = {}
        passage_scores: Dict[int, Tuple[float, str]] = {}

        for idx, (itype, tid, score, txt) in enumerate(zip(item_types, target_ids, scores, full_texts)):
            s_float = float(score)
            tid_int = int(tid)
            if itype == 'faq':
                if tid_int not in faq_scores or s_float > faq_scores[tid_int][0]:
                    faq_scores[tid_int] = (s_float, str(txt))
            elif itype == 'passage':
                if tid_int not in passage_scores or s_float > passage_scores[tid_int][0]:
                    passage_scores[tid_int] = (s_float, str(txt))

        # Sort FAQ matches by score descending
        sorted_faqs = sorted(
            [{"faq_id": fid, "score": sc, "text": txt} for fid, (sc, txt) in faq_scores.items()],
            key=lambda x: x["score"],
            reverse=True
        )

        # Sort Passage matches by score descending
        sorted_passages = sorted(
            [{"passage_id": pid, "score": sc, "content": txt} for pid, (sc, txt) in passage_scores.items()],
            key=lambda x: x["score"],
            reverse=True
        )

        best_faq = sorted_faqs[0] if sorted_faqs else None
        top_faqs = sorted_faqs[:3]
        best_passage = sorted_passages[0] if sorted_passages else None

        print(f"[MATCHER LOG] Business='{business_id}' Query='{query_text}' | Best FAQ Score={best_faq['score'] if best_faq else 0:.4f} | Best Passage Score={best_passage['score'] if best_passage else 0:.4f}")

        return {
            "best_faq": best_faq,
            "top_faqs": top_faqs,
            "best_passage": best_passage
        }

    except Exception as e:
        print(f"Error querying index for business {business_id}: {e}")
        return {
            "best_faq": None,
            "top_faqs": [],
            "best_passage": None
        }
