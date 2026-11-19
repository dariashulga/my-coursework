import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


def _build_chrome_driver(options):
    """
    Создаёт экземпляр webdriver.Chrome:
    - на Linux (например, Streamlit Cloud) использует системные chromium и chromedriver;
    - на Windows/локально использует webdriver-manager.
    """
    chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
    chromedriver_path = shutil.which("chromedriver")

    if chromium_path and chromedriver_path:
        options.binary_location = chromium_path
        service = Service(chromedriver_path)
        return webdriver.Chrome(service=service, options=options)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def get_selenium_driver():
    """
    Конфигурирует изолированный экземпляр браузера Chrome в режиме Headless
    с персистентным профилем для обхода редиректов и блокировок веб-ресурсов.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    bot_profile_path = os.path.join(project_root, "data", "bot_chrome_profile")

    chrome_options.add_argument(f"--user-data-dir={bot_profile_path}")
    chrome_options.add_argument("--profile-directory=BotProfile")

    try:
        return _build_chrome_driver(chrome_options)
    except Exception as e:
        print(f"⚠️ Ошибка изолированного браузера ({e}), запускаю чистый headless...")
        fallback_options = Options()
        fallback_options.add_argument("--headless=new")
        fallback_options.add_argument("--no-sandbox")
        fallback_options.add_argument("--disable-dev-shm-usage")
        fallback_options.add_argument("--disable-gpu")
        return _build_chrome_driver(fallback_options)


def parse_rss_date(pub_date_str):
    """Преобразует строковое представление даты из формата RSS XML структуры в объект datetime."""
    if not pub_date_str:
        return None
    try:
        pub_date_str = pub_date_str.strip()
        return datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
    except Exception:
        try:
            return datetime.strptime(pub_date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except Exception:
            return None


def decode_urls_with_selenium(google_news_items, max_results=None):
    """
    Декодирует зашифрованные внутренние URL-адреса Google News (news.google.com/articles/...)
    в реальные ссылки целевых новостных изданий посредством эмуляции редиректа в браузере.
    """
    if not google_news_items:
        return []

    print(" Запуск браузера для дешифровки...")
    driver = get_selenium_driver()
    decoded_list = []
    consent_accepted = False

    try:
        for item in google_news_items:
            url = item["url"]
            rss_date = item["rss_date"]

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
                    except Exception:
                        pass

                try:
                    WebDriverWait(driver, 8).until(
                        lambda d: "google.com" not in d.current_url
                    )
                    final_url = driver.current_url
                    if "news.google.com" not in final_url:
                        decoded_list.append({"url": final_url, "rss_date": rss_date})
                        print(f" Раскрыто ({len(decoded_list)}): {final_url}")
                except TimeoutException:
                    current = driver.current_url
                    if "google.com" not in current:
                        decoded_list.append({"url": current, "rss_date": rss_date})
                    else:
                        print(f" Не удалось пробиться через: {url[:50]}...")

            except BaseException as e:
                err_name = type(e).__name__
                if err_name in ("ScriptRunnerStopException", "StopException"):
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
        except Exception:
            pass

    return decoded_list


def search_news_by_keyword(keyword, start_date=None, end_date=None, max_results=None):
    """
    Выполняет синтаксический разбор новостного RSS-потока Google News с использованием
    расширенных поисковых операторов (before/after) для фильтрации временного диапазона.
    """
    query = keyword

    if start_date and end_date:
        print(f" Строгий поиск в Google RSS для фразы: '{keyword}' в диапазоне с {start_date} по {end_date}")
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        query = f"{keyword} after:{start_str} before:{end_str}"
    else:
        print(f" Запрос к Google RSS для фразы: '{keyword}' за всё время (глубокий поиск)")

    encoded_query = quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ru&gl=BY&ceid=BY:ru"

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []

        root = ET.fromstring(response.content)

        google_news_items = []
        for item in root.findall(".//item"):
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            if link_elem is None or not link_elem.text:
                continue

            parsed_date = parse_rss_date(pub_date_elem.text if pub_date_elem is not None else None)
            google_news_items.append({
                "url": link_elem.text,
                "rss_date": parsed_date
            })

        print(f" Найдено {len(google_news_items)} сырых ссылок в RSS.")
        return decode_urls_with_selenium(google_news_items, max_results=max_results)
    except Exception as e:
        print(f"❌ Ошибка RSS: {e}")
        return []


def search_news_in_yandex(keyword, start_date=None, end_date=None, max_results=None):
    """
    Экспериментальный парсинг Яндекс.Поиска с поддержкой временных диапазонов
    и защитой от блокировок. Если дата в метаданных страницы не найдена,
    rss_date остаётся None (без подстановки текущей даты).
    """
    query = keyword
    if start_date and end_date:
        start_str = start_date.strftime("%d.%m.%Y")
        end_str = end_date.strftime("%d.%m.%Y")
        print(f"  Запрос к Яндекс Поиску для фразы: '{keyword}' в диапазоне с {start_str} по {end_str}")
        query = f"{keyword} date:{start_str}..{end_str}"
    else:
        print(f"  Запрос к Яндекс Поиску для фразы: '{keyword}' за всё время")

    encoded_query = quote(query)
    web_url = f"https://yandex.by/search/?text={encoded_query}&lr=157&ft=rev"

    print("  Запуск браузера для поиска в Яндексе...")

    is_linux = shutil.which("chromium") or shutil.which("chromium-browser")

    chrome_options = Options()
    if is_linux:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    bot_profile_path = os.path.join(project_root, "data", "bot_chrome_profile")
    chrome_options.add_argument(f"--user-data-dir={bot_profile_path}")
    chrome_options.add_argument("--profile-directory=YandexBotProfile")

    try:
        driver = _build_chrome_driver(chrome_options)
    except Exception as e:
        print(f" ⚠️ Ошибка профиля, запускаем чистый Chrome: {e}")
        fallback_options = Options()
        if is_linux:
            fallback_options.add_argument("--headless=new")
        fallback_options.add_argument("--no-sandbox")
        fallback_options.add_argument("--disable-dev-shm-usage")
        fallback_options.add_argument("--disable-blink-features=AutomationControlled")
        driver = _build_chrome_driver(fallback_options)

    yandex_news_items = []

    try:
        driver.get(web_url)
        time.sleep(3)

        page_source = driver.page_source.lower()
        if "captcha" in page_source or "робот" in page_source or "checkbox" in page_source:
            if is_linux:
                print(" ❌ Яндекс вывел капчу в headless-режиме на сервере. Пропускаем.")
                return []

            print("\n  [ВНИМАНИЕ] Яндекс вывел капчу!")
            print("  У тебя есть 20 секунд, чтобы КЛИКНУТЬ по чекбоксу 'Я не робот' в открывшемся окне браузера...")

            for _ in range(20):
                time.sleep(1)
                if "captcha" not in driver.page_source.lower() and "робот" not in driver.page_source.lower():
                    print("  Капча успешно пройдена! Продолжаем сбор данных.")
                    break
            else:
                print(" ❌ Время истекло. Капча не была разгадана. Пропускаем сессию.")
                return []

        elements = driver.find_elements(By.CSS_SELECTOR, "a.OrganicTitle-Link, a.Link")
        seen_urls = set()

        trash_domains_or_ext = [
            "yandex.", "ya.ru", "pasport", "viber", "telegram",
            "vk.com", "zen.yandex", "google.", "bing.", ".pdf"
        ]

        for elem in elements:
            try:
                url = elem.get_attribute("href")
                if not url:
                    continue

                url_lower = url.lower()
                if any(trash in url_lower for trash in trash_domains_or_ext):
                    continue

                if url not in seen_urls and url.startswith("http"):
                    seen_urls.add(url)
                    yandex_news_items.append({
                        "url": url,
                        "rss_date": None
                    })
            except Exception:
                continue

        print(f" Успешно извлечено {len(yandex_news_items)} уникальных новостных ссылок из Яндекса.")

        if max_results:
            yandex_news_items = yandex_news_items[:max_results]

        return yandex_news_items

    except Exception as e:
        print(f" ❌ Ошибка при работе с Яндексом: {e}")
        return []
    finally:
        try:
            driver.quit()
            print(" Браузер Яндекса успешно закрыт.")
        except Exception:
            pass