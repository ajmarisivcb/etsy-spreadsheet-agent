"""Etsy Open API v3 wrapper.

Auth: OAuth 2.0 with PKCE. Etsy returns access tokens prefixed with the user
ID (e.g. `12345.abc...`); the prefix is the user_id.

Docs: https://developers.etsy.com/documentation/reference/
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import requests

from .. import config

API_BASE = "https://openapi.etsy.com/v3"
AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

# Scopes — write listings + files + read receipts. See:
# https://developers.etsy.com/documentation/essentials/authentication#scopes
SCOPES = "listings_w listings_r listings_d shops_r shops_w transactions_r"


# ---------- OAuth (PKCE) ----------

def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def authorize_interactive() -> dict:
    """Run the full OAuth dance: open browser, capture redirect, exchange code.

    Persists access_token / refresh_token / expires_at / user_id / shop_id to .env.
    Returns the token dict.
    """
    if not config.ETSY_CLIENT_ID:
        raise RuntimeError("Set ETSY_CLIENT_ID in .env first")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": config.ETSY_CLIENT_ID,
        "redirect_uri": config.ETSY_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    parsed = urllib.parse.urlparse(config.ETSY_REDIRECT_URI)
    port = parsed.port or 8765

    captured: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = urllib.parse.urlparse(self.path).query
            captured.update(urllib.parse.parse_qs(qs, keep_blank_values=True))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>You can close this tab.</h2>")

        def log_message(self, *args, **kwargs):
            pass

    server = socketserver.TCPServer(("localhost", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"Opening browser to authorize Etsy...\nIf it doesn't open, visit:\n{url}")
    webbrowser.open(url)

    # Wait for the redirect (max 5 minutes)
    deadline = time.time() + 300
    while "code" not in captured and "error" not in captured and time.time() < deadline:
        time.sleep(0.2)
    server.shutdown()

    if "error" in captured:
        raise RuntimeError(f"Etsy authorization error: {captured}")
    if captured.get("state", [""])[0] != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF")

    code = captured["code"][0]
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": config.ETSY_CLIENT_ID,
            "redirect_uri": config.ETSY_REDIRECT_URI,
            "code": code,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tok = resp.json()

    _store_token(tok)
    user_id = tok["access_token"].split(".", 1)[0]
    config.persist("ETSY_USER_ID", user_id)

    # Fetch the shop_id for convenience
    shop = _request("GET", f"/application/users/{user_id}/shops",
                    access_token=tok["access_token"])
    if shop:
        shop_id = str(shop["shop_id"])
        config.persist("ETSY_SHOP_ID", shop_id)

    return tok


def _store_token(tok: dict) -> None:
    config.persist("ETSY_ACCESS_TOKEN", tok["access_token"])
    config.persist("ETSY_REFRESH_TOKEN", tok["refresh_token"])
    config.persist(
        "ETSY_TOKEN_EXPIRES_AT", str(int(time.time() + int(tok["expires_in"]))),
    )


def refresh_token() -> str:
    if not config.ETSY_REFRESH_TOKEN:
        raise RuntimeError("No refresh token — run `cli auth` first")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": config.ETSY_CLIENT_ID,
            "refresh_token": config.ETSY_REFRESH_TOKEN,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tok = resp.json()
    _store_token(tok)
    return tok["access_token"]


def _access_token() -> str:
    # Re-read from env in case a refresh happened earlier this run
    import os
    token = os.environ.get("ETSY_ACCESS_TOKEN") or config.ETSY_ACCESS_TOKEN
    if not token:
        raise RuntimeError("Not authenticated — run `python -m etsy_agent.cli auth`")
    if config.token_is_expired():
        token = refresh_token()
    return token


# ---------- Low-level request ----------

def _request(method: str, path: str, *, access_token: str | None = None,
             json: dict | None = None, params: dict | None = None,
             files: dict | None = None, data: dict | None = None) -> Any:
    token = access_token or _access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": config.ETSY_CLIENT_ID,
    }
    resp = requests.request(
        method,
        f"{API_BASE}{path}",
        headers=headers,
        json=json,
        params=params,
        files=files,
        data=data,
        timeout=60,
    )
    if resp.status_code == 204 or not resp.content:
        return None
    if not resp.ok:
        raise requests.HTTPError(
            f"{method} {path} → {resp.status_code}: {resp.text}", response=resp,
        )
    body = resp.json()
    # Etsy paginated responses wrap items in {results: [...], count: N}
    if isinstance(body, dict) and "results" in body and "count" in body:
        return body["results"]
    return body


# ---------- High-level helpers ----------

def shop_id() -> str:
    if not config.ETSY_SHOP_ID:
        raise RuntimeError("ETSY_SHOP_ID not set — run `cli auth` to populate it")
    return config.ETSY_SHOP_ID


def create_draft_listing(*, title: str, description: str, price: float, tags: list[str],
                         materials: list[str] | None = None,
                         taxonomy_id: int = 6735,
                         quantity: int = 999) -> dict:
    """Create a draft (non-published) digital download listing.

    Default taxonomy_id 6735 = "Digital Prints" — change if your niche fits a
    different category. List taxonomies via GET /application/seller-taxonomy/nodes.
    """
    payload = {
        "quantity": quantity,
        "title": title[:140],
        "description": description,
        "price": round(float(price), 2),
        "who_made": "i_did",
        "when_made": "made_to_order",
        "taxonomy_id": taxonomy_id,
        "type": "download",
        "is_digital": True,
        "tags": tags[:13],  # Etsy max 13 tags
        "materials": materials or [],
        "state": "draft",  # NEVER auto-publish
        "should_auto_renew": False,
    }
    return _request("POST", f"/application/shops/{shop_id()}/listings", json=payload)


def upload_listing_image(listing_id: int, image_path: str | Path, rank: int = 1) -> dict:
    path = Path(image_path)
    with path.open("rb") as f:
        files = {"image": (path.name, f, "image/png")}
        return _request(
            "POST",
            f"/application/shops/{shop_id()}/listings/{listing_id}/images",
            files=files,
            data={"rank": rank},
        )


def upload_listing_file(listing_id: int, file_path: str | Path,
                        name: str | None = None, rank: int = 1) -> dict:
    path = Path(file_path)
    with path.open("rb") as f:
        files = {"file": (name or path.name, f, "application/octet-stream")}
        return _request(
            "POST",
            f"/application/shops/{shop_id()}/listings/{listing_id}/files",
            files=files,
            data={"name": name or path.name, "rank": rank},
        )


def list_shop_listings(state: str = "draft", limit: int = 25) -> list[dict]:
    """state: draft | active | inactive | sold_out | expired"""
    return _request(
        "GET",
        f"/application/shops/{shop_id()}/listings",
        params={"state": state, "limit": limit},
    )


def update_listing(listing_id: int, **fields) -> dict:
    """Patch listing fields (title, description, price, tags, state, ...).

    To publish a draft: update_listing(id, state='active').
    """
    return _request(
        "PATCH",
        f"/application/shops/{shop_id()}/listings/{listing_id}",
        json=fields,
    )


def get_receipts(limit: int = 25) -> list[dict]:
    return _request(
        "GET",
        f"/application/shops/{shop_id()}/receipts",
        params={"limit": limit},
    )


def get_listing(listing_id: int) -> dict:
    return _request("GET", f"/application/listings/{listing_id}")
