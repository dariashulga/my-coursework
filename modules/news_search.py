import time
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC


def get_selenium_driver():
    """Настройка невидимого браузера Chrome"""
    chrome_options = Options()
    #chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


# --- ЭТА ФУНКЦИЯ НУЖНА ДЛЯ COLLECTOR.PY ---
def decode_google_news_url(url):
    """Декодирует ОДНУ ссылку через Selenium (совместимость с коллектором)"""
    if "news.google.com" not in url:
        return url

    driver = get_selenium_driver()
    try:
        driver.get(url)
        # Ждем редиректа на реальный сайт
        WebDriverWait(driver, 10).until(lambda d: "google.com" not in d.current_url)
        return driver.current_url
    except:
        return url  # Если не вышло, вернем что было
    finally:
        driver.quit()


def decode_urls_with_selenium(google_urls):
    if not google_urls:
        return []

    print(f"🌐 Запуск браузера...")
    driver = get_selenium_driver()
    decoded_list = []

    # Флаг, чтобы нажать кнопку согласия только один раз за сессию
    consent_accepted = False

    try:
        for url in google_urls:
            try:
                driver.get(url)

                # ШАГ: Проверка на окно согласия (только если еще не нажимали)
                if not consent_accepted:
                    try:
                        # Ищем кнопку по разным вариантам текста (рус, англ)
                        # Используем XPath, который ищет любой элемент <button>, содержащий нужные слова
                        xpath_btn = "//button[contains(., 'Принять') or contains(., 'Accept') or contains(., 'agree') or contains(., 'согласен')]"

                        # Ждем кнопку 3 секунды (этого хватит)
                        consent_button = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, xpath_btn))
                        )
                        consent_button.click()
                        consent_accepted = True
                        print("✅ Окно согласия Google закрыто.")
                        time.sleep(1)  # Даем секунду на прогрузку после клика
                    except:
                        # Если кнопки нет - значит, Google сразу начал редирект, это ок
                        pass

                # ШАГ: Умное ожидание редиректа на сайт СМИ
                try:
                    WebDriverWait(driver, 8).until(
                        lambda d: "google.com" not in d.current_url
                    )
                    final_url = driver.current_url
                    if "news.google.com" not in final_url:
                        decoded_list.append(final_url)
                        print(f"🔗 Раскрыто: {final_url}")
                except TimeoutException:
                    # Если за 8 секунд не ушли с гугла, пробуем принудительно взять URL
                    current = driver.current_url
                    if "google.com" not in current:
                        decoded_list.append(current)
                    else:
                        print(f"⚠️ Не удалось пробиться через: {url[:50]}...")

            except Exception as e:
                print(f"❌ Ошибка на ссылке: {e}")
                continue
    finally:
        driver.quit()

    return decoded_list


def search_news_by_keyword(keyword, days=30):
    print(f"📡 Запрос к Google RSS для фразы: {keyword}")
    encoded_query = quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}+when:{days}d&hl=ru&gl=BY&ceid=BY:ru"

    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []

        root = ET.fromstring(response.content)
        raw_urls = [item.find('link').text for item in root.findall('.//item')]

        print(f"🔄 Найдено {len(raw_urls)} ссылок. Начинаю дешифровку через Selenium...")
        return decode_urls_with_selenium(raw_urls)
    except Exception as e:
        print(f"❌ Ошибка RSS: {e}")
        return []