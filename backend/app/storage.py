from threading import RLock
import json
import sqlite3

class Store:
    def __init__(self,path):
        self.lock=RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.commit()
    def get(self,key,default):
        with self.lock:
            row=self.db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else default
    def put(self,key,value):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value)))
            self.db.commit()
    def clear(self):
        with self.lock:
            self.db.execute('DELETE FROM kv')
            self.db.commit()
