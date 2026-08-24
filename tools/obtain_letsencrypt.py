"""Obtain / renew Let's Encrypt certificate for erp.ifschemicals.com (HTTP-01)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERTS = ROOT / "certs"
WEBROOT = CERTS / "acme-www"
CONFIG = CERTS / "config"
WORK = CERTS / "work"
LOGS = CERTS / "logs"
DOMAIN = os.environ.get("IFS_PUBLIC_DOMAIN", "erp.ifschemicals.com")
EMAIL = os.environ.get("IFS_LE_EMAIL", "admin@ifschemicals.com")


def main() -> int:
    for p in (WEBROOT / ".well-known" / "acme-challenge", CONFIG, WORK, LOGS):
        p.mkdir(parents=True, exist_ok=True)

    py = ROOT / "venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    # Ensure certbot is available in the same interpreter
    try:
        import certbot  # noqa: F401
    except ImportError:
        print("Installing certbot ...")
        r = subprocess.run(
            [str(py), "-m", "pip", "install", "certbot"],
            cwd=str(ROOT),
        )
        if r.returncode != 0:
            print("ERROR: could not install certbot")
            return 1

    certbot_exe = ROOT / "venv" / "Scripts" / "certbot.exe"
    if certbot_exe.is_file():
        launcher = [str(certbot_exe)]
    else:
        launcher = [str(py), "-m", "certbot"]
    cmd = launcher + [
        "certonly",
        "--webroot",
        "-w",
        str(WEBROOT),
        "-d",
        DOMAIN,
        "--config-dir",
        str(CONFIG),
        "--work-dir",
        str(WORK),
        "--logs-dir",
        str(LOGS),
        "--agree-tos",
        "--email",
        EMAIL,
        "--non-interactive",
        "--keep-until-expiring",
        "--preferred-challenges",
        "http",
    ]
    print("Running:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        print("\nERROR: certificate request failed.")
        print("Check DNS: erp.ifschemicals.com -> 138.201.139.157")
        print("Check Hetzner firewall allows TCP 80 from the internet.")
        print("Proxy must be running so /.well-known/acme-challenge/ is served.")
        return r.returncode

    cert = CONFIG / "live" / DOMAIN / "fullchain.pem"
    key = CONFIG / "live" / DOMAIN / "privkey.pem"
    print("\nOK — certificate ready:")
    print(" ", cert)
    print(" ", key)
    print("\nRestart proxy: restart_https.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
