"""Apply ifschemicals.com domain settings to the ERP database."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from erp_deploy import (
    MAIN_WEBSITE_DOMAIN,
    PUBLIC_DOMAIN,
    PUBLIC_URL_HTTP,
    PUBLIC_URL_HTTPS,
    PUBLIC_URL_IP_HTTP,
    SERVER_PUBLIC_IP,
)


def main() -> None:
    import database as db
    from db_v3 import set_setting

    db.init_db()
    pairs = {
        "public_domain": PUBLIC_DOMAIN,
        "public_url": PUBLIC_URL_HTTPS,
        "public_url_http": PUBLIC_URL_HTTP,
        "company_website": MAIN_WEBSITE_DOMAIN,
        "erp_server_ip": SERVER_PUBLIC_IP,
    }
    for key, value in pairs.items():
        set_setting(key, value)
        print(f"  {key} = {value}")

    try:
        from application.config import config
        config.set("deploy", "domain", PUBLIC_DOMAIN)
        config.set("deploy", "public_url", PUBLIC_URL_HTTPS)
    except Exception:
        pass

    print(f"\nERP URL (after DNS): {PUBLIC_URL_HTTP}")
    print(f"Works now via IP:    {PUBLIC_URL_IP_HTTP}")
    print(f"Main website stays:  https://{MAIN_WEBSITE_DOMAIN}/")


if __name__ == "__main__":
    main()
