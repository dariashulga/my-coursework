# ui/streamlit_app.py

import streamlit as st
import sys
import os
import pandas as pd
from datetime import datetime

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from modules.collector import collect_articles_from_urls
from modules.database import save_analysis_result   # только эта функция теперь нужна
from modules.analyzer_site import analyze_and_rate_domains
from modules.analyzer_text import analyze_texts
from modules.aggregator import find_original_source
from modules.news_search import search_news_by_keyword

# Настройка страницы
st.set_page_config(
    page_title="Поиск первоисточника новостей",
    page_icon="📰",
    layout="wide"
)

# Заголовок
st.title(" Автоматизированный поиск первоисточника новостей")
st.markdown("---")

# Боковая панель для ввода данных
with st.sidebar:
    st.header(" Ввод данных")

    input_method = st.radio(
        "Способ ввода:",
        ["Список URL", "Ключевое слово (поиск)"]
    )

    if input_method == "Список URL":
        urls_text = st.text_area(
            "Вставьте ссылки на новости (каждая с новой строки):",
            height=150,
            placeholder="https://ria.ru/...\nhttps://tass.ru/...\nhttps://lenta.ru/..."
        )

        if st.button(" Загрузить и анализировать", type="primary"):
            if urls_text:
                urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
                if urls:
                    st.session_state['urls'] = urls
                    st.session_state['run_analysis'] = True
                else:
                    st.warning("Введите хотя бы один URL")
            else:
                st.warning("Введите ссылки")

    else:  # Ключевое слово
        keyword = st.text_input("Введите ключевую фразу для поиска:", key="keyword_input")

        # --- СЮДА ВСТАВЛЯЕМ СЛАЙДЕР, чтобы он был виден при поиске по слову ---
        st.markdown("### Фильтры поиска")
        search_days = st.slider("Искать новости за последние (дней):", 1, 365, 30)
        # --------------------------------------------------------------------

        if st.button("🔍 Найти и проанализировать", type="primary"):
            if keyword:
                with st.spinner("Поиск и анализ статей..."):
                    # --- ОБНОВЛЯЕМ ВЫЗОВ ФУНКЦИИ (добавляем days=search_days) ---
                    found_urls = search_news_by_keyword(keyword, days=search_days)
                    # -----------------------------------------------------------

                    if found_urls:
                        st.session_state['urls'] = found_urls
                        st.session_state['run_analysis'] = True
                    else:
                        st.warning(
                            "По вашему запросу ничего не найдено. Попробуйте увеличить диапазон дней или сменить ключевые слова.")
            else:
                st.warning("Введите ключевую фразу для поиска.")

    st.markdown("---")
    st.header("⚙️ Дополнительные настройки")  # Немного поправил заголовок для красоты

    use_ml = st.checkbox("Использовать ML для анализа текста", value=True)
    os.environ['USE_ML_FOR_TEXT'] = 'True' if use_ml else 'False'

# Основная область
if 'run_analysis' in st.session_state and st.session_state['run_analysis']:
    with st.spinner(" Сбор и анализ статей..."):
        # Шаг 1: Сбор статей
        st.info(" Шаг 1: Сбор статей по ссылкам...")
        articles = collect_articles_from_urls(st.session_state['urls'])
        if not articles:
            st.error("Не удалось загрузить ни одной статьи. Проверьте ссылки.")
            st.stop()

        #  ---------------- СТАРЫЕ ВЫЗОВЫ УДАЛЕНЫ (save_articles и т.д.) ----------------

        # Шаг 2: Анализ надежности сайтов
        st.info(" Шаг 2: Анализ надежности источников...")
        domain_scores = analyze_and_rate_domains(articles)
        for art in articles:
            art['reliability_score'] = domain_scores.get(art['domain'], 1)

        # Шаг 3: Анализ текста
        st.info(" Шаг 3: Анализ уникальности текстов...")
        articles = analyze_texts(articles)   # добавляет art['unique_score']

        # Шаг 4: Поиск первоисточника
        st.info(" Шаг 4: Определение первоисточника...")
        winner, reason = find_original_source(articles)

        # ========== НОВЫЙ БЛОК – СОХРАНЯЕМ РЕЗУЛЬТАТЫ В БД (без текста) ==========
        # Определяем, использовалось ли ключевое слово
        keyword = None
        if 'keyword_input' in st.session_state and st.session_state.get('keyword_input'):
            keyword = st.session_state.keyword_input

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
                'keyword': keyword
            }
            save_analysis_result(result_data)   # новая функция из database.py

        # ========================================================================

        # Сохраняем результаты в session_state для текущего отображения
        st.session_state['articles'] = articles
        st.session_state['winner'] = winner
        st.session_state['reason'] = reason
        st.session_state['domain_scores'] = domain_scores

        st.success(" Анализ завершен!")
        st.session_state['run_analysis'] = False

# Отображение результатов
if 'articles' in st.session_state:
    articles = st.session_state['articles']
    winner = st.session_state['winner']
    reason = st.session_state['reason']
    domain_scores = st.session_state['domain_scores']

    # Создаем вкладки
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

            # Метрики
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

            # Показываем первых конкурентов
            st.markdown("### Ближайшие конкуренты")
            other_articles = [a for a in articles if a['url'] != winner['url']]
            for a in other_articles[:3]:
                st.markdown(f"- {a['domain']} (рейтинг {a['reliability_score']})")

    with tab2:
        st.header("Рейтинг надежности источников")

        # Таблица рейтингов
        df_reliability = pd.DataFrame([
            {"Домен": domain, "Рейтинг (1-5)": score}
            for domain, score in domain_scores.items()
        ]).sort_values("Рейтинг (1-5)", ascending=False)

        st.dataframe(df_reliability, use_container_width=True)

        # Пояснение
        st.markdown("""
        **Как считается рейтинг:**
        - 5️ Крупное официальное СМИ (есть юр. информация, редакция, соцсети)
        - 4 Известное СМИ с контактами
        - 3️ Региональное СМИ или блог с фактчекингом
        - 2️ Сайт с минимумом информации
        - 1️ Агрегатор или непонятный источник
        """)

    with tab3:
        st.header("Детальный анализ уникальности")

        # График уникальности
        df_unique = pd.DataFrame([
            {
                "Источник": art['domain'],
                "Уникальность": art['unique_score'],
                "Заголовок": art['title'][:50] + "..."
            }
            for art in articles
        ]).sort_values("Уникальность", ascending=False)

        st.bar_chart(df_unique.set_index("Источник")["Уникальность"])
        st.dataframe(df_unique, use_container_width=True)

        # Сравнение с рейтингом
        st.subheader("Связь рейтинга и уникальности")
        df_compare = pd.DataFrame([
            {
                "Источник": art['domain'],
                "Рейтинг": art['reliability_score'],
                "Уникальность": round(art['unique_score'], 2),
                "Дата": art['date'].strftime('%d.%m.%Y') if art['date'] else "неизвестна"
            }
            for art in articles
        ])
        st.dataframe(df_compare, use_container_width=True)

    with tab4:
        st.header("Все загруженные статьи")

        for i, art in enumerate(articles):
            with st.expander(f"{i + 1}. {art['title']}"):
                st.markdown(f"**URL:** [{art['url']}]({art['url']})")
                st.markdown(f"**Домен:** {art['domain']}")
                st.markdown(f"**Дата:** {art['date'].strftime('%d.%m.%Y %H:%M') if art['date'] else 'неизвестна'}")
                st.markdown(f"**Рейтинг надежности:** {art['reliability_score']}/5")
                st.markdown(f"**Уникальность:** {art['unique_score']:.2f}")
                st.markdown("**Фрагмент текста:**")
                st.text(art['text'][:500] + "...")

# Инструкция при первом запуске
else:
    st.info(" Введите ссылки на новости в боковой панели и нажмите 'Загрузить и анализировать'")

    st.markdown("""
    ###  Как работать с системой


    1. **Вставьте ссылки** в левой панели (каждая с новой строки)

    2. **Нажмите "Загрузить и анализировать"**

    3. **Посмотрите результаты**:
       - Кто является первоисточником
       - Рейтинг надежности каждого сайта
       - Уникальность каждой статьи

    """)

    st.markdown("---")
    st.markdown(" **Начните с ввода ссылок в боковой панели!**")