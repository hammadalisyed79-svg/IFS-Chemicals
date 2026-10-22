"""
Keep IFS ERP online: restart Streamlit and/or HTTPS proxy when health fails.

Designed to run as a long-lived process (Scheduled Task / START_ERP).
Single-instance via PID lock file under logs/.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "erp_watchdog.log"
PID_FILE = LOG_DIR / "erp_watchdog.pid"
PY = ROOT / "venv" / "Scripts" / "python.exe"

LOCAL_HEALTH = "http://127.0.0.1:8501/_stcore/health"
PUBLIC_HEALTH = "https://erp.ifschemicals.com/_stcore/health"

CHECK_EVERY_SEC = 30
START_GRACE_SEC = 90
PUBLIC_FAIL_BEFORE_PROXY_RESTART = 2


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def health_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore").strip().lower()
            return resp.status == 200 and (body == "ok" or body == "")
    except Exception:
        return False


def _ps(cmd: str) -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def kill_matching(pattern: str) -> None:
    # Stop by command line match
    _ps(
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -and ($_.CommandLine -match '{pattern}') }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )


def free_ports(*ports: int) -> None:
    port_list = ",".join(str(p) for p in ports)
    _ps(
        f"Get-NetTCPConnection -LocalPort {port_list} -ErrorAction SilentlyContinue | "
        "ForEach-Object { if ($_.OwningProcess -gt 0) { "
        "Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
    )


def start_streamlit() -> None:
    if not PY.exists():
        log(f"ERROR: venv python missing: {PY}")
        return
    env = os.environ.copy()
    env["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
    env["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"
    out = LOG_DIR / "streamlit_watchdog.out.log"
    err = LOG_DIR / "streamlit_watchdog.err.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fo, err.open("a", encoding="utf-8") as fe:
        fo.write(f"\n--- restart {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        fe.write(f"\n--- restart {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        subprocess.Popen(
            [
                str(PY),
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.headless",
                "true",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                "8501",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=fo,
            stderr=fe,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )


def start_proxy() -> None:
    if not PY.exists():
        log(f"ERROR: venv python missing: {PY}")
        return
    out = LOG_DIR / "proxy_watchdog.out.log"
    err = LOG_DIR / "proxy_watchdog.err.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fo, err.open("a", encoding="utf-8") as fe:
        fo.write(f"\n--- restart {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        fe.write(f"\n--- restart {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        subprocess.Popen(
            [str(PY), "ifs_reverse_proxy.py"],
            cwd=str(ROOT),
            stdout=fo,
            stderr=fe,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )


def wait_local(seconds: int = START_GRACE_SEC) -> bool:
    for i in range(1, seconds + 1):
        if health_ok(LOCAL_HEALTH):
            log(f"Streamlit healthy after {i}s")
            return True
        time.sleep(1)
    return False


def ensure_streamlit() -> bool:
    if health_ok(LOCAL_HEALTH):
        return True
    log("Streamlit DOWN - restarting backend on :8501")
    kill_matching(r"streamlit run app\.py")
    free_ports(8501)
    time.sleep(2)
    start_streamlit()
    if wait_local():
        return True
    log("ERROR: Streamlit failed to become healthy after restart")
    return False


def ensure_proxy(public_fail_streak: int) -> int:
    if not health_ok(LOCAL_HEALTH):
        return public_fail_streak
    if health_ok(PUBLIC_HEALTH, timeout=5.0):
        return 0
    streak = public_fail_streak + 1
    log(f"Public HTTPS health fail ({streak}/{PUBLIC_FAIL_BEFORE_PROXY_RESTART})")
    if streak < PUBLIC_FAIL_BEFORE_PROXY_RESTART:
        return streak
    log("HTTPS proxy DOWN or unhealthy - restarting ports 80/443")
    kill_matching(r"ifs_reverse_proxy")
    free_ports(80, 443)
    time.sleep(2)
    start_proxy()
    for i in range(1, 46):
        if health_ok(PUBLIC_HEALTH, timeout=5.0):
            log(f"Public site healthy after {i}s")
            return 0
        time.sleep(1)
    log("ERROR: Public HTTPS still unhealthy after proxy restart "
        "(need Administrator for ports 80/443?)")
    return 0  # reset streak to avoid tight restart loop


def acquire_single_instance():
    """Named mutex so only one watchdog runs per machine."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        name = "Global\\IFS_ERP_Watchdog"
        handle = kernel32.CreateMutexW(None, False, name)
        last = kernel32.GetLastError()
        # ERROR_ALREADY_EXISTS = 183
        if last == 183:
            if handle:
                kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        return object()  # best-effort fallback: allow start


def write_pid() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid() -> None:
    try:
        if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    os.chdir(ROOT)
    mutex = acquire_single_instance()
    if mutex is None:
        print("erp_watchdog already running - exit")
        return 0
    write_pid()
    atexit.register(clear_pid)
    log(f"Watchdog started pid={os.getpid()} root={ROOT}")
    public_fail = 0
    # Initial ensure
    ensure_streamlit()
    public_fail = ensure_proxy(PUBLIC_FAIL_BEFORE_PROXY_RESTART)  # force check once
    while True:
        try:
            if not ensure_streamlit():
                time.sleep(CHECK_EVERY_SEC)
                continue
            public_fail = ensure_proxy(public_fail)
        except Exception as exc:
            log(f"Watchdog loop error: {exc!r}")
        time.sleep(CHECK_EVERY_SEC)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("Watchdog stopped (KeyboardInterrupt)")
        raise SystemExit(0)
