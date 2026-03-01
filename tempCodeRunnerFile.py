from flask import Flask

app = Flask(__name__)
import sqlite3

def init_db():
    conn = sqlite3.connect("queries.db")
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    # Queries table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query_text TEXT,
        category TEXT,
        priority TEXT,
        status TEXT,
        file_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

init_db()
@app.route("/")
def home():
    return "Backend is working!"

if __name__ == "__main__":
    app.run(debug=True)