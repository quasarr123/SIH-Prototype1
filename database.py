import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "apix_db")

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "apix.db")

_DB_ENGINE = None  # 'mariadb' or 'sqlite'

# Initial DGCA Seed Routes (Top 10 Indian Domestic Corridors)
DEFAULT_ROUTES = [
    ('DEL-BOM', 'DEL', 'BOM', 'Delhi', 'Mumbai', 0.1850, 4850.00),
    ('DEL-BLR', 'DEL', 'BLR', 'Delhi', 'Bengaluru', 0.1420, 5400.00),
    ('BOM-BLR', 'BOM', 'BLR', 'Mumbai', 'Bengaluru', 0.1100, 3950.00),
    ('DEL-CCU', 'DEL', 'CCU', 'Delhi', 'Kolkata', 0.0950, 4900.00),
    ('BLR-HYD', 'BLR', 'HYD', 'Bengaluru', 'Hyderabad', 0.0880, 2800.00),
    ('MAA-DEL', 'MAA', 'DEL', 'Chennai', 'Delhi', 0.0820, 5200.00),
    ('BOM-GOI', 'BOM', 'GOI', 'Mumbai', 'Goa', 0.0780, 3200.00),
    ('DEL-HYD', 'DEL', 'HYD', 'Delhi', 'Hyderabad', 0.0750, 4300.00),
    ('DEL-PNQ', 'DEL', 'PNQ', 'Delhi', 'Pune', 0.0730, 4600.00),
    ('BOM-MAA', 'BOM', 'MAA', 'Mumbai', 'Chennai', 0.0720, 3850.00)
]

def get_connection():
    """
    Attempts to connect to MariaDB. If unavailable or authentication fails,
    transparently falls back to local SQLite so the application never crashes.
    """
    global _DB_ENGINE
    if _DB_ENGINE != 'sqlite':
        try:
            import pymysql
            # Connect to server to ensure database exists
            server_conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=3
            )
            with server_conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4;")
            server_conn.commit()
            server_conn.close()

            # Connect to specific database
            conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                cursorclass=pymysql.cursors.DictCursor
            )
            _DB_ENGINE = 'mariadb'
            return conn, 'mariadb'
        except Exception as e:
            if _DB_ENGINE is None:
                print(f"[Database] MariaDB notice: {e}")
                print(f"[Database] Using SQLite fallback: {SQLITE_PATH}")
            _DB_ENGINE = 'sqlite'

    # SQLite Fallback
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn, 'sqlite'

def init_db():
    """Initializes tables and seeds DGCA route weights."""
    conn, engine = get_connection()
    if engine == 'mariadb':
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                route_id INT AUTO_INCREMENT PRIMARY KEY,
                route_code VARCHAR(20) NOT NULL UNIQUE,
                origin VARCHAR(10) NOT NULL,
                destination VARCHAR(10) NOT NULL,
                origin_city VARCHAR(50) NOT NULL,
                dest_city VARCHAR(50) NOT NULL,
                dgca_weight DECIMAL(6, 4) NOT NULL,
                base_price_p0 DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS airfare_quotes (
                quote_id INT AUTO_INCREMENT PRIMARY KEY,
                route_code VARCHAR(20) NOT NULL,
                carrier VARCHAR(50) NOT NULL,
                flight_number VARCHAR(20) NOT NULL,
                departure_time VARCHAR(20),
                arrival_time VARCHAR(20),
                advance_days INT NOT NULL,
                departure_date DATE NOT NULL,
                base_fare DECIMAL(10, 2) NOT NULL,
                taxes_fees DECIMAL(10, 2) NOT NULL,
                udf_charges DECIMAL(10, 2) DEFAULT 0.00,
                total_fare DECIMAL(10, 2) NOT NULL,
                source_portal VARCHAR(50) DEFAULT 'Direct',
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_route (route_code),
                INDEX idx_adv (advance_days)
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS apix_history (
                index_id INT AUTO_INCREMENT PRIMARY KEY,
                calc_date DATE NOT NULL,
                headline_apix DECIMAL(8, 2) NOT NULL,
                apix_t1 DECIMAL(8, 2),
                apix_t7 DECIMAL(8, 2),
                apix_t15 DECIMAL(8, 2),
                apix_t30 DECIMAL(8, 2),
                apix_t45 DECIMAL(8, 2),
                sample_size INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            for r in DEFAULT_ROUTES:
                cur.execute("""
                INSERT INTO routes (route_code, origin, destination, origin_city, dest_city, dgca_weight, base_price_p0)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE dgca_weight=VALUES(dgca_weight), base_price_p0=VALUES(base_price_p0);
                """, r)
        conn.commit()
        conn.close()
    else:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            route_id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_code TEXT UNIQUE NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            origin_city TEXT NOT NULL,
            dest_city TEXT NOT NULL,
            dgca_weight REAL NOT NULL,
            base_price_p0 REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS airfare_quotes (
            quote_id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_code TEXT NOT NULL,
            carrier TEXT NOT NULL,
            flight_number TEXT NOT NULL,
            departure_time TEXT,
            arrival_time TEXT,
            advance_days INTEGER NOT NULL,
            departure_date TEXT NOT NULL,
            base_fare REAL NOT NULL,
            taxes_fees REAL NOT NULL,
            udf_charges REAL DEFAULT 0.00,
            total_fare REAL NOT NULL,
            source_portal TEXT DEFAULT 'Direct',
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS apix_history (
            index_id INTEGER PRIMARY KEY AUTOINCREMENT,
            calc_date TEXT NOT NULL,
            headline_apix REAL NOT NULL,
            apix_t1 REAL,
            apix_t7 REAL,
            apix_t15 REAL,
            apix_t30 REAL,
            apix_t45 REAL,
            sample_size INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        for r in DEFAULT_ROUTES:
            cur.execute("""
            INSERT OR REPLACE INTO routes (route_code, origin, destination, origin_city, dest_city, dgca_weight, base_price_p0)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, r)
        conn.commit()
        conn.close()

def get_routes():
    """Returns list of configured DGCA routes."""
    conn, engine = get_connection()
    if engine == 'mariadb':
        with conn.cursor() as cur:
            cur.execute("SELECT route_code, origin, destination, origin_city, dest_city, dgca_weight, base_price_p0 FROM routes ORDER BY dgca_weight DESC")
            routes = cur.fetchall()
        conn.close()
        return routes
    else:
        cur = conn.cursor()
        cur.execute("SELECT route_code, origin, destination, origin_city, dest_city, dgca_weight, base_price_p0 FROM routes ORDER BY dgca_weight DESC")
        routes = [dict(row) for row in cur.fetchall()]
        conn.close()
        return routes

def insert_quotes(quotes_list):
    """Inserts a list of quote dictionaries into airfare_quotes."""
    if not quotes_list:
        return 0
    conn, engine = get_connection()
    inserted = 0
    if engine == 'mariadb':
        with conn.cursor() as cur:
            sql = """
            INSERT INTO airfare_quotes (route_code, carrier, flight_number, departure_time, arrival_time,
                                        advance_days, departure_date, base_fare, taxes_fees, udf_charges,
                                        total_fare, source_portal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            for q in quotes_list:
                cur.execute(sql, (
                    q['route_code'], q['carrier'], q['flight_number'], q.get('departure_time', '08:00'),
                    q.get('arrival_time', '10:15'), q['advance_days'], str(q['departure_date']),
                    q['base_fare'], q['taxes_fees'], q.get('udf_charges', 0.0),
                    q['total_fare'], q.get('source_portal', 'Direct')
                ))
                inserted += 1
        conn.commit()
        conn.close()
    else:
        cur = conn.cursor()
        sql = """
        INSERT INTO airfare_quotes (route_code, carrier, flight_number, departure_time, arrival_time,
                                    advance_days, departure_date, base_fare, taxes_fees, udf_charges,
                                    total_fare, source_portal)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for q in quotes_list:
            cur.execute(sql, (
                q['route_code'], q['carrier'], q['flight_number'], q.get('departure_time', '08:00'),
                q.get('arrival_time', '10:15'), q['advance_days'], str(q['departure_date']),
                q['base_fare'], q['taxes_fees'], q.get('udf_charges', 0.0),
                q['total_fare'], q.get('source_portal', 'Direct')
            ))
            inserted += 1
        conn.commit()
        conn.close()
    return inserted

def get_latest_quotes(limit=50, route_code=None):
    """Fetches recent airfare quotes."""
    conn, engine = get_connection()
    if engine == 'mariadb':
        with conn.cursor() as cur:
            if route_code:
                cur.execute("""
                SELECT quote_id, route_code, carrier, flight_number, departure_time, arrival_time,
                       advance_days, departure_date, base_fare, taxes_fees, udf_charges, total_fare,
                       source_portal, scraped_at
                FROM airfare_quotes WHERE route_code = %s ORDER BY quote_id DESC LIMIT %s
                """, (route_code, limit))
            else:
                cur.execute("""
                SELECT quote_id, route_code, carrier, flight_number, departure_time, arrival_time,
                       advance_days, departure_date, base_fare, taxes_fees, udf_charges, total_fare,
                       source_portal, scraped_at
                FROM airfare_quotes ORDER BY quote_id DESC LIMIT %s
                """, (limit,))
            quotes = cur.fetchall()
        conn.close()
        return quotes
    else:
        cur = conn.cursor()
        if route_code:
            cur.execute("""
            SELECT quote_id, route_code, carrier, flight_number, departure_time, arrival_time,
                   advance_days, departure_date, base_fare, taxes_fees, udf_charges, total_fare,
                   source_portal, scraped_at
            FROM airfare_quotes WHERE route_code = ? ORDER BY quote_id DESC LIMIT ?
            """, (route_code, limit))
        else:
            cur.execute("""
            SELECT quote_id, route_code, carrier, flight_number, departure_time, arrival_time,
                   advance_days, departure_date, base_fare, taxes_fees, udf_charges, total_fare,
                   source_portal, scraped_at
            FROM airfare_quotes ORDER BY quote_id DESC LIMIT ?
            """, (limit,))
        quotes = [dict(row) for row in cur.fetchall()]
        conn.close()
        return quotes

def save_index_record(calc_date, headline, t1, t7, t15, t30, t45, sample_size):
    """Saves a computed APIx index record."""
    conn, engine = get_connection()
    if engine == 'mariadb':
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO apix_history (calc_date, headline_apix, apix_t1, apix_t7, apix_t15, apix_t30, apix_t45, sample_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (calc_date, headline, t1, t7, t15, t30, t45, sample_size))
        conn.commit()
        conn.close()
    else:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO apix_history (calc_date, headline_apix, apix_t1, apix_t7, apix_t15, apix_t30, apix_t45, sample_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (calc_date, headline, t1, t7, t15, t30, t45, sample_size))
        conn.commit()
        conn.close()

def get_index_history(limit=30):
    """Retrieves index calculation history for charting."""
    conn, engine = get_connection()
    if engine == 'mariadb':
        with conn.cursor() as cur:
            cur.execute("""
            SELECT calc_date, headline_apix, apix_t1, apix_t7, apix_t15, apix_t30, apix_t45, sample_size
            FROM apix_history ORDER BY index_id DESC LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
        conn.close()
        return list(reversed(rows))
    else:
        cur = conn.cursor()
        cur.execute("""
        SELECT calc_date, headline_apix, apix_t1, apix_t7, apix_t15, apix_t30, apix_t45, sample_size
        FROM apix_history ORDER BY index_id DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return list(reversed(rows))
