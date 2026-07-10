import sqlite3
from pathlib import Path
from datetime import datetime

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
"""

class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def now(self): return datetime.now().isoformat(timespec='seconds')
    def employee_count(self): return self.conn.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
    def add_employee(self, name, pin_hash, role='cashier'):
        self.conn.execute('INSERT INTO employees(name,pin_hash,role,created_at) VALUES(?,?,?,?)',(name,pin_hash,role,self.now())); self.conn.commit()
    def employees(self): return self.conn.execute('SELECT * FROM employees ORDER BY name').fetchall()
    def employee_by_id(self, eid): return self.conn.execute('SELECT * FROM employees WHERE id=?',(eid,)).fetchone()
    def employee_by_pin_candidates(self): return self.conn.execute('SELECT * FROM employees WHERE active=1').fetchall()
    def update_employee(self,eid,name,role,active,pin_hash=None):
        if pin_hash:
            self.conn.execute('UPDATE employees SET name=?,role=?,active=?,pin_hash=? WHERE id=?',(name,role,int(active),pin_hash,eid))
        else:
            self.conn.execute('UPDATE employees SET name=?,role=?,active=? WHERE id=?',(name,role,int(active),eid))
        self.conn.commit()
    def delete_employee(self,eid): self.conn.execute('DELETE FROM employees WHERE id=?',(eid,)); self.conn.commit()
    def items(self, active_only=False):
        q='SELECT * FROM items' + (' WHERE active=1' if active_only else '') + ' ORDER BY category,name'
        return self.conn.execute(q).fetchall()
    def item_by_barcode(self,b): return self.conn.execute('SELECT * FROM items WHERE barcode=? AND active=1',(b,)).fetchone()
    def item_by_id(self,i): return self.conn.execute('SELECT * FROM items WHERE id=?',(i,)).fetchone()
    def save_item(self,item_id,name,barcode,price_cents,category,stock_qty,low_stock,active):
        t=self.now(); barcode=barcode.strip() or None
        if item_id:
            self.conn.execute('UPDATE items SET name=?,barcode=?,price_cents=?,category=?,stock_qty=?,low_stock=?,active=?,updated_at=? WHERE id=?',(name,barcode,price_cents,category,stock_qty,low_stock,int(active),t,item_id))
        else:
            self.conn.execute('INSERT INTO items(name,barcode,price_cents,category,stock_qty,low_stock,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(name,barcode,price_cents,category,stock_qty,low_stock,int(active),t,t))
        self.conn.commit()
    def delete_item(self,i): self.conn.execute('DELETE FROM items WHERE id=?',(i,)); self.conn.commit()
    def complete_sale(self,employee_id,lines,total,cash,change):
        cur=self.conn.execute('INSERT INTO sales(employee_id,total_cents,cash_cents,change_cents,created_at) VALUES(?,?,?,?,?)',(employee_id,total,cash,change,self.now()))
        sid=cur.lastrowid
        for line in lines:
            self.conn.execute('INSERT INTO sale_lines(sale_id,item_id,item_name,unit_price_cents,quantity,line_total_cents) VALUES(?,?,?,?,?,?)',(sid,line['id'],line['name'],line['price_cents'],line['qty'],line['price_cents']*line['qty']))
            if line['id']:
                self.conn.execute('UPDATE items SET stock_qty=MAX(0,stock_qty-?) WHERE id=?',(line['qty'],line['id']))
        self.conn.commit(); return sid
    def sales(self,limit=100):
        return self.conn.execute('SELECT sales.*,employees.name employee_name FROM sales JOIN employees ON employees.id=sales.employee_id ORDER BY sales.id DESC LIMIT ?',(limit,)).fetchall()
