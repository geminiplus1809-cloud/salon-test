import sqlite3
from datetime import datetime

def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS services (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      duration_min INTEGER NOT NULL,
      price INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS masters (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS slots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      master_id INTEGER NOT NULL,
      start_ts TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1,
      UNIQUE(master_id, start_ts),
      FOREIGN KEY(master_id) REFERENCES masters(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      user_name TEXT,
      phone TEXT,
      service_id INTEGER NOT NULL,
      master_id INTEGER NOT NULL,
      start_ts TEXT NOT NULL,
      created_ts TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'confirmed',
      UNIQUE(master_id, start_ts),
      FOREIGN KEY(service_id) REFERENCES services(id),
      FOREIGN KEY(master_id) REFERENCES masters(id)
    )
    """)

    conn.commit()

def seed_demo(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM services")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO services(name, duration_min, price) VALUES(?,?,?)",
            [
                ("Маникюр классический", 60, 1500),
                ("Маникюр + покрытие гель-лак", 90, 2300),
                ("Снятие", 30, 500),
                ("Укрепление", 30, 700),
            ],
        )

    cur.execute("SELECT COUNT(*) AS c FROM masters")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO masters(name) VALUES(?)",
            [("Анна",), ("Мария",)],
        )

    conn.commit()

def list_services(conn):
    return conn.execute("SELECT * FROM services ORDER BY id").fetchall()

def list_masters(conn):
    return conn.execute("SELECT * FROM masters ORDER BY id").fetchall()

def list_dates_for_master(conn, master_id: int, limit_days: int = 14):
    rows = conn.execute("""
      SELECT date(start_ts) AS d
      FROM slots
      WHERE master_id=? AND is_active=1 AND datetime(start_ts) >= datetime('now')
      GROUP BY date(start_ts)
      ORDER BY d
      LIMIT ?
    """, (master_id, limit_days)).fetchall()
    return [r["d"] for r in rows]

def list_times_for_master_and_date(conn, master_id: int, date_str: str):
    rows = conn.execute("""
      SELECT s.start_ts
      FROM slots s
      LEFT JOIN appointments a
        ON a.master_id=s.master_id AND a.start_ts=s.start_ts AND a.status='confirmed'
      WHERE s.master_id=? AND date(s.start_ts)=? AND s.is_active=1
        AND datetime(s.start_ts) >= datetime('now')
        AND a.id IS NULL
      ORDER BY s.start_ts
    """, (master_id, date_str)).fetchall()
    return [r["start_ts"] for r in rows]

def create_appointment(conn, user_id: int, user_name: str, phone: str, service_id: int, master_id: int, start_ts: str):
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("""
      INSERT INTO appointments(user_id, user_name, phone, service_id, master_id, start_ts, created_ts, status)
      VALUES(?,?,?,?,?,?,?, 'confirmed')
    """, (user_id, user_name, phone, service_id, master_id, start_ts, now))
    conn.commit()

def list_appointments_by_date(conn, date_str: str):
    return conn.execute("""
      SELECT a.id, a.start_ts, a.user_name, a.phone, s.name AS service, m.name AS master
      FROM appointments a
      JOIN services s ON s.id=a.service_id
      JOIN masters m ON m.id=a.master_id
      WHERE date(a.start_ts)=? AND a.status='confirmed'
      ORDER BY a.start_ts
    """, (date_str,)).fetchall()

def cancel_appointment(conn, appt_id: int):
    conn.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appt_id,))
    conn.commit()
