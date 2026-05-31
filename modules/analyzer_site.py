# modules/analyzer_site.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import REQUEST_TIMEOUT, USER_AGENT


def analyze_domain(domain):
    print(f" Анализ домена: {domain}")

    features = {
        'has_https': False,
        'has_about_page': False,
        'has_contact_page': False,
        'has_legal_info': False,
        'has_social_links': False,
        'has_editorial_mention': False,
        'external_links_count': 0
    }

    urls_to_try = [f'https://{domain}', f'http://{domain}']

    html = None
    for base_url in urls_to_try:
        try:
            resp = requests.get(base_url, timeout=REQUEST_TIMEOUT,
                                headers={'User-Agent': USER_AGENT})
            if resp.status_code == 200:
                html = resp.text
                features['has_https'] = base_url.startswith('https')
                break
        except:
            continue

    if not html:
        print(f" Не удалось загрузить главную страницу {domain}")
        return features

    soup = BeautifulSoup(html, 'html.parser')
    page_text = html.lower()

    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        link_text = a.get_text().lower()

        if any(word in href or word in link_text for word in ['about', 'о нас', 'about-us']):
            features['has_about_page'] = True
        if any(word in href or word in link_text for word in ['contact', 'контакты', 'kontakt']):
            features['has_contact_page'] = True

        full_url = urljoin(base_url, href)
        if full_url.startswith('http'):
            link_domain = urlparse(full_url).netloc
            if link_domain and link_domain != domain and not link_domain.startswith('www.' + domain):
                features['external_links_count'] += 1

    legal_markers = ['юридический адрес', 'legal address', 'privacy policy',
                     'политика конфиденциальности', 'редакция', 'свидетельство о регистрации']
    for marker in legal_markers:
        if marker in page_text:
            features['has_legal_info'] = True
            break

    social_markers = ['vk.com', 'facebook.com', 'twitter.com', 't.me',
                      'telegram', 'youtube.com', 'ok.ru']
    for marker in social_markers:
        if marker in page_text:
            features['has_social_links'] = True
            break

    editorial_markers = ['редакция', 'editorial', 'главный редактор', 'chief editor']
    for marker in editorial_markers:
        if marker in page_text:
            features['has_editorial_mention'] = True
            break

    time.sleep(0.5)  # вежливость
    return features


def compute_reliability_score(features, _domain=None):
    score = 0

    if features['has_https']:
        score += 1
    if features['has_about_page']:
        score += 1
    if features['has_contact_page']:
        score += 1
    if features['has_legal_info']:
        score += 2
    if features['has_social_links']:
        score += 1
    if features['has_editorial_mention']:
        score += 1

    ext_bonus = min(2, features['external_links_count'] // 10)
    score += ext_bonus

    return min(5, max(1, score))


def analyze_and_rate_domains(articles):
    domains = list(set(art['domain'] for art in articles))
    domain_scores = {}

    for domain in domains:
        features = analyze_domain(domain)
        score = compute_reliability_score(features, domain)
        domain_scores[domain] = score
        print(f" {domain}: рейтинг {score}/5")

    return domain_scores