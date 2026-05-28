import sqlite3
import pandas as pd

def view_database():
    # Подключаемся к файлу
    conn = sqlite3.connect('data/news.db')

    # Читаем таблицу прямо в красивый формат Pandas
    query = "SELECT * FROM analysis_results"
    df = pd.read_sql_query(query, conn)

    # Закрываем соединение
    conn.close()

    # Выводим данные в консоль
    if df.empty:
        print("База данных пока пуста.")
    else:
        # Настройка, чтобы видеть все колонки
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df.tail(45))  # Покажет последние 10 записей


if __name__ == "__main__":
    view_database()