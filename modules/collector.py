# modules/collector.py

import requests
from newspaper import Article, Config
import trafilatura
from datetime import datetime
from urllib.parse import urlparse
import sys
import os
import time
import re
from bs4 import BeautifulSoup

# --- ДОБАВЛЯЕМ ИМПОРТ НАШЕГО ДЕКОДЕРА ---
# Мы берем его из news_search.py, который ты правила раньше
from modules.news_search import decode_google_news_url

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import REQUEST_TIMEOUT, USER_AGENT


# (Функция extract_date_from_html остается без изменений...)
def extract_date_from_html(html, url):
    """ (Твой код без изменений) """
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    date_str = None
    meta_properties = ['article:published_time', 'og:published_time', 'publication_date', 'date']
    for prop in meta_properties:
        meta = soup.find('meta', property=prop) or soup.find('meta', attrs={'name': prop})
        if meta and meta.get('content'):
            date_str = meta['content']
            break
    if date_str:
        try:
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(date_str[:19], fmt)
                except:
                    continue
        except:
            pass
    path = urlparse(url).path
    match = re.search(r'(20\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])', path)
    if match:
        year, month, day = match.groups()
        return datetime(int(year), int(month), int(day))
    time_tag = soup.find('time')
    if time_tag and time_tag.get('datetime'):
        try:
            return datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
        except:
            pass
    return None


def fetch_article(url):
    # Теперь url уже должен быть чистым,
    # но оставим проверку на всякий случай
    if "news.google.com" in url:
        print(f" 🔗 Обнаружена ссылка Google News, декодируем через экстренный метод...")
        # Если вдруг проскочила гугл-ссылка, этот принт подскажет

    print(f" 📥 Загрузка: {url}")

    try:
        # 1. Настройка "личности" браузера
        config = Config()
        config.browser_user_agent = USER_AGENT
        config.request_timeout = REQUEST_TIMEOUT

        # 2. Пробуем загрузить через newspaper3k
        article = Article(url, config=config)
        article.download()
        article.parse()

        title = article.title
        text = article.text
        date = article.publish_date

        # 3. Если newspaper не справился, зовем trafilatura
        if not text or len(text) < 300:
            print(f"   ⚠️ Мало текста через newspaper, пробую trafilatura...")
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded)

        # 4. Поиск даты в HTML вручную
        if not date or (date and date.date() == datetime.now().date()):
            try:
                resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                                    headers={'User-Agent': USER_AGENT})
                if resp.status_code == 200:
                    html_date = extract_date_from_html(resp.text, url)
                    if html_date:
                        date = html_date
            except:
                pass

        # 5. Извлекаем домен
        domain = urlparse(url).netloc
        if domain.startswith('www.'):
            domain = domain[4:]

        # 6. Финальная проверка
        if not text or len(text) < 200:
            print(f"   ❌ Слишком мало данных: {url}")
            return None

        # Пауза
        time.sleep(1)

        # Убираем часовой пояс
        if date and hasattr(date, 'tzinfo') and date.tzinfo is not None:
            date = date.replace(tzinfo=None)

        # ТУТ ВАЖНО: Если после всех манипуляций мы всё еще на google.com,
        # значит декодер не сработал.
        if "google.com" in domain:
            print(f"   ⚠️ Ошибка: Ссылка осталась заблокированной Google. Пропускаем.")
            return None

        return {
            'url': url,
            'domain': domain,
            'title': title or 'Без заголовка',
            'text': text,
            'date': date
        }

    except Exception as e:
        print(f" ❌ Критическая ошибка загрузки {url}: {e}")
        return None


def collect_articles_from_urls(url_list):
    """ (Твой код без изменений) """
    articles = []
    # Убираем дубликаты из списка
    url_list = list(set(url_list))

    for url in url_list:
        if url.strip():
            data = fetch_article(url.strip())
            if data:
                articles.append(data)
    print(f" ✅ Собрано {len(articles)} статей")
    return articles