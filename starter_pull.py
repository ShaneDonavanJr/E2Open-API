"""E2open starter pull.

Loads credentials from .env, authenticates, and probes a handful of common
TMS endpoints so you can see what's reachable with your account. Nothing here
is destructive -- it only issues read (GET) requests.

Usage:
    python starter_pull.py                 # auto: authenticate + probe endpoints
    python starter_pull.py --probe /some/path
    python starter_pull.py --no-probe      # just authenticate and stop
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from e2open_client import E2openClient, E2openConfig

# Candidate endpoints to probe, grouped by what a broker typically wants.
# These are best-guess paths drawn from common e2open/BluJay TMS surfaces;
# the real names come from your tenant's integration spec. Edit freely.
DEFAULT_PROBES = [
    # --- Customers / shipper master data ---
    "/Integration/xml/shipper/customer",
    "/Integration/xml/customer",
    "/Integration/json/customer",
    "/Integration/xml/shipper",
    # --- Tenders (loads offered to you as the broker/carrier) ---
    "/Integration/xml/tender",
    "/Integration/xml/tenders",
    "/Integration/json/tender",
    "/Integration/xml/load/tender",
    "/Integration/xml/shipment/tender",
]

LINE = "-" * 70


def banner(text: str) -> None:
    print(f"\n{LINE}\n{text}\n{LINE}")


def show_response(resp) -> None:
    ct = resp.headers.get("Content-Type", "")
    print(f"  -> HTTP {resp.status_code}  ({ct or 'no content-type'})")
    body = resp.text or ""
    if "json" in ct.lower():
        try:
            pretty = json.dumps(resp.json(), indent=2)
            print("\n".join("     " + ln for ln in pretty.splitlines()[:30]))
            return
        except ValueError:
            pass
    snippet = body[:500].strip()
    if snippet:
        print("\n".join("     " + ln for ln in snippet.splitlines()[:15]))


def discover_methods(client, path: str) -> str | None:
    """Return the allowed HTTP methods for a path, if the server reveals them.

    A 405 response and/or an OPTIONS request usually carry an `Allow` header,
    which tells us how an endpoint that exists is actually meant to be called.
    """
    try:
        opt = client.request("OPTIONS", path)
    except Exception:  # noqa: BLE001
        return None
    allow = opt.headers.get("Allow") or opt.headers.get("allow")
    return allow


def classify(status: int) -> str:
    if status == 200:
        return "reachable + data"
    if status in (401, 403):
        return "exists but auth/permission issue"
    if status == 405:
        return "exists, wrong HTTP method"
    if status == 404:
        return "not found (wrong path)"
    return "see response"


def main() -> int:
    parser = argparse.ArgumentParser(description="E2open starter pull")
    parser.add_argument(
        "--probe", action="append", default=None,
        help="Endpoint path to GET (repeatable). Overrides the default list.",
    )
    parser.add_argument(
        "--no-probe", action="store_true",
        help="Only authenticate; do not probe endpoints.",
    )
    args = parser.parse_args()

    # override=True so values in .env win over OS env vars. On Windows the OS
    # always sets USERNAME, which would otherwise shadow the .env value.
    load_dotenv(override=True)
    config = E2openConfig.from_env()

    banner("E2open starter pull — configuration")
    print(f"  Base URL : {config.base_url}")
    print(f"  Username : {config.username or '(missing)'}")
    print(f"  API key  : {'set' if config.api_key else '(missing)'}")
    print(f"  Password : {'set' if config.password else '(missing)'}")
    print(f"  Auth mode: {config.auth_mode}")

    if not config.username:
        print("\nERROR: USERNAME is empty. Fill in your .env first.")
        return 1

    client = E2openClient(config)

    banner("Authenticating")
    attempts = client.authenticate()
    for a in attempts:
        flag = "OK " if a.ok else "xx "
        code = f"[{a.status_code}] " if a.status_code else ""
        print(f"  {flag}{a.mode:8} {code}{a.detail}")

    if not client.active_mode:
        print(
            "\nNo auth mode succeeded. Most likely the base URL/tenant is wrong.\n"
            "Set E2OPEN_BASE_URL in .env to your tenant host and try again.\n"
            "(Reaching a host but getting 401/403 means the URL is right but the\n"
            " credentials/mode need adjusting.)"
        )
        return 2

    print(f"\nActive auth mode: {client.active_mode}")

    if args.no_probe:
        return 0

    probes = args.probe if args.probe else DEFAULT_PROBES
    banner(f"Probing {len(probes)} endpoint(s)")
    findings: list[tuple[str, int, str]] = []
    for path in probes:
        print(f"\n• GET {path}")
        try:
            resp = client.get(path)
        except Exception as exc:  # noqa: BLE001 - surface anything to the user
            print(f"  -> request error: {exc}")
            continue
        show_response(resp)
        verdict = classify(resp.status_code)
        # When the path exists but rejects GET, find out what it does accept.
        if resp.status_code == 405:
            allow = resp.headers.get("Allow") or discover_methods(client, path)
            if allow:
                print(f"     allowed methods: {allow}")
                verdict += f" (try: {allow})"
        findings.append((path, resp.status_code, verdict))

    banner("Summary — what's reachable")
    for path, status, verdict in findings:
        print(f"  [{status}] {path}\n        {verdict}")

    banner("Next steps")
    print(
        "• [200] paths are live — wire those up for real pulls.\n"
        "• [405] paths exist but want a different method (see 'allowed methods').\n"
        "• [401/403] means the host/path is right but permissions/IP allowlist.\n"
        "• [404] everywhere usually means E2OPEN_BASE_URL is the wrong tenant host.\n"
        "Pass --probe <path> to test a specific route from your tenant's spec."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
