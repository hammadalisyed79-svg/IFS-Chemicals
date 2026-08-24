"""Public deployment settings — domain, URLs, server IP."""

from __future__ import annotations

# Main company website (WooCommerce — do NOT point ERP here)
MAIN_WEBSITE_DOMAIN = "ifschemicals.com"
MAIN_WEBSITE_IP = "170.249.216.178"

# ERP subdomain — point DNS A record to SERVER_PUBLIC_IP
PUBLIC_DOMAIN = "erp.ifschemicals.com"

# Server public IP (Hetzner ERP host)
SERVER_PUBLIC_IP = "138.201.139.157"

# User-facing URLs
PUBLIC_URL_HTTP = f"http://{PUBLIC_DOMAIN}"
PUBLIC_URL_HTTPS = f"https://{PUBLIC_DOMAIN}"
PORTAL_URL_HTTP = f"http://{PUBLIC_DOMAIN}/portal"
PORTAL_URL_HTTPS = f"https://{PUBLIC_DOMAIN}/portal"

# Direct IP fallback (works before DNS is set)
PUBLIC_URL_IP_HTTP = f"http://{SERVER_PUBLIC_IP}"

# Internal Streamlit (never expose publicly in production)
ERP_INTERNAL_HOST = "127.0.0.1"
ERP_INTERNAL_PORT = 8501
PORTAL_INTERNAL_PORT = 8502


def public_base_url(*, ssl: bool | None = None) -> str:
    """Best URL for links shown to users."""
    if ssl is True:
        return PUBLIC_URL_HTTPS
    if ssl is False:
        return PUBLIC_URL_HTTP
    try:
        from erp_core.v15_security import is_ssl_configured
        return PUBLIC_URL_HTTPS if is_ssl_configured() else PUBLIC_URL_HTTP
    except Exception:
        return PUBLIC_URL_HTTP
