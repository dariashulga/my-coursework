import streamlit as st
import streamlit.components.v1 as components
import sys
import re
import os
import pandas as pd
import json
from datetime import datetime, date

# Настройка системных путей для импорта внутренних модулей проекта
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from modules.collector import collect_articles_from_urls
from modules.database import save_analysis_result
from modules.analyzer_site import analyze_and_rate_domains
from modules.analyzer_text import analyze_texts
from modules.aggregator import find_original_source
from modules.news_search import search_news_by_keyword, search_news_in_yandex
from modules.analyzer_infrastructure import analyze_infrastructure
from modules.graph_builder import build_propagation_graph
from modules.ai_analyzer import extract_named_entities, generate_ai_summary

import logging
import warnings

# Блокирование предупреждений библиотек
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("transformers").setLevel(logging.ERROR)


def calculate_relevance_rate(article_text, keyword, article_title=""):
    if not keyword:
        return 0.0

    combined_text = f"{str(article_title)} {str(article_text)}".lower()
    keyword_lower = keyword.lower()

    raw_words = re.findall(r'[а-яа-ёa-z0-9\-]+', keyword_lower)
    significant_words = [w for w in raw_words if len(w) > 2] or raw_words

    if not significant_words:
        return 0.0

    def get_word_base(word):
        if len(word) <= 3:
            return word
        return re.sub(r'(ами|ями|ов|ев|ей|ия|ие|ий|ый|ому|ему|ах|ях|ом|ем|а|я|о|е|и|ы|у|ь)$', '', word)

    word_bases = [get_word_base(w) for w in significant_words]

    matched_count = 0
    for base in word_bases:
        if base in combined_text:
            matched_count += 1

    return matched_count / len(significant_words)


st.set_page_config(
    page_title="OSINT-Система верификации первоисточников",
    page_icon="📰",
    layout="wide"
)

st.markdown("""
    <style>
    div[data-testid="stStatusWidget"] {
        visibility: hidden;
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📰 OSINT-Система верификации первоисточников веб-контента")
st.caption("Модуль анализа сетевой инфраструктуры, семантической уникальности и графового моделирования")
st.markdown("---")

# --- БЛОК БОКОВОЙ ПАНЕЛИ УПРАВЛЕНИЯ ---
with st.sidebar:
    st.header("🔍 Ввод данных")

    input_method = st.radio(
        "Способ ввода:",
        ["Список URL", "Ключевое слово (поиск)"]
    )

    if input_method == "Список URL":
        uploaded_file = st.file_uploader("Загрузите TXT-файл со ссылками", type=["txt"])
        urls_text = st.text_area(
            "Вставьте ссылки на новости (по одной в строке):",
            height=150,
            placeholder="https://belta.by/...\nhttps://grodnonews.by/..."
        )

        if st.button(" Загрузить и анализировать", type="primary"):
            final_urls = []
            if uploaded_file is not None:
                file_contents = uploaded_file.read().decode("utf-8")
                file_urls = [line.strip() for line in file_contents.splitlines() if line.strip()]
                final_urls.extend(file_urls)

            if urls_text:
                text_urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
                final_urls.extend(text_urls)

            final_urls = list(dict.fromkeys(final_urls))

            if final_urls:
                formatted_items = [{'url': u, 'rss_date': None} for u in final_urls]
                st.session_state['urls'] = formatted_items
                st.session_state['run_analysis'] = True
            else:
                st.warning("Пожалуйста, введите ссылки в поле или загрузите .txt файл.")

    else:
        keyword = st.text_input("Введите ключевую фразу для поиска:", key="keyword_input")
        search_engine = st.radio(
            "Поисковая система:",
            ["Google News", "Яндекс Поиск", "Искать везде (Google + Яндекс)"]
        )

        st.markdown("### Период поиска")
        all_time = st.checkbox("Искать за всё время", value=False)
        delta_days = None

        if not all_time:
            today = date.today()
            start_date = st.date_input("Начало периода:", today - pd.Timedelta(days=7), max_value=today)
            end_date = st.date_input("Конец периода:", today, max_value=today)
            delta_days = (end_date - start_date).days
            if delta_days <= 0:
                delta_days = 1

        st.markdown("### Количество ссылок")
        limit_mode = st.radio("Сколько новостей обработать?", ["Найти абсолютно все", "Задать точный лимит"])
        max_links = None
        if limit_mode == "Задать точный лимит":
            max_links = st.number_input("Максимальное число новостей:", min_value=1, max_value=100, value=20, step=1)

        if st.button(" Найти и проанализировать", type="primary"):
            if keyword:
                with st.spinner("Поиск и дешифровка статей..."):
                    if all_time:
                        g_start, g_end, y_start, y_end = None, None, None, None
                    else:
                        g_start, g_end = start_date, end_date + pd.Timedelta(days=1)
                        y_start, y_end = start_date, end_date

                    found_urls = []
                    if search_engine == "Google News":
                        found_urls = search_news_by_keyword(keyword, start_date=g_start, end_date=g_end,
                                                            max_results=max_links)
                    elif search_engine == "Яндекс Поиск":
                        found_urls = search_news_in_yandex(keyword, start_date=y_start, end_date=y_end,
                                                           max_results=max_links)
                    elif search_engine == "Искать везде (Google + Яндекс)":
                        g_res = search_news_by_keyword(keyword, start_date=g_start, end_date=g_end,
                                                       max_results=max_links)
                        y_res = search_news_in_yandex(keyword, start_date=y_start, end_date=y_end,
                                                      max_results=max_links)
                        found_urls = g_res + y_res

                    if found_urls:
                        st.session_state['urls'] = found_urls
                        st.session_state['run_analysis'] = True
                    else:
                        st.warning("По вашему запросу ничего не найдено.")
            else:
                st.warning("Введите ключевую фразу для поиска.")

    st.markdown("---")
    st.header("⚙️ Настройки ML")
    use_ml = st.checkbox("Использовать ML для анализа текста", value=True)
    os.environ['USE_ML_FOR_TEXT'] = 'True' if use_ml else 'False'

# --- КОНВЕЙЕР ОБРАБОТКИ ---
if 'run_analysis' in st.session_state and st.session_state['run_analysis']:
    with st.spinner("⚡ Сбор контента, семантический анализ и аудит инфраструктуры..."):
        analysis_start_time = datetime.now()
        raw_articles = collect_articles_from_urls(st.session_state['urls'])

        if not raw_articles:
            st.error("Не удалось загрузить ни одной статьи.")
            st.stop()

        articles = []
        keyword_val = st.session_state.get('keyword_input') if input_method == "Ключевое слово (поиск)" else None

        if input_method == "Ключевое слово (поиск)" and keyword_val:
            raw_kw_words = re.findall(r'[а-яа-ёa-z0-9\-]+', keyword_val.lower())
            sig_kw_words = [w for w in raw_kw_words if len(w) > 2] or raw_kw_words

            for art in raw_articles:
                relevance_rate = calculate_relevance_rate(art['text'], keyword_val, art['title'])
                title_lower = art['title'].lower()
                title_matches = sum(1 for w in sig_kw_words if
                                    re.sub(r'(ами|ями|ов|ев|ей|ия|ие|ий|ый|ому|ему|ах|ях|ом|ем|а|я|о|е|и|ы|у|ь)$', '',
                                           w) in title_lower)
                title_coverage = title_matches / len(sig_kw_words) if sig_kw_words else 0.0

                if title_coverage >= 0.8:
                    relevance_rate += 5.0
                elif title_coverage >= 0.5:
                    relevance_rate += 1.0

                if relevance_rate >= 0.4:
                    art['relevance_rate'] = relevance_rate
                    articles.append(art)

        else:
            for art in raw_articles:
                art['relevance_rate'] = 1.0
                articles.append(art)

        if not articles and raw_articles:
            for art in raw_articles:
                art['relevance_rate'] = 1.0
                articles.append(art)

        cleaned_articles = []
        for art in articles:
            url_lower = art['url'].lower()
            title_lower = art['title'].lower()

            if any(trash in url_lower for trash in
                   ["bing.com/search", "google.com/search", "yandex.by/search", "reklama", "promo"]):
                continue
            if "date:" in title_lower or "after:" in title_lower or "before:" in title_lower:
                continue

            if art.get('date'):
                time_diff = abs((art['date'] - analysis_start_time).total_seconds())
                art['is_date_fake'] = (time_diff < 5.0)
                if input_method == "Ключевое слово (поиск)" and not all_time:
                    article_date = art['date'].date()
                    if not (start_date <= article_date <= end_date):
                        continue
            else:
                art['is_date_fake'] = False

            cleaned_articles.append(art)

        articles = cleaned_articles

        domain_scores = analyze_and_rate_domains(articles)
        for art in articles:
            art['reliability_score'] = domain_scores.get(art['domain'], 1)

        articles = analyze_texts(articles)

        # 🤖 Генерируем ИИ-выжимку (Summary) для КАЖДОЙ статьи заранее
        for art in articles:
            art['ai_summary'] = generate_ai_summary(art.get('text', ''))


        def get_sorting_priority(x):
            rate = x.get('relevance_rate', 0.0)
            date_val = x.get('date')
            timestamp = 3786912000.0 if (x.get('is_date_fake', False) or not date_val) else date_val.timestamp()
            return (0, timestamp) if input_method == "Список URL" else (timestamp, -rate)


        sorted_articles = sorted(articles, key=get_sorting_priority)

        if not sorted_articles:
            st.error("❌ В указанном диапазоне дат не найдено релевантных новостей.")
            st.session_state['run_analysis'] = False
            st.stop()

        winner = sorted_articles[0]
        reason = f"Статья выбрана по наименьшему временному штампу и релевантности заголовка ({winner['date'].strftime('%d.%m.%Y %H:%M') if winner['date'] else 'время не указано'})."

        # ВЫЗОВ НОВЫХ МОДУЛЕЙ
        infra_info = analyze_infrastructure(winner['domain'])
        graph_html_path = build_propagation_graph(articles, winner)

        # Сохранение в БД
        for art in articles:
            is_original = (art['url'] == winner['url'])
            result_data = {
                'url': art['url'],
                'domain': art['domain'],
                'title': art['title'],
                'date': art['date'],
                'reliability_score': art['reliability_score'],
                'uniqueness_score': art['unique_score'],
                'is_original_source': is_original,
                'keyword': keyword_val
            }
            save_analysis_result(result_data)

        st.session_state['articles'] = articles
        st.session_state['winner'] = winner
        st.session_state['reason'] = reason
        st.session_state['domain_scores'] = domain_scores
        st.session_state['infra_info'] = infra_info
        st.session_state['graph_html_path'] = graph_html_path
        st.session_state['run_analysis'] = False

# --- БЛОК ОТОБРАЖЕНИЯ РЕЗУЛЬТАТОВ ---
if 'articles' in st.session_state:
    articles = st.session_state['articles']
    winner = st.session_state['winner']
    domain_scores = st.session_state.get('domain_scores', {})
    infra_info = st.session_state.get('infra_info', {})
    graph_html_path = st.session_state.get('graph_html_path', '')
    reason = st.session_state.get('reason', '')
    keyword_val = st.session_state.get('keyword_input') if input_method == "Ключевое слово (поиск)" else None

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        " Первоисточник",
        " Граф распространения",
        " Сетевая безопасность",
        " Рейтинг источников",
        " Детальный анализ",
        " Все статьи"
    ])

    with tab1:
        st.header("Первоисточник новости")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.success(f"### {winner['title']}")
            st.markdown(f"**URL:** [{winner['url']}]({winner['url']})")
            st.markdown(f"**Домен:** `{winner['domain']}`")
            date_str = winner['date'].strftime('%d.%m.%Y %H:%M') if winner['date'] else "неизвестна"
            st.markdown(f"**Дата публикации:** {date_str}")

            mcol1, mcol2, mcol3 = st.columns(3)
            with mcol1:
                st.metric("Рейтинг надежности", f"{winner.get('reliability_score', 1)}/5")
            with mcol2:
                st.metric("Уникальность", f"{winner.get('unique_score', 0.0):.2f}")
            with mcol3:
                st.metric("Длина текста", f"{len(winner.get('text', ''))} симв.")

            st.markdown("---")
            st.subheader("🤖 ИИ-анализ и суммаризация инцидента")

            # Используем уже готовое саммари из словаря победителя
            ai_summary = winner.get('ai_summary', '')
            entities = extract_named_entities(winner.get('text', ''))

            st.info(f"**Краткая выжимка (Summary):**\n\n{ai_summary}")

            st.markdown("**👤 Фигуранты / Персоны:** " + (
                ", ".join(entities['persons']) if entities['persons'] else "Не обнаружено"))
            st.markdown("**🏢 Организации:** " + (
                ", ".join(entities['organizations']) if entities['organizations'] else "Не обнаружено"))
            st.markdown(
                "**📍 Локации:** " + (", ".join(entities['locations']) if entities['locations'] else "Не обнаружено"))

            st.markdown("---")
            st.subheader("📥 Экспорт результатов")

            export_data = {
                "analysis_date": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "method": input_method,
                "query_keyword": keyword_val,
                "detected_original_source": {
                    "title": winner['title'],
                    "url": winner['url'],
                    "domain": winner['domain'],
                    "publication_date": date_str,
                    "reliability_score": winner.get('reliability_score', 1),
                    "uniqueness_score": round(winner.get('unique_score', 0.0), 4),
                    "infrastructure": infra_info,
                    "ai_summary": ai_summary,
                    "entities": entities
                },
                "selection_reason": reason
            }

            json_string = json.dumps(export_data, ensure_ascii=False, indent=4)
            st.download_button(
                label="📥 Скачать полный OSINT-отчет в JSON",
                data=json_string,
                file_name=f"osint_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

        with col2:
            st.info("### Причина выбора")
            st.markdown(f"_{reason}_")

    with tab2:
        st.header("🕸️ Дерево распространения инфоповода")
        st.caption(
            "Интерактивный граф: красным выделен первоисточник, синим — сайты-рерайтеры. На стрелках указана временная задержка.")

        if graph_html_path and os.path.exists(graph_html_path):
            with open(graph_html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            components.html(html_content, height=530, scrolling=True)
        else:
            st.warning("Граф не сформирован.")

    with tab3:
        st.header("🛡️ Аудит сетевой инфраструктуры доменов")
        st.caption("Технический паспорт сервера для выявления фишинга, анонимных ресурсов и оценки доверия.")

        all_domains = list(dict.fromkeys([art['domain'] for art in articles]))
        default_index = all_domains.index(winner['domain']) if winner['domain'] in all_domains else 0

        selected_domain = st.selectbox(
            " Выберите домен для проведения OSINT-аудита:",
            options=all_domains,
            index=default_index
        )

        if selected_domain:
            with st.spinner(f" Проверка Whois, SSL и IP для {selected_domain}..."):
                current_infra = analyze_infrastructure(selected_domain)

            w_data = current_infra.get('whois', {})
            ssl_data = current_infra.get('ssl', {})
            domain_rank = domain_scores.get(selected_domain, 1)

            st.markdown("---")
            st.subheader(f"📊 Результаты аудита: `{selected_domain}` (Базовый рейтинг: {domain_rank}/5)")

            if w_data.get('is_suspicious_age'):
                st.error("⚠️ ВНИМАНИЕ: Домену меньше 30 дней! Высокий риск фишинга или фейкового вброса!")

            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                st.markdown("### 🌐 Домен (Whois)")
                st.markdown(f"**Зарегистрирован:** `{w_data.get('registered_domain')}`")
                st.markdown(f"**Дата создания:** {w_data.get('creation_date')}")
                st.markdown(
                    f"**Возраст домена:** {w_data.get('age_days') if w_data.get('age_days') is not None else 'н/д'} дней")
                st.markdown(f"**Регистратор:** {w_data.get('registrar')}")

            with sc2:
                st.markdown("### 🔒 SSL / HTTPS")
                st.markdown(f"**Наличие SSL:** {'✅ Есть' if ssl_data.get('has_ssl') else '❌ Отсутствует'}")
                st.markdown(f"**Издатель:** {ssl_data.get('ssl_issuer')}")
                st.markdown(f"**Действителен до:** {ssl_data.get('ssl_expires')}")

            with sc3:
                st.markdown("### 🖥️ Сетевой узел")
                st.markdown(f"**IP-адрес:** `{ssl_data.get('ip_address')}`")

    with tab4:
        st.header("📊 Рейтинг надежности источников")
        df_reliability = pd.DataFrame([
            {"Домен": domain, "Рейтинг (1-5)": score}
            for domain, score in domain_scores.items()
        ]).sort_values("Рейтинг (1-5)", ascending=False)
        st.dataframe(df_reliability, use_container_width=True)

    with tab5:
        st.header("📈 Детальный анализ уникальности")
        df_unique = pd.DataFrame([
            {"Источник": art['domain'], "Уникальность": art.get('unique_score', 0.0),
             "Заголовок": art['title'][:50] + "..."}
            for art in articles
        ]).sort_values("Уникальность", ascending=False)
        st.bar_chart(df_unique.set_index("Источник")["Уникальность"])
        st.dataframe(df_unique, use_container_width=True)

    with tab6:
        st.header("📑 Все загруженные статьи")
        for i, art in enumerate(articles):
            with st.expander(f"{i + 1}. {art['title']} ({art['domain']})"):
                st.markdown(f"**URL:** [{art['url']}]({art['url']})")
                st.markdown(f"**Домен:** `{art['domain']}`")
                st.markdown(f"**Дата:** {art['date'].strftime('%d.%m.%Y %H:%M') if art['date'] else 'неизвестна'}")
                st.markdown(f"**Рейтинг надежности:** {art.get('reliability_score', 1)}/5")
                st.markdown(f"**Уникальность:** {art.get('unique_score', 0.0):.2f}")

                # 🤖 Вывод ИИ-выжимки для каждой статьи
                st.info(f"**ИИ-выжимка:** {art.get('ai_summary', 'Нет данных')}")

                st.text(art.get('text', '')[:500] + "...")
else:
    st.info("Введите данные в боковой панели для начала OSINT-мониторинга.")