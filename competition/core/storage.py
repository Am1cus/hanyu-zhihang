"""Independent SQLite snapshots, task events, and execution provenance."""
from datetime import datetime, timezone
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
        self.connection.execute("CREATE TABLE IF NOT EXISTS execution_audit (run_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,seq))")
        self.connection.execute("CREATE TABLE IF NOT EXISTS creation_requests (request_key TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, run_id TEXT NOT NULL)")
        self.connection.commit()

    def save(self, run, audit_actions=None, creation_request=None):
        # Execution actions belong to API provenance, not the deterministic
        # simulator export or its result_sha256.
        snapshot = run.export()
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        with self.lock, self.connection:
            # Persist request identity and its run in the SAME transaction.
            # A lost HTTP response can then be retried after process restart.
            if creation_request is not None:
                key, request_sha256 = creation_request
                self.connection.execute("INSERT INTO creation_requests VALUES(?,?,?)", (key, request_sha256, run.id))
            self.connection.execute("INSERT INTO runs(id,status,snapshot) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,snapshot=excluded.snapshot,updated_at=CURRENT_TIMESTAMP", (run.id, run.status, encoded))
            for i, event in enumerate(snapshot["events"]):
                payload = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                prior = self.connection.execute("SELECT payload FROM event_log WHERE run_id=? AND seq=?", (run.id, i)).fetchone()
                if prior is not None and prior[0] != payload:
                    raise ValueError("immutable task event conflict")
                self.connection.execute("INSERT OR IGNORE INTO event_log VALUES(?,?,?)", (run.id, i, payload))
            for action in audit_actions or []:
                row = self.connection.execute("SELECT COALESCE(MAX(seq),0) FROM execution_audit WHERE run_id=?", (run.id,)).fetchone()
                seq = row[0] + 1
                payload = {**action, "seq": seq,
                           "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
                self.connection.execute("INSERT INTO execution_audit VALUES(?,?,?)",
                                        (run.id, seq, json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))))

    def creation_request(self, key):
        with self.lock:
            return self.connection.execute("SELECT request_sha256,run_id FROM creation_requests WHERE request_key=?", (key,)).fetchone()

    def execution_audit(self, run_id):
        with self.lock:
            rows = self.connection.execute("SELECT payload FROM execution_audit WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        records = [json.loads(row[0]) for row in rows]
        replay = next((record for record in records if record["action"] == "replay_origin"), None)
        created = any(record["action"] == "create" for record in records)
        origin = {"status": "replay" if replay else "original" if created else "unknown",
                  "source_run_id": replay["source_run_id"] if replay else None}
        return {"schema_version": 1, "status": "recorded" if records else "unknown",
                "origin": origin, "records": records}

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
