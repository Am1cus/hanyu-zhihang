"""Independent SQLite snapshots, task events, and execution provenance."""
from datetime import datetime, timezone
import base64
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
        self.save_batch([(run, audit_actions, creation_request)])

    def save_batch(self, entries):
        """Commit snapshots, audit actions and request identities together."""
        with self.lock, self.connection:
            for run, audit_actions, creation_request in entries:
                self._save(run, audit_actions, creation_request)

    def _save(self, run, audit_actions, creation_request):
        # Execution actions are separate from the deterministic export.
        snapshot = run.export()
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
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

    def history(self, limit=50, cursor=None):
        """Page lightweight summaries within the first page's rowid boundary.

        The cursor is a position, not an authorization token. No snapshots or
        telemetry are decoded just to build a history list. Keep ``list`` for
        legacy callers that explicitly need whole archives.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid_history_limit')
        position = None
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or not 1 <= len(cursor) <= 512:
                    raise ValueError()
                raw = base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True)
                position = json.loads(raw)
                if (not isinstance(position, list) or len(position) != 4 or type(position[0]) is not int
                        or position[0] != 1 or type(position[1]) is not int or type(position[3]) is not int
                        or not 0 < position[3] <= position[1] <= 9223372036854775807
                        or not isinstance(position[2], str) or not 1 <= len(position[2]) <= 64):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError) as exc:
                raise ValueError('invalid_history_cursor') from exc
        with self.lock:
            ceiling = position[1] if position else self.connection.execute(
                'SELECT COALESCE(MAX(rowid),0) FROM runs').fetchone()[0]
            query = """SELECT id,created_at,rowid,json_extract(snapshot,'$.summary'),
                       json_extract(snapshot,'$.configuration') FROM runs WHERE rowid<=?"""
            parameters = [ceiling]
            if position:
                query += ' AND (created_at<? OR (created_at=? AND rowid<?))'
                parameters += [position[2], position[2], position[3]]
            query += ' ORDER BY created_at DESC,rowid DESC LIMIT ?'
            rows = self.connection.execute(query, [*parameters, limit + 1]).fetchall()
        items = [{'id':row[0], 'summary':json.loads(row[3]), 'configuration':json.loads(row[4])}
                 for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            payload = json.dumps([1, ceiling, last[1], last[2]], separators=(',', ':')).encode()
            next_cursor = base64.urlsafe_b64encode(payload).decode().rstrip('=')
        return {'items':items, 'next_cursor':next_cursor}

    def close(self):
        with self.lock:
            self.connection.close()
