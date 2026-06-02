import streamlit as st
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

import logging
import warnings

# Блокирование предупреждений библиотек для предотвращения загрязнения логов интерфейса
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("transformers").setLevel(logging.ERROR)


def calculate_relevance_rate(article_text, keyword, article_title=""):
    """
    Рассчитывает процент совпадения слов из запроса с текстом и заголовком статьи.
    """
    if not keyword:
        return 0.0

    # Соединяем заголовок и текст, чтобы поиск шел по всему массиву данных статьи
    combined_text = f"{str(article_title)} {str(article_text)}".lower()
    keyword_lower = keyword.lower()

    # Разбираем поисковый запрос на отдельные слова, очищая от знаков препинания
    raw_words = re.findall(r'[а-яа-ёa-z0-9\-]+', keyword_lower)

    # Исключаем слишком короткие слова/предлоги/союзы (меньше 3 символов)
    significant_words = [w for w in raw_words if len(w) > 2]
    if not significant_words:
        significant_words = raw_words

    if not significant_words:
        return 0.0

    # Функция для базового стемминга
    def get_word_base(word):
        if len(word) <= 3:
            return word
        return re.sub(r'(ами|ями|ов|ев|ей|ия|ие|ий|ый|ому|ему|ах|ях|ом|ем|а|я|о|е|и|ы|у|ь)$', '', word)

    word_bases = [get_word_base(w) for w in significant_words]

    # Считаем совпадения в объединенном тексте (заголовок + тело)
    matched_count = 0
    for base in word_bases:
        if base in combined_text:
            matched_count += 1

    return matched_count / len(significant_words)


st.set_page_config(
    page_title="Поиск первоисточника новостей",
    page_icon="📰",
    layout="wide"
)

st.title(" 📰 Автоматизированный поиск первоисточника новостей")
st.markdown("---")

# --- БЛОК БОКОВОЙ ПАНЕЛИ УПРАВЛЕНИЯ ---
with st.sidebar:
    st.header(" Ввод данных")

    # Выбор режима работы программного комплекса
    input_method = st.radio(
        "Способ ввода:",
        ["Список URL", "Ключевое слово (поиск)"]
    )

    # РЕЖИМ 1: Обработка готовых пользовательских ссылок
    if input_method == "Список URL":
        uploaded_file = st.file_uploader("Или загрузите TXT-файл со ссылками", type=["txt"])

        urls_text = st.text_area(
            "Вставьте ссылки на новости (каждая с новой строки):",
            height=150,
            placeholder="https://belta.by/...n"
                        "https://grodnonews.by/..."
        )

        if st.button(" Загрузить и анализировать", type="primary"):
            final_urls = []

            # Извлечение данных из загруженного текстового файла
            if uploaded_file is not None:
                file_contents = uploaded_file.read().decode("utf-8")
                file_urls = [line.strip() for line in file_contents.splitlines() if line.strip()]
                final_urls.extend(file_urls)

            # Извлечение данных из текстового поля ввода
            if urls_text:
                text_urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
                final_urls.extend(text_urls)

            # Фильтрация дубликатов URL-адресов
            final_urls = list(dict.fromkeys(final_urls))

            if final_urls:
                formatted_items = [{'url': u, 'rss_date': None} for u in final_urls]
                st.session_state['urls'] = formatted_items
                st.session_state['run_analysis'] = True
            else:
                st.warning("Пожалуйста, введите ссылки в поле или загрузите .txt файл.")

    # РЕЖИМ 2: Интеграция с поисковыми системами по ключевому запросу
    else:
        keyword = st.text_input("Введите ключевую фразу для поиска:", key="keyword_input")

        search_engine = st.radio(
            "Поисковая система:",
            ["Google News", "Яндекс Поиск", "Искать везде (Google + Яндекс)"]
        )

        st.markdown("### Период поиска")
        all_time = st.checkbox("Искать за всё время (без привязки к датам)", value=False)

        delta_days = None

        # Расчет временного интервала для поисковых запросов
        if not all_time:
            today = date.today()
            start_date = st.date_input("Начало периода:", today - pd.Timedelta(days=7), max_value=today)
            end_date = st.date_input("Конец периода:", today, max_value=today)

            delta_days = (end_date - start_date).days
            if delta_days <= 0:
                delta_days = 1
        else:
            st.caption(" Поиск будет выполнен по всему доступному архиву.")

        st.markdown("### Количество ссылок")
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

        # Обработка поисковых запросов и агрегация сырых ссылок
        if st.button(" Найти и проанализировать", type="primary"):
            if keyword:
                with st.spinner("Поиск и дешифровка статей..."):

                    # Форматирование дат под синтаксис конкретной поисковой системы
                    if all_time:
                        g_start, g_end = None, None
                        y_start, y_end = None, None
                    else:
                        g_start = start_date
                        g_end = end_date + pd.Timedelta(days=1)
                        y_start = start_date
                        y_end = end_date

                    found_urls = []

                    # Ветвление запросов по выбранным поисковым шлюзам
                    if search_engine == "Google News":
                        found_urls = search_news_by_keyword(keyword, start_date=g_start, end_date=g_end,
                                                            max_results=max_links)

                    elif search_engine == "Яндекс Поиск":
                        found_urls = search_news_in_yandex(keyword, start_date=y_start, end_date=y_end,
                                                           max_results=max_links)

                    elif search_engine == "Искать везде (Google + Яндекс)":
                        st.text(" Сбор данных из Google...")
                        google_res = search_news_by_keyword(keyword, start_date=g_start, end_date=g_end,
                                                            max_results=max_links)

                        st.text(" Сбор данных из Яндекса...")
                        yandex_res = search_news_in_yandex(keyword, start_date=y_start, end_date=y_end,
                                                           max_results=max_links)

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

# --- КОНВЕЙЕР ОБРАБОТКИ И СЕМАНТИЧЕСКОГО АНАЛИЗА ДАННЫХ ---
if 'run_analysis' in st.session_state and st.session_state['run_analysis']:
    with st.spinner(" Сбор и анализ статей..."):

        # Фиксируем точное время старта анализа для отслеживания яндексовских заглушек datetime.now()
        analysis_start_time = datetime.now()

        # Краулинг контента и очистка HTML разметки
        raw_articles = collect_articles_from_urls(st.session_state['urls'])
        if not raw_articles:
            st.error("Не удалось загрузить ни одной статьи. Проверьте доступность ресурсов.")
            st.stop()

        # --- НАЧАЛО СЕМАНТИЧЕСКОЙ ФИЛЬТРАЦИИ ---
        articles = []
        keyword_val = st.session_state.get('keyword_input') if input_method == "Ключевое слово (поиск)" else None

        if input_method == "Ключевое слово (поиск)" and keyword_val:
            raw_kw_words = re.findall(r'[а-яа-ёa-z0-9\-]+', keyword_val.lower())
            sig_kw_words = [w for w in raw_kw_words if len(w) > 2] or raw_kw_words

            for art in raw_articles:
                # 1. Базовый расчет релевантности текста + заголовка
                relevance_rate = calculate_relevance_rate(art['text'], keyword_val, art['title'])

                # 2. Строгая проверка заголовка
                title_lower = art['title'].lower()
                title_matches = 0

                for w in sig_kw_words:
                    base = re.sub(r'(ами|ями|ов|ев|ей|ия|ие|ий|ый|ому|ему|ах|ях|ом|ем|а|я|о|е|и|ы|у|ь)$', '', w)
                    if base in title_lower:
                        title_matches += 1

                title_coverage = title_matches / len(sig_kw_words) if sig_kw_words else 0.0

                # Применяем весовые коэффициенты к релевантности
                if title_coverage >= 0.8:
                    relevance_rate += 5.0  # Огромный приоритет для целевой новости (все слова в заголовке)
                elif title_coverage >= 0.5:
                    relevance_rate += 1.0  # Небольшой бонус для частичных совпадений

                # Пропускаем в финальный пул только те статьи, где есть хоть какой-то намек на контекст
                if relevance_rate >= 0.4:
                    art['relevance_rate'] = relevance_rate
                    articles.append(art)
                else:
                    print(f"   [Семантический фильтр] Отсечена нерелеватная статья ({art['title']})")
        else:
            # Если это режим "Список URL", просто копируем все статьи с максимальным весом
            for art in raw_articles:
                art['relevance_rate'] = 1.0
                articles.append(art)

        # Резервный Fallback: если фильтр отсек вообще всё, принудительно возвращаем все исходные статьи
        if not articles and raw_articles:
            print("   [Семантический фильтр] Предупреждение: все статьи отсечены. Включается резервный режим.")
            for art in raw_articles:
                art['relevance_rate'] = 1.0
                articles.append(art)
        # --- КОНЕЦ СЕМАНТИЧЕСКОЙ ФИЛЬТРАЦИИ ---

        # --- ФИЛЬТРАЦИЯ ПОИСКА И ВАЛИДАЦИЯ ДАТ ---
        cleaned_articles = []
        for art in articles:
            url_lower = art['url'].lower()
            title_lower = art['title'].lower()

            # 1. Вырезаем левые поисковые редиректы, рекламу и мусорные домены, просочившиеся из браузера
            if any(trash in url_lower for trash in
                   ["bing.com/search", "google.com/search", "yandex.by/search", "reklama", "promo"]):
                print(f"   [Фильтр мусора] Исключена системная/рекламная ссылка: {art['url']}")
                continue

            # 2. Если в заголовок попал сам технический поисковый запрос — удаляем
            if "date:" in title_lower or "after:" in title_lower or "before:" in title_lower:
                print(f"   [Фильтр мусора] Исключен битый технический заголовок: {art['title']}")
                continue

            # 3. Безопасная борьба с фейковыми датами Яндекса + жесткая проверка календаря
            if art.get('date'):
                # Проверяем, не является ли дата системной заглушкой datetime.now()
                time_diff = abs((art['date'] - analysis_start_time).total_seconds())
                if time_diff < 5.0:  # Разница меньше 5 секунд означает системный автогенератор Яндекса
                    art['is_date_fake'] = True
                else:
                    art['is_date_fake'] = False

                # Фильтрация по календарному периоду (выбрасываем статьи, не входящие в ползунки дат)
                if input_method == "Ключевое слово (поиск)" and not all_time:
                    article_date = art['date'].date()
                    if not (start_date <= article_date <= end_date):
                        print(
                            f"   [Фильтр дат] Статья полностью удалена (вне диапазона): {art['title']} ({article_date})")
                        continue
            else:
                art['is_date_fake'] = False

            cleaned_articles.append(art)

        articles = cleaned_articles
        # --- КОНЕЦ ФИЛЬТРАЦИИ ---

        # Расчет рейтинга доверия (Reliability Score) для доменов
        domain_scores = analyze_and_rate_domains(articles)
        for art in articles:
            art['reliability_score'] = domain_scores.get(art['domain'], 1)

        # Оценка семантической уникальности текстовых блоков (NLTK / RuBERT)
        articles = analyze_texts(articles)


        # --- ИЕРАРХИЧЕСКОЕ РАНЖИРОВАНИЕ ПЕРВОИСТОЧНИКА ---
        # Сортируем статьи по каскадному принципу:
        # 1. Главный абсолютный критерий: Семантика заголовка и релевантность текста (-rate).
        # 2. Главный хронологический критерий: Время публикации (timestamp от старых к новым). Часы и минуты учитываются строго!
        def get_sorting_priority(x):
            # Базовая релевантность (включает жесткие +5.0 за совпадение ключевых слов в заголовке)
            rate = x.get('relevance_rate', 0.0)

            # Извлекаем временную метку (хронология)
            date_val = x.get('date')

            # Если дата фейковая (не распозналась на сайте Яндекса),
            # ставим огромный искусственный timestamp, уводя статью в самый конец списка результатов
            if x.get('is_date_fake', False):
                timestamp = 3786912000.0  # Коэффициент-штраф
            else:
                timestamp = date_val.timestamp() if date_val else 3786912000.0

            if input_method == "Список URL":
                # В режиме экспресс-анализа по URL текстовый поиск отключен, сортируем строго по времени
                return (0, timestamp)

            return (timestamp, -rate)


        # Выполняем сортировку пула
        sorted_articles = sorted(articles, key=get_sorting_priority)

        if not sorted_articles:
            st.error(
                "❌ В указанном диапазоне дат не найдено релевантных новостей. Попробуйте расширить временной интервал поиска.")
            st.session_state['run_analysis'] = False
            st.stop()

        winner = sorted_articles[0]

        # Переопределяем причину для вывода статуса в интерфейсе
        winner_percent = int(winner.get('relevance_rate', 1.0) * 100)

        # Формируем аргументацию
        if winner_percent >= 500:
            base_reason = f"Статья определена как первоисточник, так как ключевые слова найдены непосредственно в ЗАГОЛОВКЕ, а время публикации является самым ранним в группе ({winner['date'].strftime('%d.%m.%Y %H:%M') if winner['date'] else 'время не указано'})."
        else:
            base_reason = f"Статья выбрана по минимальному временному штампу среди релевантных документов контента."

        reason = base_reason

        # Каскадное сохранение результатов в реляционную базу данных SQLite
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

        # Сохранение финального состояния в кэш сессии Streamlit
        st.session_state['articles'] = articles
        st.session_state['winner'] = winner
        st.session_state['reason'] = reason
        st.session_state['domain_scores'] = domain_scores
        st.session_state['run_analysis'] = False

# --- БЛОК ОТОБРАЖЕНИЯ РЕЗУЛЬТАТОВ ---
if 'articles' in st.session_state:
    articles = st.session_state['articles']
    winner = st.session_state['winner']

    domain_scores = st.session_state.get('domain_scores', {})
    reason = st.session_state.get('reason', 'Первоисточник определен на основе временных и текстовых метрик.')
    keyword_val = st.session_state.get('keyword_input') if input_method == "Ключевое слово (поиск)" else None

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
                st.metric("Рейтинг надежности", f"{winner.get('reliability_score', 1)}/5")
            with mcol2:
                st.metric("Уникальность", f"{winner.get('unique_score', 0.0):.2f}")
            with mcol3:
                st.metric("Длина текста", f"{len(winner.get('text', ''))} симв.")

            st.markdown("---")
            st.subheader(" Экспорт результатов")

            # Формирование структурированного словаря для сериализации в JSON-отчет
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
                    "text_length_chars": len(winner.get('text', ''))
                },
                "selection_reason": reason,
                "all_analyzed_sources": [
                    {
                        "domain": art['domain'],
                        "url": art['url'],
                        "title": art['title'],
                        "date": art['date'].strftime('%d.%m.%Y %H:%M') if art['date'] else "неизвестна",
                        "reliability_score": art.get('reliability_score', 1),
                        "uniqueness_score": round(art.get('unique_score', 0.0), 4),
                        "is_original": (art['url'] == winner['url'])
                    }
                    for art in articles
                ]
            }

            json_string = json.dumps(export_data, ensure_ascii=False, indent=4)
            file_name = f"osint_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            st.download_button(
                label=" Скачать отчет об анализе в JSON",
                data=json_string,
                file_name=file_name,
                mime="application/json",
                type="secondary"
            )

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
            {"Источник": art['domain'], "Уникальность": art.get('unique_score', 0.0),
             "Заголовок": art['title'][:50] + "..."}
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
                st.markdown(f"**Рейтинг надежности:** {art.get('reliability_score', 1)}/5")
                st.markdown(f"**Уникальность:** {art.get('unique_score', 0.0):.2f}")
                st.text(art.get('text', '')[:500] + "...")
else:
    st.info("Введите данные в боковой панели для начала OSINT-мониторинга.")