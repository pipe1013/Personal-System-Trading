# init_db.py
import sqlite3
from config import DB_PATH

connection = sqlite3.connect(DB_PATH)
cursor = connection.cursor()

# Crea la tabla trades con todas las columnas necesarias
cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        notebook_id INTEGER,
        asset TEXT NOT NULL,
        account_balance REAL,
        account_type TEXT CHECK(account_type IN ('Demo', 'Real')),
        lot_size REAL NOT NULL,
        entry_point REAL NOT NULL,
        stop_loss REAL,
        take_profit REAL,
        result TEXT CHECK(result IN ('Ganadora', 'Perdedora')),
        trade_date DATE,
        emotion TEXT CHECK(emotion IN ('Confianza', 'Ansiedad', 'Optimismo', 'Miedo', 'Euforia', 'Irritación', 'Calma')),
        activation_routine BOOLEAN,
        entry_image_path TEXT,
        FOREIGN KEY (notebook_id) REFERENCES notebooks(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')

# Crea la tabla users
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )
''')

# Crea la tabla notebooks
cursor.execute('''
    CREATE TABLE IF NOT EXISTS notebooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        initial_balance REAL,
        account_type TEXT CHECK(account_type IN ('Demo', 'Real')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')

connection.commit()
connection.close()
print("Tablas creadas exitosamente.")
