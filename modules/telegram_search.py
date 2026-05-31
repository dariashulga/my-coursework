import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Подключаем конфигурацию проекта
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import TELEGRAM_CHANNELS


def search_news_in_telegram(keyword, start_date=None, end_date=None, max_results=None):
    """
    Прямой OSINT-парсер веб-витрин Telegram-каналов.
    Забирает самые свежие посты в реальном времени, обходя задержки индексации Google.
    """
    print(f"🕵️‍♂️ Запущен прямой веб-анализ TG-каналов для фразы: '{keyword}'")
    found_posts = []
    keyword_lower = keyword.lower()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for channel in TELEGRAM_CHANNELS:
        if max_results and len(found_posts) >= max_results:
            break

        # Ссылка на публичную веб-витрину канала, которая отдается без авторизации
        channel_url = f"https://t.me/s/{channel}"
        print(f"📡 Сканирование ленты: {channel_url}...")

        try:
            response = requests.get(channel_url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"   ⚠️ Канал {channel} вернул статус: {response.status_code}")
                continue

            # Парсим HTML-код страницы канала
            soup = BeautifulSoup(response.text, 'html.parser')

            # В веб-версии Telegram каждый пост лежит в блоке с классом 'tgme_widget_message'
            messages = soup.find_all('div', class_='tgme_widget_message')

            for msg in messages:
                if max_results and len(found_posts) >= max_results:
                    break

                # Ищем текст сообщения
                text_div = msg.find('div', class_='tgme_widget_message_text')
                if not text_div:
                    continue

                text = text_div.get_text()

                # Проверяем наличие ключевого слова
                if keyword_lower in text.lower():
                    # Извлекаем ссылку на конкретный пост
                    # Она лежит в теге <a> внутри класса 'tgme_widget_message_date'
                    date_link_tag = msg.find('a', class_='tgme_widget_message_date')
                    if date_link_tag and 'href' in date_link_tag.attrs:
                        post_url = date_link_tag['href']
                        # Превращаем внутреннюю ссылку /s/ обратно в стандартную
                        post_url = post_url.replace("t.me/s/", "t.me/")
                    else:
                        continue

                    # Извлекаем дату для фильтрации (если она есть в теге <time>)
                    time_tag = msg.find('time')
                    msg_date = datetime.now()  # По умолчанию текущая
                    if time_tag and 'datetime' in time_tag.attrs:
                        try:
                            # Telegram отдает дату в формате ISO, например: 2026-05-30T14:23:01+00:00
                            raw_date = time_tag['datetime'].split('T')[0]
                            msg_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                        except Exception:
                            pass

                    # Проверка диапазона дат
                    if start_date and end_date:
                        if not (start_date <= msg_date <= end_date):
                            continue

                    found_posts.append({
                        'url': post_url,
                        'rss_date': datetime.combine(msg_date, datetime.min.time())
                    })
                    print(f"   🎯 Найдено прямое совпадение: {post_url}")

        except Exception as e:
            print(f"   ⚠️ Ошибка парсинга веб-ленты {channel}: {e}")

    return found_posts