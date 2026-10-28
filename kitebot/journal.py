"""Append-only trade journal (JSON lines). The raw material for the learning loop."""

import json
from datetime import datetime
from pathlib import Path

from .strategies import RULES_VERSION


class Journal:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self.entries: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, day: str, **fields) -> None:
        entry = {"event": event, "day": day, "rules": RULES_VERSION, "logged_at": datetime.now().isoformat(timespec="seconds"), **fields}
        self.entries.append(entry)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")

    @staticmethod
    def read(path: str | Path) -> list[dict]:
        path = Path(path)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
