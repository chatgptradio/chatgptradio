"""Headless browser display — Xvfb + Chromium for overlay rendering."""
from __future__ import annotations

import asyncio
import os
import shutil

import structlog

log = structlog.get_logger()

_DISPLAY = os.environ.get("OVERLAY_DISPLAY", ":99")
_OVERLAY_PORT = int(os.environ.get("OVERLAY_HTTP_PORT", "8080"))


async def run_browser_display(
    ready_event: asyncio.Event,
    display: str = _DISPLAY,
    port: int = _OVERLAY_PORT,
) -> None:
    """Start Xvfb + Chromium pointing at the local overlay HTTP server.

    Sets ready_event once Chromium has had time to load and connect to WS.
    Restarts Chromium automatically if it crashes.
    """
    if not shutil.which("Xvfb"):
        log.warning("browser_display_skipped", reason="Xvfb not found")
        ready_event.set()
        return

    import time as _time
    overlay_url = f"http://localhost:{port}/visualizer.html?v={int(_time.time())}"

    # Start Xvfb
    xvfb = await asyncio.create_subprocess_exec(
        "Xvfb", display, "-screen", "0", "1280x720x24",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    log.info("xvfb_started", display=display)
    await asyncio.sleep(1.0)

    chromium_bin = shutil.which("chromium-browser") or shutil.which("chromium")
    if not chromium_bin:
        log.warning("browser_display_skipped", reason="chromium not found")
        xvfb.terminate()
        ready_event.set()
        return

    async def _start_chromium() -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            "nice", "-n", "5",               # slight yield to FFmpeg; 10 was too aggressive on 2-core
            chromium_bin,
            "--no-sandbox",
            "--disable-gpu",
            "--enable-unsafe-swiftshader",   # software WebGL — EGL+virgl incompatible with Xvfb/x11grab
            "--ignore-gpu-blocklist",
            "--use-gl=swiftshader",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--test-type",                   # suppresses --no-sandbox warning bar
            "--window-size=1280,720",
            # Headless overhead reduction
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--disable-notifications",
            "--disable-default-apps",
            "--disable-hang-monitor",
            "--disable-component-update",
            "--disable-client-side-phishing-detection",
            "--mute-audio",                  # audio goes through FFmpeg pipe, not Chromium
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            f"--display={display}",
            f"--app={overlay_url}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    chrome = await _start_chromium()
    log.info("chromium_started", url=overlay_url)
    await asyncio.sleep(3.0)
    ready_event.set()
    log.info("browser_display_ready")

    try:
        while True:
            # Check if xvfb died
            if xvfb.returncode is not None:
                log.warning("xvfb_died", returncode=xvfb.returncode)
                xvfb = await asyncio.create_subprocess_exec(
                    "Xvfb", display, "-screen", "0", "1280x720x24",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.sleep(1.0)

            # Check if chromium died → restart
            if chrome.returncode is not None:
                log.warning("chromium_died", returncode=chrome.returncode)
                chrome = await _start_chromium()
                log.info("chromium_restarted")
                await asyncio.sleep(2.0)

            await asyncio.sleep(5.0)
    finally:
        if xvfb.returncode is None:
            xvfb.terminate()
        if chrome.returncode is None:
            chrome.terminate()
