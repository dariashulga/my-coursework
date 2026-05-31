import time
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote
import requests
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC


def get_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def parse_rss_date(pub_date_str):
    """Конвертирует дату из формата Google RSS (RFC 822) в привычный datetime"""
    try:
        pub_date_str = pub_date_str.strip()
        return datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
    except:
        try:
            # Запасной вариант на случай другого формата часового пояса (например, +0300)
            return datetime.strptime(pub_date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except:
            return None


def decode_urls_with_selenium(google_news_items, max_results=None):
    """
    Принимает список словарей [{'url': ..., 'rss_date': ...}]
    Возвращает список словарей с расшифрованными URL и сохраненной датой из RSS
    """
    if not google_news_items:
        return []

    print(f" Запуск браузера для дешифровки...")
    driver = get_selenium_driver()
    decoded_list = []
    consent_accepted = False

    try:
        for item in google_news_items:
            url = item['url']
            rss_date = item['rss_date']

            if max_results and len(decoded_list) >= max_results:
                print(f" Достигнут лимит в {max_results} успешных ссылок.")
                break

            try:
                driver.get(url)

                if not consent_accepted:
                    try:
                        xpath_btn = "//button[contains(., 'Принять') or contains(., 'Accept') or contains(., 'agree') or contains(., 'согласен')]"
                        consent_button = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, xpath_btn))
                        )
                        consent_button.click()
                        consent_accepted = True
                        print(" Окно согласия Google закрыто.")
                        time.sleep(1)
                    except:
                        pass

                try:
                    WebDriverWait(driver, 8).until(
                        lambda d: "google.com" not in d.current_url
                    )
                    final_url = driver.current_url
                    if "news.google.com" not in final_url:
                        # СОХРАНЯЕМ В СПИСОК И ССЫЛКУ, И ДАТУ ИЗ RSS
                        decoded_list.append({'url': final_url, 'rss_date': rss_date})
                        print(f" Раскрыто ({len(decoded_list)}): {final_url}")
                except TimeoutException:
                    current = driver.current_url
                    if "google.com" not in current:
                        decoded_list.append({'url': current, 'rss_date': rss_date})
                    else:
                        print(f"⚠️ Не удалось пробиться через: {url[:50]}...")

            except BaseException as e:
                err_name = type(e).__name__
                if err_name == "ScriptRunnerStopException" or err_name == "StopException":
                    print(" Пользователь принудительно остановил выполнение в Streamlit! Выходим...")
                    raise e

                err_msg = str(e)
                if any(marker in err_msg for marker in ["localhost", "10061", "Max retries exceeded"]):
                    print("💀 Связь с браузером потеряна (Streamlit был остановлен). Прерываем цикл.")
                    break

                print(f"❌ Ошибка на ссылке: {e}")
                continue
    finally:
        try:
            driver.quit()
            print(" Процесс браузера успешно очищен и закрыт.")
        except:
            pass

    return decoded_list


def search_news_by_keyword(keyword, start_date=None, end_date=None, max_results=None):
    query = keyword

    if start_date and end_date:
        print(f" Строгий поиск в Google RSS для фразы: '{keyword}' в диапазоне с {start_date} по {end_date}")
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        query = f"{keyword} after:{start_str} before:{end_str}"
    else:
        print(f" Запрос к Google RSS для фразы: '{keyword}' за всё время (глубокий поиск)")

    encoded_query = quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ru&gl=BY&ceid=BY:ru"

    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []

        root = ET.fromstring(response.content)

        # СОБИРАЕМ ПАРУ: ССЫЛКА + ДАТА ИЗ RSS
        google_news_items = []
        for item in root.findall('.//item'):
            link_txt = item.find('link').text
            pub_date_txt = item.find('pubDate').text

            parsed_date = parse_rss_date(pub_date_txt)

            google_news_items.append({
                'url': link_txt,
                'rss_date': parsed_date
            })

        print(f" Найдено {len(google_news_items)} сырых ссылок в RSS.")

        # Передаем структурированный список в дешифратор
        return decode_urls_with_selenium(google_news_items, max_results=max_results)
    except Exception as e:
        print(f"❌ Ошибка RSS: {e}")
        return []


def search_news_in_yandex(keyword, start_date=None, end_date=None, max_results=None):
    """Поиск новостей через RSS Яндекса с фильтрацией по датам"""
    query = keyword

    if start_date and end_date:
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')

        query = f"{keyword} date:{start_str}..{end_str}"
        print(f" Строгий поиск в Яндекс RSS для фразы: '{keyword}' в диапазоне {start_str}..{end_str}")
    else:
        print(f" Запрос к Яндекс RSS для фразы: '{keyword}' за всё время")

    encoded_query = quote(query)
    # Формируем поисковую RSS-ссылку Яндекса
    rss_url = f"https://yandex.by/search/rss?text={encoded_query}&lr=157"  # lr=157 — это регион Минск/Беларусь

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ Яндекс вернул код ответа: {response.status_code}")
            return []

        root = ET.fromstring(response.content)

        yandex_news_items = []
        for item in root.findall('.//item'):
            link_txt = item.find('link').text
            pub_date_txt = item.find('pubDate').text

            parsed_date = parse_rss_date(pub_date_txt)

            yandex_news_items.append({
                'url': link_txt,
                'rss_date': parsed_date
            })

        print(f" Найдено {len(yandex_news_items)} сырых ссылок в Яндекс RSS.")

        # Передаем ссылки в наш готовый дешифратор на Selenium
        return decode_urls_with_selenium(yandex_news_items, max_results=max_results)
    except Exception as e:
        print(f"❌ Ошибка Яндекс RSS: {e}")
        return []

def decode_google_news_url():
    return None