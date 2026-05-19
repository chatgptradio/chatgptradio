"""CommandEngine — lightweight chat command dispatcher.

Manages cooldowns for !vibe and !request commands and exposes a push()
method to inject commands into the DSP/playback pipeline.
"""

from __future__ import annotations

import time


VALID_VIBES: tuple[str, ...] = (
    "ambient",
    "electronic",
    "jazz",
    "industrial",
    "neoclassical",
    "experimental",
    "drone",
)

VALID_GENRES: tuple[str, ...] = (
    "ambient",
    "electronic",
    "jazz",
    "industrial",
    "neoclassical",
    "experimental",
    "drone",
)

_VIBE_COOLDOWN_S: float = 120.0
_REQUEST_COOLDOWN_S: float = 60.0


class CommandEngine:
    """Tracks cooldowns and routes commands to downstream consumers."""

    def __init__(self) -> None:
        self._vibe_last: dict[str, float] = {}
        self._request_last: dict[str, float] = {}
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

    def try_vibe(self, mode: str) -> bool:
        """Return True and record timestamp if cooldown has elapsed."""
        now = time.monotonic()
        if now - self._vibe_last.get(mode, 0.0) >= _VIBE_COOLDOWN_S:
            self._vibe_last[mode] = now
            return True
        return False

    def cooldown_remaining(self, kind: str, arg: str) -> float:
        """Return seconds remaining before *arg* can be used again for *kind*."""
        now = time.monotonic()
        if kind == "vibe":
            return max(0.0, _VIBE_COOLDOWN_S - (now - self._vibe_last.get(arg, 0.0)))
        if kind == "request":
            return max(
                0.0, _REQUEST_COOLDOWN_S - (now - self._request_last.get(arg, 0.0))
            )
        return 0.0

    def try_request(self, genre: str) -> bool:
        """Return True and record timestamp if cooldown has elapsed."""
        now = time.monotonic()
        if now - self._request_last.get(genre, 0.0) >= _REQUEST_COOLDOWN_S:
            self._request_last[genre] = now
            return True
        return False
