# modules/analyzer_text.py

import nltk
from nltk.tokenize import sent_tokenize
import sys
import os
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import USE_ML_FOR_TEXT

# Глобальная переменная для модели (чтобы загрузить один раз)
_embedding_model = None


def get_embedding_model():
    """Ленивая загрузка модели эмбеддингов"""
    global _embedding_model
    if _embedding_model is None and USE_ML_FOR_TEXT:
        try:
            from sentence_transformers import SentenceTransformer
            print(" Загрузка ML модели...")
            # Лёгкая русскоязычная модель
            _embedding_model = SentenceTransformer('cointegrated/rubert-tiny2')
            print(" ML модель загружена")
        except Exception as e:
            print(f" Ошибка загрузки модели: {e}")
    return _embedding_model


def preprocess_sentences(text):
    """
    Разбивает текст на предложения и очищает их
    """
    if not text:
        return []

    try:
        sentences = sent_tokenize(text)
    except:
        # Если nltk не сработал, грубо режем по точкам
        sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 20]

    cleaned = []
    for s in sentences:
        s = s.strip()
        # Убираем слишком короткие (это не предложения)
        if len(s) > 20:
            cleaned.append(s.lower())
    return cleaned


def count_unique_sentences(articles_texts):
    """
    Метод 1: простое сравнение предложений (эвристика)
    Возвращает список - сколько уникальных предложений в каждой статье
    """
    # Разбиваем все тексты на предложения
    all_sentences = [preprocess_sentences(text) for text in articles_texts]

    unique_counts = []
    for i, sentences_i in enumerate(all_sentences):
        # Собираем все предложения из других статей
        other_sentences = set()
        for j, sentences_j in enumerate(all_sentences):
            if j != i:
                other_sentences.update(sentences_j)

        # Считаем уникальные для i-й статьи
        unique = sum(1 for sent in sentences_i if sent not in other_sentences)
        unique_counts.append(unique)

    return unique_counts


def calculate_uniqueness_ml(articles_texts):
    """
    Метод 2: использование эмбеддингов (ML)
    Возвращает список - оценку уникальности для каждой статьи
    """
    model = get_embedding_model()
    if model is None:
        # Если модель не загрузилась, используем простой метод
        return count_unique_sentences(articles_texts)

    # Получаем эмбеддинги для всех текстов (обрезаем до 512 токенов)
    embeddings = []
    for text in articles_texts:
        # Берём первые 2000 символов (достаточно для смысла)
        truncated = text[:2000] if text else ""
        emb = model.encode(truncated, normalize_embeddings=True)
        embeddings.append(emb)

    # Считаем "уникальность" как среднюю косинусную дистанцию до других
    uniqueness = []
    for i, emb_i in enumerate(embeddings):
        similarities = []
        for j, emb_j in enumerate(embeddings):
            if i != j:
                # Косинусная близость (чем меньше, тем уникальнее)
                sim = np.dot(emb_i, emb_j)
                similarities.append(sim)
        # Уникальность = 1 - средняя близость
        avg_sim = np.mean(similarities) if similarities else 0
        uniqueness.append(1 - avg_sim)

    return uniqueness


def analyze_texts(articles):
    """
    Главная функция анализа текстов
    Возвращает список статей с добавленным полем unique_score
    """
    texts = [art['text'] for art in articles]

    if USE_ML_FOR_TEXT:
        print(" Используем ML для анализа текста...")
        unique_scores = calculate_uniqueness_ml(texts)
    else:
        print(" Используем простое сравнение предложений...")
        unique_scores = count_unique_sentences(texts)

    # Добавляем результат в статьи
    for i, art in enumerate(articles):
        art['unique_score'] = float(unique_scores[i])
        print(f"   {art['title'][:50]}...: уникальность {art['unique_score']:.2f}")

    return articles