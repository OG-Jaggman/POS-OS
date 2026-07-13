import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS employees (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 pin_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('manager','cashier')),
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 barcode TEXT UNIQUE,
 price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
 category TEXT NOT NULL DEFAULT 'General',
 stock_qty INTEGER NOT NULL DEFAULT 0,
 low_stock INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
 id INTEGER PRIMARY KEY,
 employee_id INTEGER NOT NULL,
 total_cents INTEGER NOT NULL,
 cash_cents INTEGER NOT NULL,
 change_cents INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 FOREIGN KEY(employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS sale_lines (
 id INTEGER PRIMARY KEY,
 sale_id INTEGER NOT NULL,
 item_id INTEGER,
 item_name TEXT NOT NULL,
 unit_price_cents INTEGER NOT NULL,
 quantity INTEGER NOT NULL,
 line_total_cents INTEGER NOT NULL,
 FOREIGN KEY(sale_id) REFERENCES sales(id)
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS printers (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 printer_type TEXT NOT NULL CHECK(printer_type IN ('network','system','cups','windows','file')),
 host TEXT NOT NULL DEFAULT '',
 port INTEGER NOT NULL DEFAULT 9100,
 queue_name TEXT NOT NULL DEFAULT '',
 file_path TEXT NOT NULL DEFAULT '',
 paper_width_mm INTEGER NOT NULL DEFAULT 80 CHECK(paper_width_mm IN (58,80)),
 auto_cut INTEGER NOT NULL DEFAULT 1,
 drawer_enabled INTEGER NOT NULL DEFAULT 1,
 drawer_pin INTEGER NOT NULL DEFAULT 0,
 drawer_on_ms INTEGER NOT NULL DEFAULT 120,
 drawer_off_ms INTEGER NOT NULL DEFAULT 240,
 is_default INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate_printers()
        self.conn.commit()

    def _migrate_printers(self):
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(printers)")}
        additions = {
            "drawer_enabled": "INTEGER NOT NULL DEFAULT 1",
            "drawer_pin": "INTEGER NOT NULL DEFAULT 0",
            "drawer_on_ms": "INTEGER NOT NULL DEFAULT 120",
            "drawer_off_ms": "INTEGER NOT NULL DEFAULT 240",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE printers ADD COLUMN {name} {definition}")

    def now(self):
        return datetime.now().isoformat(timespec="seconds")

    def employee_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]

    def add_employee(self, name, pin_hash, role="cashier"):
        self.conn.execute(
            "INSERT INTO employees(name,pin_hash,role,created_at) VALUES(?,?,?,?)",
            (name, pin_hash, role, self.now()),
        )
        self.conn.commit()

    def employees(self):
        return self.conn.execute("SELECT * FROM employees ORDER BY name").fetchall()

    def employee_by_id(self, eid):
        return self.conn.execute("SELECT * FROM employees WHERE id=?", (eid,)).fetchone()

    def employee_by_pin_candidates(self):
        return self.conn.execute("SELECT * FROM employees WHERE active=1").fetchall()

    def update_employee(self, eid, name, role, active, pin_hash=None):
        if pin_hash:
            self.conn.execute(
                "UPDATE employees SET name=?,role=?,active=?,pin_hash=? WHERE id=?",
                (name, role, int(active), pin_hash, eid),
            )
        else:
            self.conn.execute(
                "UPDATE employees SET name=?,role=?,active=? WHERE id=?",
                (name, role, int(active), eid),
            )
        self.conn.commit()

    def delete_employee(self, eid):
        self.conn.execute("DELETE FROM employees WHERE id=?", (eid,))
        self.conn.commit()

    def items(self, active_only=False):
        query = "SELECT * FROM items" + (" WHERE active=1" if active_only else "") + " ORDER BY category,name"
        return self.conn.execute(query).fetchall()

    def item_by_barcode(self, barcode):
        return self.conn.execute(
            "SELECT * FROM items WHERE barcode=? AND active=1", (barcode,)
        ).fetchone()

    def item_by_id(self, item_id):
        return self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()

    def save_item(self, item_id, name, barcode, price_cents, category, stock_qty, low_stock, active):
        timestamp = self.now()
        barcode = barcode.strip() or None
        if item_id:
            self.conn.execute(
                "UPDATE items SET name=?,barcode=?,price_cents=?,category=?,stock_qty=?,low_stock=?,active=?,updated_at=? WHERE id=?",
                (name, barcode, price_cents, category, stock_qty, low_stock, int(active), timestamp, item_id),
            )
        else:
            self.conn.execute(
                "INSERT INTO items(name,barcode,price_cents,category,stock_qty,low_stock,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (name, barcode, price_cents, category, stock_qty, low_stock, int(active), timestamp, timestamp),
            )
        self.conn.commit()

    def delete_item(self, item_id):
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()

    def complete_sale(self, employee_id, lines, total, cash, change):
        created = self.now()
        cursor = self.conn.execute(
            "INSERT INTO sales(employee_id,total_cents,cash_cents,change_cents,created_at) VALUES(?,?,?,?,?)",
            (employee_id, total, cash, change, created),
        )
        sale_id = cursor.lastrowid
        for line in lines:
            self.conn.execute(
                "INSERT INTO sale_lines(sale_id,item_id,item_name,unit_price_cents,quantity,line_total_cents) VALUES(?,?,?,?,?,?)",
                (sale_id, line["id"], line["name"], line["price_cents"], line["qty"], line["price_cents"] * line["qty"]),
            )
            if line["id"]:
                self.conn.execute(
                    "UPDATE items SET stock_qty=MAX(0,stock_qty-?) WHERE id=?",
                    (line["qty"], line["id"]),
                )
        self.conn.commit()
        return sale_id, created

    def sales(self, limit=100):
        return self.conn.execute(
            "SELECT sales.*,employees.name employee_name FROM sales JOIN employees ON employees.id=sales.employee_id ORDER BY sales.id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def sale_lines(self, sale_id):
        return self.conn.execute(
            "SELECT * FROM sale_lines WHERE sale_id=? ORDER BY id", (sale_id,)
        ).fetchall()

    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def set_setting(self, key, value):
        data = json.dumps(value)
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, data),
        )
        self.conn.commit()

    def printers(self, active_only=False):
        query = "SELECT * FROM printers" + (" WHERE active=1" if active_only else "") + " ORDER BY is_default DESC,name"
        return self.conn.execute(query).fetchall()

    def printer_by_id(self, printer_id):
        return self.conn.execute("SELECT * FROM printers WHERE id=?", (printer_id,)).fetchone()

    def default_printer(self):
        return self.conn.execute(
            "SELECT * FROM printers WHERE active=1 ORDER BY is_default DESC,id LIMIT 1"
        ).fetchone()

    def save_printer(
        self,
        printer_id,
        name,
        printer_type,
        host,
        port,
        queue_name,
        file_path,
        paper_width_mm,
        auto_cut,
        drawer_enabled,
        drawer_pin,
        drawer_on_ms,
        drawer_off_ms,
        is_default,
        active,
    ):
        timestamp = self.now()
        if is_default:
            self.conn.execute("UPDATE printers SET is_default=0")
        values = (
            name,
            printer_type,
            host,
            int(port),
            queue_name,
            file_path,
            int(paper_width_mm),
            int(auto_cut),
            int(drawer_enabled),
            int(drawer_pin),
            int(drawer_on_ms),
            int(drawer_off_ms),
            int(is_default),
            int(active),
            timestamp,
        )
        if printer_id:
            self.conn.execute(
                "UPDATE printers SET name=?,printer_type=?,host=?,port=?,queue_name=?,file_path=?,paper_width_mm=?,auto_cut=?,drawer_enabled=?,drawer_pin=?,drawer_on_ms=?,drawer_off_ms=?,is_default=?,active=?,updated_at=? WHERE id=?",
                values + (printer_id,),
            )
        else:
            self.conn.execute(
                "INSERT INTO printers(name,printer_type,host,port,queue_name,file_path,paper_width_mm,auto_cut,drawer_enabled,drawer_pin,drawer_on_ms,drawer_off_ms,is_default,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values + (timestamp,),
            )
        self.conn.commit()

    def delete_printer(self, printer_id):
        self.conn.execute("DELETE FROM printers WHERE id=?", (printer_id,))
        self.conn.commit()
