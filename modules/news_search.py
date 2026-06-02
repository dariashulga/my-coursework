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
    """
    Конфигурирует изолированный экземпляр браузера Chrome в режиме Headless
    с персистентным профилем для обхода капчи и блокировок веб-ресурсов.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # Использование выделенной изолированной папки профиля для накопления Cookie-файлов бота
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    bot_profile_path = os.path.join(project_root, "data", "bot_chrome_profile")

    chrome_options.add_argument(f"--user-data-dir={bot_profile_path}")
    chrome_options.add_argument("--profile-directory=BotProfile")

    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        # Откат к полностью чистому экземпляру браузера в случае блокировок сессии
        print(f"⚠️ Ошибка изолированного браузера ({e}), запускаю чистый headless...")
        fallback_options = Options()
        fallback_options.add_argument("--headless")
        fallback_options.add_argument("--no-sandbox")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=fallback_options)

def parse_rss_date(pub_date_str):
    """Преобразует строковое представление даты из формата RSS XML структуры в объект datetime."""
    try:
        pub_date_str = pub_date_str.strip()
        return datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
    except:
        try:
            # Парсинг альтернативных представлений временных зон (сдвиг в часах)
            return datetime.strptime(pub_date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except:
            return None


def decode_urls_with_selenium(google_news_items, max_results=None):
    """
    Декодирует зашифрованные внутренние URL-адреса Google News (news.google.com/articles/...)
    в реальные ссылки целевых новостных изданий посредством эмуляции редиректа в браузере.
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

                # Автоматический клик по модальным окнам согласия (GDPR / Google Cookie Policy)
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
                # Ожидание перенаправления с домена поисковика на конечный сайт новости
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
                # Обработка прерывания потока пользователем из веб-интерфейса Streamlit
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
    """
    Выполняет синтаксический разбор новостного RSS-потока Google News с использованием
    расширенных поисковых операторов (before/after) для фильтрации временного диапазона.
    """
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

        # Разбор XML элементов структуры RSS-ленты поисковой выдачи
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
        return decode_urls_with_selenium(google_news_items, max_results=max_results)
    except Exception as e:
        print(f"❌ Ошибка RSS: {e}")
        return []


def search_news_in_yandex(keyword, start_date=None, end_date=None, max_results=None):
    """
    Улучшенный парсинг Яндекс.Поиска с защитой от блокировок,
    поддержкой временных диапазонов и обработкой капчи.
    """
    # 1. Формируем правильный поисковый запрос Яндекса с учетом дат
    query = keyword
    if start_date and end_date:
        start_str = start_date.strftime('%d.%m.%Y')
        end_str = end_date.strftime('%d.%m.%Y')
        print(f"  Запрос к Яндекс Поиску для фразы: '{keyword}' в диапазоне с {start_str} по {end_str}")
        # Используем легитимный синтаксис Яндекса для фильтрации дат внутри запроса
        query = f"{keyword} date:{start_str}..{end_str}"
    else:
        print(f"  Запрос к Яндекс Поиску для фразы: '{keyword}' за всё время")

    encoded_query = quote(query)
    # Сортировка по времени, чтобы самые ранние/свежие новости были структурированы
    web_url = f"https://yandex.by/search/?text={encoded_query}&lr=157&ft=rev"

    # 2. Запускаем браузер
    print("  Запуск маскированного браузера для обхода защиты Яндекса...")

    chrome_options = Options()
    # Мы НЕ пишем --headless, чтобы дать системе открыться в обычном окне.
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")  # Скрывает, что это Selenium
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # Подключаем папку профиля, чтобы сохранять куки
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    bot_profile_path = os.path.join(project_root, "data", "bot_chrome_profile")
    chrome_options.add_argument(f"--user-data-dir={bot_profile_path}")
    chrome_options.add_argument("--profile-directory=YandexBotProfile")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f" ⚠️ Ошибка профиля, запускаем чистый Chrome: {e}")
        fallback_options = Options()
        fallback_options.add_argument("--disable-blink-features=AutomationControlled")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=fallback_options)

    yandex_news_items = []

    try:
        driver.get(web_url)
        time.sleep(3)

        # 3. УМНЫЙ ПЕРЕХВАТ КАПЧИ
        page_source = driver.page_source.lower()
        if "captcha" in page_source or "робот" in page_source or "checkbox" in page_source:
            print("\n  [ВНИМАНИЕ] Яндекс вывел капчу!")
            print("  У тебя есть 20 секунд, чтобы КЛИКНУТЬ по чекбоксу 'Я не робот' в открывшемся окне браузера...")

            for second in range(20):
                time.sleep(1)
                if "captcha" not in driver.page_source.lower() and "робот" not in driver.page_source.lower():
                    print("  Капча успешно пройдена! Продолжаем сбор данных.")
                    break
            else:
                print(" ❌ Время истекло. Капча не была разгадана. Пропускаем сессию.")
                return []

        # 4. СБОР ССЫЛОК ПО ВАЛИДНЫМ СЕЛЕКТОРАМ ВЫДАЧИ
        # Ищем теги 'a' внутри основного поискового контейнера выдачи Яндекса
        elements = driver.find_elements(By.CSS_SELECTOR, "a.OrganicTitle-Link, a.Link")
        seen_urls = set()

        for elem in elements:
            try:
                url = elem.get_attribute("href")
                if not url:
                    continue

                # отсекаем внутренний мусор Яндекса
                if any(trash in url for trash in
                       ["yandex.", "ya.ru", "pasport", "viber", "telegram", "vk.com", "zen.yandex"]):
                    continue

                if url not in seen_urls and url.startswith("http"):
                    seen_urls.add(url)

                    # Для Яндекса подтягиваем текущее время как базовый фолбэк,
                    yandex_news_items.append({
                        'url': url,
                        'rss_date': datetime.now()
                    })
            except:
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
        except:
            pass
