"""Independent SQLite snapshots and append-only task events in a separate DB."""
import json
from pathlib import Path
import sqlite3
import threading


class RunStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS event_log (run_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,seq))")
        self.connection.commit()

    def save(self, run):
        snapshot = run.export()
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO runs(id,status,snapshot) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,snapshot=excluded.snapshot,updated_at=CURRENT_TIMESTAMP", (run.id, run.status, encoded))
            for i, event in enumerate(snapshot["events"]):
                payload = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                prior = self.connection.execute("SELECT payload FROM event_log WHERE run_id=? AND seq=?", (run.id, i)).fetchone()
                if prior is not None and prior[0] != payload:
                    raise ValueError("immutable task event conflict")
                self.connection.execute("INSERT OR IGNORE INTO event_log VALUES(?,?,?)", (run.id, i, payload))

    def get(self, run_id):
        with self.lock:
            row = self.connection.execute("SELECT snapshot FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit=50):
        with self.lock:
            rows = self.connection.execute("SELECT snapshot FROM runs ORDER BY created_at DESC,rowid DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def close(self):
        with self.lock:
            self.connection.close()
