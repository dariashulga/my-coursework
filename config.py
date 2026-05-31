# config.py

# Настройки Telegram API
TELEGRAM_API_ID = 32534245  # <-- ЗАМЕНИ НА СВОЙ API_ID (БЕЗ КАВЫЧЕК, ПРОСТО ЦИФРЫ)
TELEGRAM_API_HASH = '79512e608761d264488303a0c482ca1c'  # <-- ЗАМЕНИ НА СВОЙ API_HASH (В КАВЫЧКАХ)
# Токен нашего OSINT-бота
TELEGRAM_BOT_TOKEN = '8726214132:AAEAGE1y8v2gOqF4rEtFrYbey5xP3KwDSJ0'

# Список топовых белорусских новостных каналов для мониторинга
# Сюда мы можем дописывать любые открытые каналы (без знака @)
TELEGRAM_CHANNELS = [
    'belta_telegramm',        # БЕЛТА
    'newgrodno',     # Новости Гродно
    'grodnoplus',   # АвтоГродно
    'vestiminska',    # Минск-Новости
]

# Настройки парсинга
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Веса для рейтинга надежности (сумма преобразуется в рейтинг 1-5)
RELIABILITY_WEIGHTS = {
    'has_https': 1,
    'has_about_page': 1,
    'has_contact_page': 1,
    'has_legal_info': 2,
    'has_social_links': 1,
    'has_editorial_mention': 1,
    'external_links_score': lambda count: min(2, count // 5)  # ссылки на другие сайты
}

# Путь к базе данных
DATABASE_PATH = 'data/news.db'

# Режимы работы
USE_ML_FOR_TEXT = True  # True - эмбеддинги, False - простое сравнение предложений