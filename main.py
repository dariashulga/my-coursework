# main.py
import sys
from modules.news_search import search_news_by_keyword, decode_urls_with_selenium
from modules.collector import collect_articles_from_urls  # используем актуальную функцию из твоего коллектора
from modules.analyzer_site import analyze_and_rate_domains
from modules.analyzer_text import analyze_texts
from modules.aggregator import find_original_source
from modules.database import save_analysis_result


def main():
    print("=" * 60)
    print("🚀 OSINT-SYSTEM: ПОИСК ПЕРВОИСТОЧНИКА (Console Version)")
    print("=" * 60)

    # 1. Ввод поискового запроса
    query = input("\n🔎 Введите тему для расследования (например, '9 мая Гродно'): ").strip()
    if not query:
        print("❌ Ошибка: пустой запрос.")
        return

    # 2. Поиск через RSS (Google News)
    print(f"\n📡 Шаг 1/5: Поиск в Google News RSS...")
    raw_urls = search_news_by_keyword(query)
    print(f"✅ Найдено зашифрованных ссылок: {len(raw_urls)}")

    if not raw_urls:
        print("❌ Ничего не найдено.")
        return

    # 3. Дешифровка через Selenium (Твой «взломщик» Google)
    print(f"\n🌐 Шаг 2/5: Дешифровка ссылок через Selenium (может занять время)...")
    clean_urls = decode_urls_with_selenium(raw_urls)
    print(f"✅ Раскрыто реальных адресов: {len(clean_urls)}")

    if not clean_urls:
        print("❌ Не удалось раскрыть ни одной ссылки.")
        return

    # 4. Сбор контента (Текст, заголовки, даты)
    print(f"\n📥 Шаг 3/5: Загрузка текстов статей...")
    articles = collect_articles_from_urls(clean_urls)
    print(f"✅ Успешно загружено статей: {len(articles)}")

    if not articles:
        print("❌ Не удалось получить текст статей.")
        return

    # 5. Анализ (Сайты + Текст)
    print(f"\n⚖️ Шаг 4/5: Анализ надежности и уникальности...")

    # Считаем рейтинг доменов
    domain_scores = analyze_and_rate_domains(articles)
    for art in articles:
        art['reliability_score'] = domain_scores.get(art['domain'], 1)

    # Считаем уникальность через ML
    articles = analyze_texts(articles)

    # 6. Финал: Поиск победителя
    print(f"\n🏆 Шаг 5/5: Определение первоисточника...")
    winner, reason = find_original_source(articles)

    # Сохраняем результат в базу (в папку data)
    for art in articles:
        is_winner = (art['url'] == winner['url'])
        save_analysis_result(art, query, is_winner)

    # ВЫВОД РЕЗУЛЬТАТОВ
    print("\n" + "⭐" * 60)
    print("ИТОГОВОЕ ЗАКЛЮЧЕНИЕ")
    print("⭐" * 60)
    print(f"ПОБЕДИТЕЛЬ: {winner['title']}")
    print(f"ИСТОЧНИК:  {winner['domain']}")
    print(f"ДАТА:      {winner['date']}")
    print(f"УНИКАЛЬНОСТЬ: {winner.get('unique_score', 0):.2f}")
    print(f"РЕЙТИНГ:   {winner['reliability_score']}/5")
    print(f"\nВЕРДИКТ: {reason}")
    print("=" * 60)
    print("✅ Данные сохранены в базу data/news.db")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit()