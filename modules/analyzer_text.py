# modules/analyzer_text.py

import os
import logging
import warnings

# Глушим системные предупреждения Windows, HuggingFace и PyTorch
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("transformers").setLevel(logging.ERROR)

from transformers.utils import logging as transformers_logging
transformers_logging.set_verbosity_error()

import nltk
from nltk.tokenize import sent_tokenize
import sys
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import USE_ML_FOR_TEXT

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None and USE_ML_FOR_TEXT:
        try:
            from sentence_transformers import SentenceTransformer
            print(" Загрузка ML модели...")
            _embedding_model = SentenceTransformer('cointegrated/rubert-tiny2')
            print(" ML модель загружена")
        except Exception as e:
            print(f" Ошибка загрузки модели: {e}")
    return _embedding_model


def preprocess_sentences(text):
    if not text:
        return []

    try:
        sentences = sent_tokenize(text)
    except:
        sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 20]

    cleaned = []
    for s in sentences:
        s = s.strip()
        if len(s) > 20:
            cleaned.append(s.lower())
    return cleaned


def count_unique_sentences(articles_texts):
    all_sentences = [preprocess_sentences(text) for text in articles_texts]

    unique_counts = []
    for i, sentences_i in enumerate(all_sentences):
        other_sentences = set()
        for j, sentences_j in enumerate(all_sentences):
            if j != i:
                other_sentences.update(sentences_j)

        unique = sum(1 for sent in sentences_i if sent not in other_sentences)
        unique_counts.append(unique)

    return unique_counts


def calculate_uniqueness_ml(articles_texts):
    model = get_embedding_model()
    if model is None:
        return count_unique_sentences(articles_texts)

    embeddings = []
    for text in articles_texts:
        # Берём первые 2000 символов (достаточно для смысла)
        truncated = text[:2000] if text else ""
        emb = model.encode(truncated, normalize_embeddings=True)
        embeddings.append(emb)

    uniqueness = []
    for i, emb_i in enumerate(embeddings):
        similarities = []
        for j, emb_j in enumerate(embeddings):
            if i != j:
                sim = np.dot(emb_i, emb_j)
                similarities.append(sim)
        avg_sim = np.mean(similarities) if similarities else 0
        uniqueness.append(1 - avg_sim)

    return uniqueness


def analyze_texts(articles):
    texts = [art['text'] for art in articles]

    if USE_ML_FOR_TEXT:
        print(" Используем ML для анализа текста...")
        unique_scores = calculate_uniqueness_ml(texts)
    else:
        print(" Используем простое сравнение предложений...")
        unique_scores = count_unique_sentences(texts)

    for i, art in enumerate(articles):
        art['unique_score'] = float(unique_scores[i])
        print(f"   {art['title'][:50]}...: уникальность {art['unique_score']:.2f}")

    return articles