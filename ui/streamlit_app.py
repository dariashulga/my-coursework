import streamlit as st
import sys
import os
import pandas as pd
from datetime import datetime, date

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from modules.collector import collect_articles_from_urls
from modules.database import save_analysis_result
from modules.analyzer_site import analyze_and_rate_domains
from modules.analyzer_text import analyze_texts
from modules.aggregator import find_original_source
from modules.news_search import search_news_by_keyword, search_news_in_yandex # <-- Добавь импорт

# Настройка страницы
st.set_page_config(
    page_title="Поиск первоисточника новостей",
    page_icon="📰",
    layout="wide"
)

st.title(" Автоматизированный поиск первоисточника новостей")
st.markdown("---")

with st.sidebar:
    st.header(" Ввод данных")

    input_method = st.radio(
        "Способ ввода:",
        ["Список URL", "Ключевое слово (поиск)"]
    )

    if input_method == "Список URL":

        uploaded_file = st.file_uploader("Или загрузите TXT-файл со ссылками", type=["txt"])

        urls_text = st.text_area(
            "Вставьте ссылки на новости (каждая с новой строки):",
            height=150,
            placeholder="https://belta.by/...\nhttps://grodnonews.by/..."
        )

        if st.button(" Загрузить и анализировать", type="primary"):
            final_urls = []

            # 1. Читаем ссылки из загруженного файла .txt (если он прикреплен)
            if uploaded_file is not None:
                file_contents = uploaded_file.read().decode("utf-8")
                file_urls = [line.strip() for line in file_contents.splitlines() if line.strip()]
                final_urls.extend(file_urls)

            # 2. Читаем ссылки из текстового поля text_area
            if urls_text:
                text_urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
                final_urls.extend(text_urls)

            # Убираем дубликаты, сохраняя порядок
            final_urls = list(dict.fromkeys(final_urls))

            if final_urls:
                # ВАЖНЫЙ СТЫК: Упаковываем ссылки в формат [{'url': u, 'rss_date': None}, ...]
                # Теперь collector.py получит структуру, которую ожидает!
                formatted_items = [{'url': u, 'rss_date': None} for u in final_urls]

                # Записываем в session_state и даем команду на старт
                st.session_state['urls'] = formatted_items
                st.session_state['run_analysis'] = True
            else:
                st.warning("Пожалуйста, введите ссылки в поле или загрузите .txt файл.")

    else:  # Ключевое слово
        keyword = st.text_input("Введите ключевую фразу для поиска:", key="keyword_input")

        # --- НАШ НОВЫЙ ВЫБОР ПОИСКОВИКА ---
        search_engine = st.radio(
            "Поисковая система:",
            ["Google News", "Яндекс Поиск", "Искать везде (Google + Яндекс)"]
        )

        st.markdown("### 📅 Период поиска")
        # Использование интерактивного календаря для выбора диапазона дат
        all_time = st.checkbox("Искать за всё время (без привязки к датам)", value=False)

        delta_days = None  # По умолчанию дней нет

        if not all_time:
            # Если галочка НЕ стоит, показываем календарь
            today = date.today()
            start_date = st.date_input("Начало периода:", today - pd.Timedelta(days=7), max_value=today)
            end_date = st.date_input("Конец периода:", today, max_value=today)

            delta_days = (end_date - start_date).days
            if delta_days <= 0:
                delta_days = 1
        else:
            # Если галочка стоит, пишем информационный текст
            st.caption("ℹ️ Поиск будет выполнен по всему доступному архиву Google News.")

        st.markdown("### 🔢 Количество ссылок")
        limit_mode = st.radio(
            "Сколько новостей обработать?",
            ["Найти абсолютно все", "Задать точный лимит"]
        )

        max_links = None
        if limit_mode == "Задать точный лимит":
            max_links = st.number_input(
                "Укажите максимальное число успешных новостей:",
                min_value=1,
                max_value=100,
                value=20,
                step=1
            )

        if st.button("🔍 Найти и проанализировать", type="primary"):
            if keyword:
                with st.spinner("Поиск и дешифровка статей..."):

                    # Готовим даты для Google (с запасом в +1 день)
                    if all_time:
                        g_start, g_end = None, None
                        y_start, y_end = None, None
                    else:
                        g_start = start_date
                        g_end = end_date + pd.Timedelta(days=1)
                        y_start = start_date
                        y_end = end_date

                    found_urls = []

                    # ВЕТВЛЕНИЕ В ЗАВИСИМОСТИ ОТ ВЫБРАННОГО ПОИСКОВИКА
                    if search_engine == "Google News":
                        found_urls = search_news_by_keyword(keyword, start_date=g_start, end_date=g_end,
                                                            max_results=max_links)

                    elif search_engine == "Яндекс Поиск":
                        found_urls = search_news_in_yandex(keyword, start_date=y_start, end_date=y_end,
                                                           max_results=max_links)

                    elif search_engine == "Искать везде (Google + Яндекс)":
                        st.text("🔎 Сбор данных из Google...")
                        google_res = search_news_by_keyword(keyword, start_date=g_start, end_date=g_end,
                                                            max_results=max_links)

                        st.text("🔎 Сбор данных из Яндекса...")
                        yandex_res = search_news_in_yandex(keyword, start_date=y_start, end_date=y_end,
                                                           max_results=max_links)

                        # Объединяем результаты
                        found_urls = google_res + yandex_res

                    if found_urls:
                        st.session_state['urls'] = found_urls
                        st.session_state['run_analysis'] = True
                    else:
                        st.warning("По вашему запросу ничего не найдено. Попробуйте изменить параметры.")
            else:
                st.warning("Введите ключевую фразу для поиска.")

    st.markdown("---")
    st.header("⚙️ Дополнительные настройки")
    use_ml = st.checkbox("Использовать ML для анализа текста", value=True)
    os.environ['USE_ML_FOR_TEXT'] = 'True' if use_ml else 'False'

# --- Логика анализа и вкладок отображения результатов (остается без изменений) ---
if 'run_analysis' in st.session_state and st.session_state['run_analysis']:
    with st.spinner(" Сбор и анализ статей..."):
        articles = collect_articles_from_urls(st.session_state['urls'])
        if not articles:
            st.error("Не удалось загрузить ни одной статьи. Проверьте доступность ресурсов.")
            st.stop()

        domain_scores = analyze_and_rate_domains(articles)
        for art in articles:
            art['reliability_score'] = domain_scores.get(art['domain'], 1)

        articles = analyze_texts(articles)
        winner, reason = find_original_source(articles)

        keyword_val = st.session_state.get('keyword_input') if input_method == "Ключевое слово (поиск)" else None

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

        st.success(" Анализ завершен!")
        st.session_state['run_analysis'] = False

if 'articles' in st.session_state:
    articles = st.session_state['articles']
    winner = st.session_state['winner']
    reason = st.session_state['reason']
    domain_scores = st.session_state['domain_scores']

    tab1, tab2, tab3, tab4 = st.tabs([
        " Первоисточник",
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
            st.markdown(f"**Домен:** {winner['domain']}")
            date_str = winner['date'].strftime('%d.%m.%Y %H:%M') if winner['date'] else "неизвестна"
            st.markdown(f"**Дата публикации:** {date_str}")

            mcol1, mcol2, mcol3 = st.columns(3)
            with mcol1:
                st.metric("Рейтинг надежности", f"{winner['reliability_score']}/5")
            with mcol2:
                st.metric("Уникальность", f"{winner['unique_score']:.2f}")
            with mcol3:
                st.metric("Длина текста", f"{len(winner['text'])} симв.")
        with col2:
            st.info("### Причина выбора")
            st.markdown(f"_{reason}_")

    with tab2:
        st.header("Рейтинг надежности источников")
        df_reliability = pd.DataFrame([
            {"Домен": domain, "Рейтинг (1-5)": score}
            for domain, score in domain_scores.items()
        ]).sort_values("Рейтинг (1-5)", ascending=False)
        st.dataframe(df_reliability, use_container_width=True)

    with tab3:
        st.header("Детальный анализ уникальности")
        df_unique = pd.DataFrame([
            {"Источник": art['domain'], "Уникальность": art['unique_score'], "Заголовок": art['title'][:50] + "..."}
            for art in articles
        ]).sort_values("Уникальность", ascending=False)
        st.bar_chart(df_unique.set_index("Источник")["Уникальность"])
        st.dataframe(df_unique, use_container_width=True)

    with tab4:
        st.header("Все загруженные статьи")
        for i, art in enumerate(articles):
            with st.expander(f"{i + 1}. {art['title']}"):
                st.markdown(f"**URL:** [{art['url']}]({art['url']})")
                st.markdown(f"**Домен:** {art['domain']}")
                st.markdown(f"**Дата:** {art['date'].strftime('%d.%m.%Y %H:%M') if art['date'] else 'неизвестна'}")
                st.markdown(f"**Рейтинг надежности:** {art['reliability_score']}/5")
                st.markdown(f"**Уникальность:** {art['unique_score']:.2f}")
                st.text(art['text'][:500] + "...")
else:
    st.info("Введите данные в боковой панели для начала OSINT-мониторинга.")