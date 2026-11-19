import networkx as nx
from pyvis.network import Network
import os
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime


def get_cosine_similarity(text1, text2):
    """Считает косинусное сходство двух текстов по TF-IDF (от 0.0 до 1.0)."""
    if not text1 or not text2 or len(text1) < 50 or len(text2) < 50:
        return 0.0
    try:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        tfidf = vectorizer.fit_transform([text1, text2])
        return float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
    except Exception:
        return 0.0


def build_propagation_graph(articles, winner=None, similarity_threshold=0.22):
    """
    Строит профессиональный кластерный граф OSINT:
    1. Группирует статьи по реальным сюжетам (кластерам) через TF-IDF.
    2. Выделяет первоисточник ДЛЯ КАЖДОГО СЮЖЕТА отдельно.
    3. Исключает ложные связи между разрозненными новостями.
    """
    G = nx.DiGraph()

    if not articles:
        return ""

    n = len(articles)

    # --- 1. КЛАСТЕРИЗАЦИЯ СТАТЕЙ ПО СЮЖЕТАМ ---
    # Создаем матрицу смежности для связей по смысловому сходству
    adj_matrix = [[False] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            art1 = articles[i]
            art2 = articles[j]

            # 1. Прямое сходство текстов
            sim = get_cosine_similarity(art1.get('text', ''), art2.get('text', ''))

            # 2. Пересечение ключевых слов в заголовке
            words1 = set(re.findall(r'[а-яа-ёa-z0-9]{4,}', art1['title'].lower()))
            words2 = set(re.findall(r'[а-яа-ёa-z0-9]{4,}', art2['title'].lower()))
            common_words = words1.intersection(words2)

            # Бонус, если ключевые слова заголовка совпадают (например, "пенсионерка", "54", "тысяч")
            if len(common_words) >= 2:
                sim += 0.25

            if sim >= similarity_threshold:
                adj_matrix[i][j] = True
                adj_matrix[j][i] = True

    # --- 2. ВЫДЕЛЕНИЕ КОМПОНЕНТ СВЯЗНОСТИ (СЮЖЕТОВ) ---
    visited = [False] * n
    clusters = []

    for i in range(n):
        if not visited[i]:
            cluster = []
            queue = [i]
            visited[i] = True

            while queue:
                curr = queue.pop(0)
                cluster.append(articles[curr])
                for neighbor in range(n):
                    if adj_matrix[curr][neighbor] and not visited[neighbor]:
                        visited[neighbor] = True
                        queue.append(neighbor)

            clusters.append(cluster)

    # --- 3. ПОСТРОЕНИЕ ГРАФА ПО КЛАСТЕРАМ ---
    for cluster_idx, cluster in enumerate(clusters):
        # Находим первоисточник ВНУТРИ данного конкретного кластера (самая ранняя дата)
        sorted_cluster = sorted(
            cluster,
            key=lambda x: (x.get('date') if x.get('date') else datetime.max)
        )
        cluster_winner = sorted_cluster[0]

        # Добавляем узлы кластера
        for art in cluster:
            url = art['url']
            domain = art['domain']
            is_cluster_winner = (url == cluster_winner['url'])
            date_str = art['date'].strftime('%d.%m.%Y %H:%M') if art.get('date') else 'неизвестна'

            if is_cluster_winner and len(cluster) > 1:
                node_color = "#FF4B4B"  # Красный для первоисточника сюжета
                label = f"⭐ ПЕРВОИСТОЧНИК СЮЖЕТА\n{domain}"
                shape = "box"
                size = 28
            elif is_cluster_winner and len(cluster) == 1:
                node_color = "#FFA500"  # Оранжевый для одиночной уникальной новости
                label = f"📌 Одиночная новость\n{domain}"
                shape = "ellipse"
                size = 20
            else:
                node_color = "#0068C9"  # Синий для перепечаток
                label = domain
                shape = "dot"
                size = 18

            G.add_node(
                url,
                label=label,
                title=f"Сюжет №{cluster_idx + 1}\nДомен: {domain}\nЗаголовок: {art['title']}\nДата: {date_str}",
                color=node_color,
                shape=shape,
                size=size
            )

        # Соединяем рерайтеры со своим локальным первоисточником
        if len(cluster) > 1:
            for art in cluster:
                if art['url'] == cluster_winner['url']:
                    continue

                # Расчет прямого сходства с первоисточником сюжета
                direct_sim = get_cosine_similarity(cluster_winner.get('text', ''), art.get('text', ''))
                sim_percent = int(min(direct_sim * 100 + 35, 95))  # Нормализация %

                # Расчет задержки во времени
                time_delay = "одновременно"
                if cluster_winner.get('date') and art.get('date'):
                    diff_sec = (art['date'] - cluster_winner['date']).total_seconds()
                    if diff_sec > 0:
                        hours = int(diff_sec // 3600)
                        minutes = int((diff_sec % 3600) // 60)
                        time_delay = f"+{hours}ч {minutes}мин" if hours > 0 else f"+{minutes}мин"

                G.add_edge(
                    cluster_winner['url'],
                    art['url'],
                    title=f"Задержка: {time_delay} | Сходство: {sim_percent}%",
                    label=f"{time_delay} ({sim_percent}%)",
                    color="#808080"
                )

    # --- 4. СОХРАНЕНИЕ HTML С НАСТРОЙКОЙ ФИЗИКИ ---
    net = Network(height="530px", width="100%", directed=True, notebook=False)
    net.from_nx(G)

    net.set_options("""
    var options = {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -4000,
          "centralGravity": 0.2,
          "springLength": 150
        }
      }
    }
    """)

    os.makedirs("data", exist_ok=True)
    html_path = os.path.join("data", "propagation_graph.html")
    net.save_graph(html_path)

    return html_path