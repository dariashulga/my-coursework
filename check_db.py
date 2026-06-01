import sqlite3
import pandas as pd

def view_database():
    """Выполняет прямое чтение и табличное форматирование исторических логов из СУБД."""
    conn = sqlite3.connect('data/news.db')

    query = "SELECT * FROM analysis_results"
    df = pd.read_sql_query(query, conn)

    conn.close()

    # Выводим данные в консоль
    if df.empty:
        print("База данных пока пуста.")
    else:
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df.tail(45))


if __name__ == "__main__":
    view_database()