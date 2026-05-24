"""CommandEngine — lightweight chat command dispatcher.

Manages cooldowns for chat commands and exposes a push()
method to inject commands into the DSP/playback pipeline.
"""

from __future__ import annotations

import time


VALID_GENRES: tuple[str, ...] = (
    "ambient",
    "electronic",
    "jazz",
    "industrial",
    "neoclassical",
    "experimental",
    "drone",
)

_REQUEST_COOLDOWN_S: float = 60.0
_SWITCH_COOLDOWN_S: float = 300.0
_REPLAY_COOLDOWN_S: float = 120.0
_MOOD_COOLDOWN_S: float = 30.0


class CommandEngine:
    """Tracks cooldowns and routes commands to downstream consumers."""

    def __init__(self) -> None:
        self._request_last: dict[str, float] = {}
        self._switch_last: float = 0.0
        self._replay_last: float = 0.0
        self._mood_last: float = 0.0
        self._pending: list[tuple[str, str]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def push(self, kind: str, value: str) -> None:
        """Enqueue a command for the DSP/playback pipeline."""
        self._pending.append((kind, value))

    def pop_all(self) -> list[tuple[str, str]]:
        """Drain and return all pending commands."""
        out, self._pending = self._pending, []
        return out

    # ── Cooldown helpers ──────────────────────────────────────────────────────

    def try_request(self, genre: str) -> bool:
        now = time.monotonic()
        if now - self._request_last.get(genre, 0.0) >= _REQUEST_COOLDOWN_S:
            self._request_last[genre] = now
            return True
        return False

    def try_switch(self) -> bool:
        now = time.monotonic()
        if now - self._switch_last >= _SWITCH_COOLDOWN_S:
            self._switch_last = now
            return True
        return False

    def try_replay(self) -> bool:
        now = time.monotonic()
        if now - self._replay_last >= _REPLAY_COOLDOWN_S:
            self._replay_last = now
            return True
        return False

    def try_mood(self) -> bool:
        now = time.monotonic()
        if now - self._mood_last >= _MOOD_COOLDOWN_S:
            self._mood_last = now
            return True
        return False

    def cooldown_remaining(self, kind: str, arg: str = "") -> float:
        """Return seconds remaining before *kind* can be used again."""
        now = time.monotonic()
        if kind == "request":
            return max(0.0, _REQUEST_COOLDOWN_S - (now - self._request_last.get(arg, 0.0)))
        if kind == "switch":
            return max(0.0, _SWITCH_COOLDOWN_S - (now - self._switch_last))
        if kind == "replay":
            return max(0.0, _REPLAY_COOLDOWN_S - (now - self._replay_last))
        if kind == "mood":
            return max(0.0, _MOOD_COOLDOWN_S - (now - self._mood_last))
        return 0.0
