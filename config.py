# config.py

# Настройки парсинга
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

RELIABILITY_WEIGHTS = {
    'has_https': 1,
    'has_about_page': 1,
    'has_contact_page': 1,
    'has_legal_info': 2,
    'has_social_links': 1,
    'has_editorial_mention': 1,
    'external_links_score': lambda count: min(2, count // 5)
}

DATABASE_PATH = 'data/news.db'

USE_ML_FOR_TEXT = True  # True - эмбеддинги, False - простое сравнение предложений