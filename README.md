# ChatGPT Radio

A 24/7 YouTube live stream where music, visuals, and narration respond in real-time to signals from the OpenAI/AI world — service status, community sentiment, trending topics, and market data.

The system has no fixed mood or genre. It is its history of states.

## Architecture

```
Collectors → GlobalState → DSP → FFmpeg → RTMP → YouTube
                       ↘ WebSocket → Three.js overlay
```

- **Collectors** — poll external APIs (OpenAI Status, HN, Reddit, arXiv, yfinance, …) and push normalized signals into `GlobalState`
- **GlobalState** — single Pydantic v2 source of truth (~77 fields), persisted to SQLite WAL
- **Drift engine** — territorial momentum system that shapes the stream's emotional trajectory without any hardcoded constants
- **DSP pipeline** — Pedalboard + pyrubberband → adaptive crossfade → FFmpeg stdin → RTMP
- **Music generation** — Stable Audio 2.5 via fal.ai, with prompts derived from live state
- **Overlay** — Three.js + WebGL fed by WebSocket at 4 fps, strictly data-driven (no fake animation)

## Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12, asyncio |
| State | Pydantic v2, SQLite WAL (aiosqlite) |
| DSP | Pedalboard, pyrubberband |
| Music | Stable Audio 2.5 (fal.ai) |
| Visuals | Three.js, WebGL, OBS Browser Source |
| Chat | YouTube Live Chat API + GPT-4o-mini |
| Logs | structlog (JSON) |
| Tests | pytest, pyright, ruff |

## Setup

### Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) package manager
- FFmpeg with `libx264` and `libmp3lame`
- OBS Studio (for overlay capture)
- A YouTube channel with live streaming enabled

### Install

```bash
git clone https://github.com/chatgptradio/chatgptradio
cd chatgptradio
uv sync
cp .env.example .env
# fill in your API keys
```

### Run

```bash
uv run python main.py
```

### Tests

```bash
uv run pytest && uv run pyright && uv run ruff check .
```

## Configuration

Edit `config.yaml` to enable/disable collectors and set their polling intervals. All API credentials go in `.env` (see `.env.example`).

## The NO FAKE contract

Every visual element must be traceable to a real signal. If `GlobalState` freezes, the overlay must freeze. See `overlays/NO_FAKE.md` for the full specification.

## Architecture Decision Records

Design decisions are documented in [`docs/adr/`](docs/adr/).

## License

MIT
