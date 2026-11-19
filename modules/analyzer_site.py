import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import REQUEST_TIMEOUT, USER_AGENT
from modules.analyzer_infrastructure import analyze_infrastructure


def analyze_domain(domain):
    """
    Выполняет комплексный OSINT-аудит домена: проверяет структуру сайта,
    наличие юридических маркеров, данных редакции и запрашивает параметры Whois/SSL.
    """
    print(f" Анализ домена: {domain}")

    features = {
        'has_https': False,
        'has_about_page': False,
        'has_contact_page': False,
        'has_legal_info': False,
        'has_social_links': False,
        'has_editorial_mention': False,
        'age_days': 0
    }

    # 1. Подтягиваем технические данные (Whois + SSL) через наш модуль инфраструктуры
    try:
        infra = analyze_infrastructure(domain)
        whois_data = infra.get('whois', {})
        ssl_data = infra.get('ssl', {})

        features['has_https'] = ssl_data.get('has_ssl', False)
        features['age_days'] = whois_data.get('age_days') or 0
    except Exception as e:
        print(f"   ⚠️ Ошибка получения Whois/SSL для {domain}: {e}")

    # 2. Краулинг главной страницы для анализа контентных маркеров доверия
    urls_to_try = [f'https://{domain}', f'http://{domain}']
    html = None
    base_url_used = None

    for base_url in urls_to_try:
        try:
            resp = requests.get(base_url, timeout=REQUEST_TIMEOUT,
                                headers={'User-Agent': USER_AGENT})
            if resp.status_code == 200:
                html = resp.text
                base_url_used = base_url
                if base_url.startswith('https') and not features['has_https']:
                    features['has_https'] = True
                break
        except:
            continue

    if not html:
        print(f"   ⚠️ Не удалось загрузить главную страницу {domain}, оцениваем по техническим метрикам.")
        return compute_reliability_score(features, domain)

    soup = BeautifulSoup(html, 'html.parser')
    page_text = html.lower()

    # Поиск ссылок на разделы о нас и контакты
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        link_text = a.get_text().lower()

        if any(word in href or word in link_text for word in ['about', 'о нас', 'о проекте', 'about-us']):
            features['has_about_page'] = True
        if any(word in href or word in link_text for word in ['contact', 'контакты', 'kontakt', 'обратная связь']):
            features['has_contact_page'] = True

    # Контентные маркеры
    if any(marker in page_text for marker in
           ['юридический адрес', 'legal address', 'privacy policy', 'политика конфиденциальности',
            'свидетельство о государственной регистрации']):
        features['has_legal_info'] = True

    if any(marker in page_text for marker in ['vk.com', 't.me', 'telegram', 'youtube.com', 'ok.ru']):
        features['has_social_links'] = True

    if any(marker in page_text for marker in
           ['редакция', 'editorial', 'главный редактор', 'chief editor', 'журналист']):
        features['has_editorial_mention'] = True

    time.sleep(0.3)
    return compute_reliability_score(features, domain)


def compute_reliability_score(features, domain=None):
    """
    Строгая аддитивная модель расчета рейтинга доверия (от 1 до 5)
    на основе верифицируемых факторов прозрачности ресурса.
    """
    # Базовый уровень для любого доступного сайта в сети
    score = 1

    # Фактор 1: Техническая безопасность (Наличие SSL-сертификата)
    if features.get('has_https'):
        score += 1

    # Фактор 2: Историческая стабильность (Возраст домена по Whois > 1 года)
    age = features.get('age_days', 0)
    if age and age > 365:
        score += 1

    # Фактор 3: Информационная прозрачность (Контакты + Раздел "О нас")
    if features.get('has_about_page') or features.get('has_contact_page'):
        score += 1

    # Фактор 4: Юридическая ответственность и редакция (Юр. инфо + Упоминание редакции)
    if features.get('has_legal_info') or features.get('has_editorial_mention'):
        score += 1

    # Известные верифицированные СМИ Беларуси (Белый список авторитета)
    trusted_media = ['belta.by', 'gp.by', 'sb.by', 'mlyn.by', 'ndsmi.by', 'sport5.by', 'grodnonews.by']
    if domain in trusted_media:
        score = max(score, 4)  # Гарантируем высокий балл для проверенных республиканских/региональных СМИ

    return min(5, max(1, score))


def analyze_and_rate_domains(articles):
    """
    Групповой расчет рейтинга надежности для всех уникальных доменов в выборке.
    """
    domains = list(set(art['domain'] for art in articles))
    domain_scores = {}

    for domain in domains:
        score = analyze_domain(domain)
        domain_scores[domain] = score
        print(f" {domain}: рейтинг {score}/5")

    return domain_scores