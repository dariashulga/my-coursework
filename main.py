import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.news_search import search_news_by_keyword, search_news_in_yandex
from modules.collector import collect_articles_from_urls
from modules.analyzer_site import analyze_and_rate_domains
from modules.analyzer_text import analyze_texts
from modules.aggregator import find_original_source
from modules.database import save_analysis_result


def main():
    print("=" * 60)
    print(" OSINT-SYSTEM: ПОИСК ПЕРВОИСТОЧНИКА (Console Version)")
    print("=" * 60)

    query = input("\n Введите тему для расследования (например, 'последний звонок Гродно'): ").strip()
    if not query:
        print(" Ошибка: пустой запрос.")
        return

    # Сбор данных из двух поисковых систем (Google + Яндекс)
    print(f"\n Шаг 1/4: Поиск и автоматическая дешифровка ссылок...")

    print(" Сканирование Google News RSS...")
    google_res = search_news_by_keyword(query)
    print(f"   Найдено и раскрыто через Google: {len(google_res)} ссылок.")

    print(" Сканирование Яндекс RSS...")
    yandex_res = search_news_in_yandex(query)
    print(f"   Найдено и раскрыто через Яндекс: {len(yandex_res)} ссылок.")

    combined_items = google_res + yandex_res
    print(f" Всего уникальных сырых объектов для анализа: {len(combined_items)}")

    if not combined_items:
        print(" ️ Ничего не найдено ни в одном из источников.")
        return

    print(f"\n Шаг 2/4: Загрузка контента и извлечение метаданных статей...")
    articles = collect_articles_from_urls(combined_items)
    print(f" Успешно загружено и очищено статей: {len(articles)}")

    if not articles:
        print(" Не удалось получить валидный текст статей для анализа.")
        return

    print(f"\n Шаг 3/4: Экспертная оценка надежности доменов и уникальности текстов...")

    domain_scores = analyze_and_rate_domains(articles)
    for art in articles:
        art['reliability_score'] = domain_scores.get(art['domain'], 1)

    articles = analyze_texts(articles)

    print(f"\n Шаг 4/4: Математическое определение первоисточника...")
    winner, reason = find_original_source(articles)

    # Синхронизация консольных результатов с общей базой данных проекта
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
            'keyword': query
        }
        save_analysis_result(result_data)

    print("\n" + "=" * 60)
    print(" ИТОВЫЙ ВЕРДИКТ OSINT-РАССЛЕДОВАНИЯ")
    print("=" * 60)
    print(f" ПЕРВОИСТОЧНИК: {winner['title']}")
    print(f" URL:          {winner['url']}")
    print(f" ДОМЕН:        {winner['domain']}")

    date_str = winner['date'].strftime('%d.%m.%Y %H:%M') if winner['date'] else "неизвестна"
    print(f" ДАТА ПУБЛ.:   {date_str}")
    print(f" УНИКАЛЬНОСТЬ: {winner.get('unique_score', 0.0):.2f}")
    print(f" НАДЕЖНОСТЬ:   {winner['reliability_score']}/5")
    print(f"\n ОБОСНОВАНИЕ СИСТЕМЫ:\n_{reason}_")
    print("=" * 60)
    print(" Все результаты успешно залогированы в базу данных data/news.db")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n Программа принудительно остановлена пользователем.")
        sys.exit()