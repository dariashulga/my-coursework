# modules/aggregator.py

from datetime import datetime, timezone
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def make_timezone_naive(dt):
    """
        Приводит объект datetime к единому формату UTC и удаляет информацию о таймзоне
        для корректного сравнения дат между собой.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def find_original_source(articles):
    """
        Алгоритм определения первоисточника на основе временного фактора,
        рейтинга доверия ресурса и семантической уникальности текста.
    """
    if not articles:
        return None, "Нет статей для анализа"

    # Подготавливаем статьи: нормализуем даты и фильтруем
    valid_articles = []
    for art in articles:
        date_normalized = make_timezone_naive(art.get('date'))

        # Проверяем наличие необходимых полей
        if (date_normalized is not None and
                art.get('reliability_score') is not None and
                art.get('unique_score') is not None):
            art_copy = art.copy()
            art_copy['date'] = date_normalized
            valid_articles.append(art_copy)

    if not valid_articles:
    # Если нет статей с полными данными, пробуем без дат
        for art in articles:
            if art.get('reliability_score') is not None and art.get('unique_score') is not None:
                art_copy = art.copy()
                art_copy['date'] = None
                valid_articles.append(art_copy)

    if not valid_articles:
        return None, "Нет статей с полными данными"

    # Разделяем статьи с датой
    with_date = [a for a in valid_articles if a['date'] is not None]

    # Группировка и поиск самой ранней даты публикации
    if with_date:
        sorted_by_date = sorted(with_date, key=lambda x: x['date'])

        date_groups = {}
        for art in sorted_by_date:
            date_str = art['date'].strftime('%Y-%m-%d')
            date_groups.setdefault(date_str, []).append(art)

        earliest_date = min(date_groups.keys())
        candidates = date_groups[earliest_date]
    else:
        # Если нет статей с датой, берем все
        candidates = valid_articles

    if len(candidates) == 1:
        winner = candidates[0]
        reason = "Самая ранняя публикация"
        return winner, reason

    # Фильтрация по критерию авторитетности (Reliability Score) при совпадении дат
    max_reliability = max(c['reliability_score'] for c in candidates)
    reliability_candidates = [c for c in candidates if c['reliability_score'] == max_reliability]

    if len(reliability_candidates) == 1:
        winner = reliability_candidates[0]
        reason = f"Самая ранняя публикация и наивысший рейтинг ({max_reliability})"
        return winner, reason

    # Фильтрация по максимальной уникальности текста (устранение дубликатов)
    winner = max(reliability_candidates, key=lambda x: x['unique_score'])
    reason = (f"Самая ранняя публикация, наивысший рейтинг ({max_reliability}), "
              f"наибольшая уникальность ({winner['unique_score']:.2f})")

    return winner, reason