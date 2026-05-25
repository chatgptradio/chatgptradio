from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CollectorConfig:
    name: str
    interval_s: int
    module: str = ""  # auto-derived as collectors.{name} if empty


@dataclass
class WebSocketConfig:
    port: int = 8765
    fps: int = 4


@dataclass
class SQLiteConfig:
    path: str = "streams/state.db"
    snapshot_retention_days: int = 30
    history_retention_days: int = 90


@dataclass
class VariableEvent:
    name: str
    label: str
    date: str  # "YYYY-MM-DD"


@dataclass
class CalendarConfig:
    variable_events: list[VariableEvent] = field(default_factory=list)


@dataclass
class AppConfig:
    collectors: list[CollectorConfig] = field(default_factory=list)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text())

    collectors = [
        CollectorConfig(
            name=c["name"],
            interval_s=c["interval_s"],
            module=c.get("module", f"collectors.{c['name']}"),
        )
        for c in raw.get("collectors", [])
    ]

    ws_raw = raw.get("websocket", {})
    websocket = WebSocketConfig(
        port=ws_raw.get("port", 8765),
        fps=ws_raw.get("fps", 4),
    )

    db_raw = raw.get("sqlite", {})
    sqlite = SQLiteConfig(
        path=db_raw.get("path", "streams/state.db"),
        snapshot_retention_days=db_raw.get("snapshot_retention_days", 30),
        history_retention_days=db_raw.get("history_retention_days", 90),
    )

    cal_raw = raw.get("calendar", {})
    calendar = CalendarConfig(
        variable_events=[
            VariableEvent(
                name=ve["name"],
                label=ve["label"],
                date=ve["date"],
            )
            for ve in cal_raw.get("variable_events", [])
        ]
    )

    return AppConfig(collectors=collectors, websocket=websocket, sqlite=sqlite, calendar=calendar)
