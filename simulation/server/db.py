"""Реестр морских дронов (SQLite) и подпись ответа (HMAC)."""
import hashlib
import hmac
import sqlite3
from typing import Dict, List, Optional

# Демо-данные. Ключи - демонстрационные, в реальной системе выдаются при регистрации аппарата.
SEED = [
    ("MD-0427", "НИЦ «Морские системы» (демо)", "Инспекция кабеля, зона B", 1, "key-0427"),
    ("MD-0311", "Порт-оператор (демо)", "Обследование дна", 1, "key-0311"),
    ("MD-0588", "Университет (демо)", "Мониторинг воды (допуск истёк)", 0, "key-0588"),
]


def make_mac(key: str, drone_id: str, counter: int) -> str:
    """4 байта (8 hex) подписи: HMAC-SHA256(key, 'ID:счётчик')."""
    return hmac.new(key.encode(), f"{drone_id}:{counter}".encode(), hashlib.sha256).hexdigest()[:8]


class Registry:
    def __init__(self, path: str):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS drones("
            "id TEXT PRIMARY KEY, owner TEXT, mission TEXT, allowed INTEGER, key TEXT)")
        if not self.con.execute("SELECT 1 FROM drones LIMIT 1").fetchone():
            self.con.executemany("INSERT INTO drones VALUES (?,?,?,?,?)", SEED)
            self.con.commit()

    def get(self, drone_id: Optional[str]) -> Optional[Dict]:
        if not drone_id:
            return None
        r = self.con.execute(
            "SELECT id, owner, mission, allowed, key FROM drones WHERE id=?", (drone_id,)).fetchone()
        return dict(zip(("id", "owner", "mission", "allowed", "key"), r)) if r else None

    def all(self) -> List[Dict]:
        rows = self.con.execute("SELECT id, owner, mission, allowed FROM drones ORDER BY id").fetchall()
        return [dict(zip(("id", "owner", "mission", "allowed"), r)) for r in rows]

    def upsert(self, drone_id: str, owner: str, mission: str, allowed: bool, key: Optional[str] = None):
        old = self.get(drone_id)
        key = key or (old["key"] if old else f"key-{drone_id}")
        self.con.execute("INSERT OR REPLACE INTO drones VALUES (?,?,?,?,?)",
                         (drone_id, owner, mission, 1 if allowed else 0, key))
        self.con.commit()
