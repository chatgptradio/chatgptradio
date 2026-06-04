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
        overlay_url = f"http://localhost:{port}/visualizer.html?v={int(_time.time())}"
        return await asyncio.create_subprocess_exec(
            chromium_bin,
            "--no-sandbox",
            "--disable-gpu",
            "--enable-unsafe-swiftshader",   # software WebGL — EGL+virgl incompatible avec Xvfb/x11grab
            "--ignore-gpu-blocklist",
            "--use-gl=swiftshader",
            "--disable-gpu-vsync",           # évite l'auto-throttle SwiftShader
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
            "--enable-logging=stderr",
            "--log-level=0",
            f"--app={overlay_url}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=open("/tmp/chromium_console.log", "a"),
        )

    chrome = await _start_chromium()
    log.info("chromium_started", url=f"http://localhost:{port}/visualizer.html")
    await asyncio.sleep(3.0)
    ready_event.set()
    log.info("browser_display_ready")

    # Restart Chromium every 35min — SwiftShader state degrades at ~47min causing
    # fps drop. 35min keeps the JS heap fresh well before the onset threshold.
    _CHROMIUM_RESTART_INTERVAL = 35 * 60
    _last_chromium_start = _time.monotonic()

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
                _last_chromium_start = _time.monotonic()
                log.info("chromium_restarted")
                await asyncio.sleep(2.0)
            elif _time.monotonic() - _last_chromium_start >= _CHROMIUM_RESTART_INTERVAL:
                # Proactive restart to clear V8/SwiftShader memory accumulation
                log.info("chromium_periodic_restart", interval_min=_CHROMIUM_RESTART_INTERVAL // 60)
                chrome.terminate()
                await asyncio.sleep(2.0)
                chrome = await _start_chromium()
                _last_chromium_start = _time.monotonic()
                await asyncio.sleep(2.0)
                # Renice new GPU process — same as restart.sh does at initial start.
                # Without this, the GPU process runs at normal priority after each
                # periodic restart and competes with ffmpeg for CPU → frame drops.
                try:
                    import subprocess as _sp
                    _gpu_pids = _sp.run(
                        ["pgrep", "-f", "gpu-process"],
                        capture_output=True, text=True,
                    ).stdout.split()
                    for _pid in _gpu_pids:
                        try:
                            import os as _os
                            _os.setpriority(_os.PRIO_PROCESS, int(_pid), 10)
                        except (OSError, ValueError):
                            pass
                    if _gpu_pids:
                        log.info("chromium_gpu_reniced", count=len(_gpu_pids))
                except Exception:
                    pass

            await asyncio.sleep(5.0)
    finally:
        if xvfb.returncode is None:
            xvfb.terminate()
        if chrome.returncode is None:
            chrome.terminate()
