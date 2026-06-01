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

import os


def get_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    bot_profile_path = os.path.join(project_root, "data", "bot_chrome_profile")

    chrome_options.add_argument(f"--user-data-dir={bot_profile_path}")
    chrome_options.add_argument("--profile-directory=BotProfile")

    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"⚠️ Ошибка изолированного браузера ({e}), запускаю чистый headless...")
        fallback_options = Options()
        fallback_options.add_argument("--headless")
        fallback_options.add_argument("--no-sandbox")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=fallback_options)

def parse_rss_date(pub_date_str):
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
                        print(f" Не удалось пробиться через: {url[:50]}...")

            except BaseException as e:
                err_name = type(e).__name__
                if err_name == "ScriptRunnerStopException" or err_name == "StopException":
                    print(" Пользователь принудительно остановил выполнение в Streamlit! Выходим...")
                    raise e

                err_msg = str(e)
                if any(marker in err_msg for marker in ["localhost", "10061", "Max retries exceeded"]):
                    print(" Связь с браузером потеряна (Streamlit был остановлен). Прерываем цикл.")
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
    query = keyword
    print(f" Запрос к Яндекс Поиску для фразы: '{keyword}'")

    encoded_query = quote(query)
    # Используем URL обычного веб-поиска, так как он открывается у тебя идеально!
    web_url = f"https://yandex.by/search/?text={encoded_query}&lr=157"

    driver = get_selenium_driver()
    yandex_news_items = []

    try:
        driver.get(web_url)
        time.sleep(4)

        page_source = driver.page_source.lower()
        if "captcha" in page_source or "робот" in page_source:
            print(" Яндекс заблокировал запрос капчей. Пропускаем.")
            return []

        elements = driver.find_elements(By.TAG_NAME, "a")

        seen_urls = set()
        for elem in elements:
            try:
                url = elem.get_attribute("href")
                if not url:
                    continue

                if "yandex." in url or "ya.ru" in url or "pasport" in url or "viber" in url or "telegram" in url:
                    continue

                if url not in seen_urls and (url.startswith("http://") or url.startswith("https://")):
                    seen_urls.add(url)


                    yandex_news_items.append({
                        'url': url,
                        'rss_date': datetime.now()
                    })
            except:
                continue

        print(f" Извлечено {len(yandex_news_items)} уникальных ссылок из выдачи Яндекса.")

        if max_results:
            yandex_news_items = yandex_news_items[:max_results]

        return yandex_news_items

    except Exception as e:
        print(f"❌ Ошибка при сборе данных из Яндекса: {e}")
        return []
    finally:
        try:
            driver.quit()
            print(" Браузер Яндекса успешно закрыт.")
        except:
            pass

def decode_google_news_url():
    return None