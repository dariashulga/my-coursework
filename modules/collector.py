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


sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import REQUEST_TIMEOUT, USER_AGENT


def extract_date_from_html(html, url):
    """
    Продвинутый эвристический парсер даты публикации статьи на основе мета-тегов HTML,
    структуры URL-адреса страницы и тегов временной разметки (<time>).
    """
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    date_str = None

    # Способ 1: Чтение стандартных мета-тегов OpenGraph и DublinCore
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

    # Способ 2: Извлечение даты из пути URL-адреса (регулярные выражения)
    path = urlparse(url).path
    match = re.search(r'(20\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])', path)
    if match:
        year, month, day = match.groups()
        return datetime(int(year), int(month), int(day))

    # Способ 3: Поиск семантического тега времени в разметке страницы
    time_tag = soup.find('time')
    if time_tag and time_tag.get('datetime'):
        try:
            return datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
        except:
            pass
    return None


def fetch_article(url, rss_date=None):
    """
    Многоуровневый загрузчик контента. Скачивает тело статьи, очищает HTML-теги
    и валидирует временные метки публикации.
    """
    domain_lower = urlparse(url).netloc.lower()

    # Фильтрация нетекстовых медиаплатформ для предотвращения смещения временных рамок анализа
    if any(video_service in domain_lower for video_service in ['youtube.com', 'youtu.be', 'vk.com', 'rutube.ru']):
        print(f"   Пропускаем видеохостинг/соцсеть: {urlparse(url).netloc}")
        return None

    if "news.google.com" in url:
        print(f" Обнаружена ссылка Google News, декодируем через экстренный метод...")

    print(f" Загрузка: {url}")

    try:
        # Инициализация первого уровня парсинга через библиотеку newspaper
        config = Config()
        config.browser_user_agent = USER_AGENT
        config.request_timeout = REQUEST_TIMEOUT

        article = Article(url, config=config)
        article.download()
        article.parse()

        # Второй уровень парсинга: применение trafilatura при неудаче базового парсера
        title = article.title
        text = article.text
        date = article.publish_date

        if not text or len(text) < 300:
            print(f"   ⚠️ Мало текста через newspaper, пробую trafilatura...")
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded)

        # Валидация даты: если дата не найдена или совпадает с сегодняшней (ошибка кэша), ищем в HTML
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

        # Использование даты из RSS-потока в качестве стабильного Fallback-значения
        if date is None and rss_date is not None:
            date = rss_date
            print(f" Дата для {urlparse(url).netloc} взята из Google News RSS (Fallback)")

        domain = urlparse(url).netloc
        if domain.startswith('www.'):
            domain = domain[4:]

        # Оценка объема текстовой информации и обработка микроновостей по заголовку
        if not text or len(str(text).strip()) < 30:
            if title and title != 'Без заголовка':
                text = f"Заголовок: {title}. Текст публикации слишком короткий для семантического анализа."
                print(f"   Короткая статья/заметка сохранена по заголовку: {domain}")
            else:
                print(f"   ❌ Слишком мало данных, пропускаем: {url}")
                return None

        time.sleep(1)

        if date and hasattr(date, 'tzinfo') and date.tzinfo is not None:
            date = date.replace(tzinfo=None)

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


def collect_articles_from_urls(google_news_items):
    """
    Управляет пулом потоков загрузки и производит дедубликацию URL-адресов.
    """
    articles = []
    seen_urls = set()
    unique_items = []
    for item in google_news_items:
        if item['url'] not in seen_urls:
            seen_urls.add(item['url'])
            unique_items.append(item)

    for item in unique_items:
        url = item['url']
        rss_date = item['rss_date']

        if url.strip():
            data = fetch_article(url.strip(), rss_date=rss_date)
            if data:
                articles.append(data)

    print(f" Собрано {len(articles)} статей")
    return articles