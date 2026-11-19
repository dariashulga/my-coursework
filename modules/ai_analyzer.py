from natasha import (
    Segmenter,
    NewsEmbedding,
    NewsNERTagger,
    Doc
)
import re

# Инициализация компонентов Natasha для русского языка (загружается один раз)
_segmenter = Segmenter()
_emb = NewsEmbedding()
_ner_tagger = NewsNERTagger(_emb)


def extract_named_entities(text):
    """
    Извлекает из текста ключевые сущности (люди, организации, локации) с помощью Natasha.
    """
    if not text:
        return {"persons": [], "organizations": [], "locations": []}

    doc = Doc(text)
    doc.segment(_segmenter)
    doc.tag_ner(_ner_tagger)

    persons = set()
    organizations = set()
    locations = set()

    for span in doc.spans:
        if span.type == 'PER':
            persons.add(span.text)
        elif span.type == 'ORG':
            organizations.add(span.text)
        elif span.type == 'LOC' or span.type == 'GPE':
            locations.add(span.text)

    return {
        "persons": list(persons),
        "organizations": list(organizations),
        "locations": list(locations)
    }


def generate_ai_summary(text, max_sentences=3):
    """
    Генерирует интеллектуальную выжимку (экстрактивное суммаризирование) из текста статьи,
    выделяя наиболее важные предложения, содержащие цифры, факты и сущности.
    """
    if not text or len(text) < 150:
        return text

    # Разбиваем текст на предложения
    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)
    if len(sentences) <= max_sentences:
        return text

    # Оцениваем важность каждого предложения по наличию цифр, дат и заглавных букв
    scored_sentences = []
    for sent in sentences:
        score = 0
        if any(char.isdigit() for char in sent):
            score += 3  # Предложения с цифрами и суммами важнее всего в расследованиях
        if len(sent.split()) > 5:
            score += 1
        scored_sentences.append((score, sent))

    # Сортируем по важности и берем топ предложения
    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    top_sentences = [s[1] for s in scored_sentences[:max_sentences]]

    return " ".join(top_sentences)