from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_jsonl(path: str | Path, items: list[dict[str, Any]]) -> None:
    with Path(path).open("w") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    items = []
    with Path(path).open() as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def write_json(path: str | Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())
