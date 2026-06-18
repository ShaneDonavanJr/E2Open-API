"""Minimal E2open TMS API client.

Supports the two auth modes a TMS / pricing tenant typically exposes:

  * api_key  -> Authorization: Basic base64(USERNAME:API_KEY)
  * session  -> POST USERNAME/PASSWORD to the authenticate endpoint, then
                send the returned LeanSessionID on every subsequent request.

The client is intentionally thin: it handles auth + sane default headers and
gives you a `request()` helper so you can poke at any endpoint to "see options".
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field

import requests


@dataclass
class E2openConfig:
    base_url: str
    username: str
    password: str
    api_key: str
    auth_mode: str = "auto"  # "api_key", "session", or "auto"
    auth_path: str = "/Integration/xml/authenticate"
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "E2openConfig":
        base_url = os.getenv("E2OPEN_BASE_URL", "https://na-api.tms.e2open.com")
        return cls(
            base_url=base_url.rstrip("/"),
            username=os.getenv("USERNAME", ""),
            password=os.getenv("PASSWORD", ""),
            api_key=os.getenv("API_KEY", ""),
            auth_mode=os.getenv("E2OPEN_AUTH_MODE", "auto").lower(),
            auth_path=os.getenv("E2OPEN_AUTH_PATH", "/Integration/xml/authenticate"),
        )


@dataclass
class AuthResult:
    mode: str
    ok: bool
    detail: str = ""
    status_code: int | None = None


class E2openClient:
    def __init__(self, config: E2openConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "e2open-starter/1.0",
                "Origin": config.base_url,
                "Referer": config.base_url + "/",
            }
        )
        self.active_mode: str | None = None
        self.lean_session_id: str | None = None

    # --- auth -------------------------------------------------------------
    def _basic_header(self) -> str:
        raw = f"{self.config.username}:{self.config.api_key}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _try_api_key(self) -> AuthResult:
        if not self.config.api_key:
            return AuthResult("api_key", False, "No API_KEY set")
        self.session.headers["Authorization"] = self._basic_header()
        self.active_mode = "api_key"
        return AuthResult("api_key", True, "Basic auth header set (not yet verified)")

    def _try_session(self) -> AuthResult:
        if not (self.config.username and self.config.password):
            return AuthResult("session", False, "Missing USERNAME or PASSWORD")
        url = self.config.base_url + self.config.auth_path
        try:
            resp = self.session.post(
                url,
                json={
                    "username": self.config.username,
                    "password": self.config.password,
                },
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            return AuthResult("session", False, f"Request failed: {exc}")

        if resp.status_code >= 400:
            return AuthResult(
                "session", False, f"HTTP {resp.status_code}: {resp.text[:200]}",
                resp.status_code,
            )

        session_id = self._extract_session_id(resp)
        if not session_id:
            return AuthResult(
                "session", False,
                f"Authenticated (HTTP {resp.status_code}) but no LeanSessionID found",
                resp.status_code,
            )
        self.lean_session_id = session_id
        self.session.headers["LeanSessionID"] = session_id
        self.active_mode = "session"
        return AuthResult("session", True, "LeanSessionID obtained", resp.status_code)

    @staticmethod
    def _extract_session_id(resp: requests.Response) -> str | None:
        try:
            data = resp.json()
        except ValueError:
            return None
        for key in ("LeanSessionID", "leanSessionId", "sessionId", "SessionId", "token"):
            if isinstance(data, dict) and data.get(key):
                return str(data[key])
        return None

    def authenticate(self) -> list[AuthResult]:
        """Authenticate per the configured mode; returns each attempt's result."""
        attempts: list[AuthResult] = []
        mode = self.config.auth_mode
        order = ["api_key", "session"] if mode == "auto" else [mode]
        for m in order:
            result = self._try_api_key() if m == "api_key" else self._try_session()
            attempts.append(result)
            if result.ok:
                break
        return attempts

    # --- requests ---------------------------------------------------------
    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else self.config.base_url + path
        kwargs.setdefault("timeout", self.config.timeout)
        return self.session.request(method, url, **kwargs)

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.request("POST", path, **kwargs)
