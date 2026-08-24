"""IFS ERP reverse proxy — HTTP/HTTPS + WebSocket to Streamlit."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, RedirectResponse, Response
from starlette.websockets import WebSocketDisconnect

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ifs_proxy")

ROOT = Path(__file__).resolve().parent
CERTS_DIR = Path(os.environ.get("IFS_CERTS_DIR", str(ROOT / "certs")))
ACME_WEBROOT = CERTS_DIR / "acme-www"
CERT_FILE = Path(
    os.environ.get(
        "IFS_SSL_CERT",
        str(CERTS_DIR / "config" / "live" / "erp.ifschemicals.com" / "fullchain.pem"),
    )
)
KEY_FILE = Path(
    os.environ.get(
        "IFS_SSL_KEY",
        str(CERTS_DIR / "config" / "live" / "erp.ifschemicals.com" / "privkey.pem"),
    )
)
PUBLIC_DOMAIN = os.environ.get("IFS_PUBLIC_DOMAIN", "erp.ifschemicals.com")

TARGET = os.environ.get("IFS_ERP_TARGET", "http://127.0.0.1:8501")
TARGET_WS = TARGET.replace("http://", "ws://").replace("https://", "wss://")
UPSTREAM_HOST = os.environ.get("IFS_ERP_UPSTREAM_HOST", "127.0.0.1:8501")
FORCE_HTTPS = os.environ.get("IFS_FORCE_HTTPS", "1").strip() not in ("0", "false", "no")

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "content-encoding",
}

app = FastAPI(title="IFS ERP Proxy", docs_url=None, redoc_url=None)
_http_client: httpx.AsyncClient | None = None


def ssl_ready() -> bool:
    return CERT_FILE.is_file() and KEY_FILE.is_file()


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=TARGET, timeout=None, follow_redirects=False)
    return _http_client


def _forward_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in HOP_HEADERS:
            continue
        out[key] = value
    out["Host"] = UPSTREAM_HOST
    out["X-Forwarded-For"] = request.client.host if request.client else ""
    # Prefer client-facing scheme (HTTPS terminate here)
    xf_proto = request.headers.get("x-forwarded-proto")
    if request.url.scheme == "https" or (request.scope.get("server") or ("", 0))[1] == 443:
        out["X-Forwarded-Proto"] = "https"
    elif xf_proto:
        out["X-Forwarded-Proto"] = xf_proto
    else:
        out["X-Forwarded-Proto"] = request.url.scheme
    out["X-Forwarded-Host"] = request.headers.get("host", "")
    return out


def _is_acme_path(path: str) -> bool:
    return path.startswith(".well-known/acme-challenge/")


@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_http(request: Request, path: str = ""):
    # Let's Encrypt HTTP-01
    if path and _is_acme_path(path):
        token = path.rsplit("/", 1)[-1]
        challenge = ACME_WEBROOT / ".well-known" / "acme-challenge" / token
        if challenge.is_file():
            return FileResponse(challenge, media_type="text/plain")
        return Response(content=b"challenge not found", status_code=404)

    # Redirect HTTP → HTTPS when certificates are installed
    port = (request.scope.get("server") or ("", 0))[1]
    is_https = request.url.scheme == "https" or port == 443
    if FORCE_HTTPS and ssl_ready() and not is_https and request.method in ("GET", "HEAD"):
        host = request.headers.get("host", PUBLIC_DOMAIN).split(":")[0]
        target = f"https://{host}{request.url.path}"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(url=target, status_code=301)

    target_path = f"/{path}" if path else "/"
    url = httpx.URL(path=target_path, query=request.url.query.encode())
    body = await request.body()
    req = get_http_client().build_request(
        request.method,
        url,
        headers=_forward_headers(request),
        content=body if body else None,
    )
    upstream = await get_http_client().send(req, stream=True)
    headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_HEADERS}
    content = await upstream.aread()
    await upstream.aclose()
    return Response(content=content, status_code=upstream.status_code, headers=headers)


async def _bridge_websockets(client: WebSocket, upstream) -> None:
    async def client_to_upstream():
        try:
            while True:
                msg = await client.receive()
                if msg.get("type") == "websocket.disconnect":
                    await upstream.close()
                    break
                if "text" in msg and msg["text"] is not None:
                    await upstream.send(msg["text"])
                elif "bytes" in msg and msg["bytes"] is not None:
                    await upstream.send(msg["bytes"])
        except WebSocketDisconnect:
            await upstream.close()

    async def upstream_to_client():
        async for message in upstream:
            if isinstance(message, bytes):
                await client.send_bytes(message)
            else:
                await client.send_text(message)

    await asyncio.gather(client_to_upstream(), upstream_to_client())


@app.websocket("")
@app.websocket("/{path:path}")
async def proxy_ws(websocket: WebSocket, path: str = ""):
    target_path = f"/{path}" if path else "/"
    query = websocket.scope.get("query_string", b"").decode()
    suffix = f"?{query}" if query else ""
    target_url = f"{TARGET_WS}{target_path}{suffix}"
    subprotocols = list(websocket.scope.get("subprotocols") or [])

    # Do NOT override Host — Tornado/Streamlit rejects WS with custom Host (HTTP 400).
    # Do NOT forward Origin — with enableCORS=true Streamlit 403s external domains.
    extra_headers: list[tuple[str, str]] = []
    for hdr in ("cookie", "user-agent", "sec-websocket-protocol"):
        val = websocket.headers.get(hdr)
        if val:
            extra_headers.append((hdr, val))

    try:
        import websockets

        async with websockets.connect(
            target_url,
            additional_headers=extra_headers or None,
            subprotocols=subprotocols or None,
            max_size=None,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            await websocket.accept(subprotocol=upstream.subprotocol)
            await _bridge_websockets(websocket, upstream)
    except Exception as exc:
        log.warning("WebSocket proxy failed %s: %s", target_url, exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@app.get("/healthz")
async def healthz():
    try:
        r = await get_http_client().get("/")
        body = b"ok" if r.status_code < 500 else b"upstream error"
        return Response(content=body, status_code=200 if r.status_code < 500 else 503)
    except Exception:
        return Response(content=b"upstream down", status_code=503)


async def _serve(config: uvicorn.Config) -> None:
    server = uvicorn.Server(config)
    await server.serve()


async def run_proxy() -> None:
    ACME_WEBROOT.mkdir(parents=True, exist_ok=True)
    (ACME_WEBROOT / ".well-known" / "acme-challenge").mkdir(parents=True, exist_ok=True)

    http_port = int(os.environ.get("IFS_PROXY_PORT", "80"))
    https_port = int(os.environ.get("IFS_PROXY_HTTPS_PORT", "443"))

    tasks = [
        _serve(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=http_port,
                log_level="info",
                ws="websockets",
            )
        )
    ]

    if ssl_ready():
        log.info("HTTPS enabled — cert=%s key=%s", CERT_FILE, KEY_FILE)
        tasks.append(
            _serve(
                uvicorn.Config(
                    app,
                    host="0.0.0.0",
                    port=https_port,
                    log_level="info",
                    ws="websockets",
                    ssl_certfile=str(CERT_FILE),
                    ssl_keyfile=str(KEY_FILE),
                )
            )
        )
    else:
        log.warning(
            "No SSL certs at %s — HTTP only. Run enable_https.bat after DNS is ready.",
            CERT_FILE,
        )

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(run_proxy())
