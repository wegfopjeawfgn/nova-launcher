"""Remember recent downloads and imports so Nova can show what happened and offer retries."""
from datetime import datetime
import uuid

import motor

STATES = {"running": "En curso", "ok": "Listo", "error": "Con error",
          "cancelled": "Cancelada", "interrupted": "Interrumpida"}


class History:
    def __init__(self, path, limit=20):
        self.path = path
        self.limit = limit
        data = motor.read(path, [])
        self.entries = [entry for entry in data if isinstance(entry, dict) and entry.get("id")]
        for entry in self.entries:
            if entry.get("state") == "running":
                entry["state"] = "interrupted"
                entry["message"] = "Nova se cerró antes de terminar."
        self.entries = self.entries[-limit:]

    def start(self, kind, title):
        entry = {"id": uuid.uuid4().hex, "kind": kind, "title": title, "state": "running",
                 "message": "", "time": datetime.now().isoformat(timespec="seconds")}
        self.entries.append(entry)
        self.entries = self.entries[-self.limit:]
        self._save()
        return entry["id"]

    def finish(self, entry_id, state, message):
        if state not in STATES:
            raise ValueError(state)
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry.update(state=state, message=message[:300])
                self._save()
                return True
        return False

    def recent(self):
        return list(reversed(self.entries))

    def clear_finished(self):
        self.entries = [entry for entry in self.entries if entry["state"] == "running"]
        self._save()

    def _save(self):
        try:
            motor.save(self.path, self.entries)
        except OSError:
            pass  # history is a convenience; never fail a download because of it
