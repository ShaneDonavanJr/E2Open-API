# E2open API starter

A tiny, read-only starter for poking at an E2open TMS / pricing tenant so you
can see what your account can reach.

## What's here

| File               | Purpose                                                       |
| ------------------ | ------------------------------------------------------------- |
| `e2open_client.py` | Thin client: handles auth (API key or session) + requests.    |
| `starter_pull.py`  | Entry point: authenticates and probes a few read-only routes. |
| `.env`             | Your real credentials (gitignored).                           |
| `.env.example`     | Template showing all supported settings.                      |
| `requirements.txt` | Python dependencies.                                          |

## Setup

```bash
pip install -r requirements.txt
```

Your `.env` already has `USERNAME`, `PASSWORD`, and `API_KEY`. You can also add
these optional settings (see `.env.example`):

```ini
E2OPEN_BASE_URL=https://na-api.tms.e2open.com   # your tenant host
E2OPEN_AUTH_MODE=auto                            # api_key | session | auto
```

## Run

```bash
python starter_pull.py            # authenticate + probe default endpoints
python starter_pull.py --no-probe # just verify auth works
python starter_pull.py --probe /Integration/xml/carrier   # probe a specific path
```

## Auth modes

E2open tenants expose different auth schemes. This starter supports the two
common TMS ones and will try both when `E2OPEN_AUTH_MODE=auto`:

- **api_key** — sends `Authorization: Basic base64(USERNAME:API_KEY)`.
- **session** — POSTs `USERNAME`/`PASSWORD` to `/Integration/xml/authenticate`,
  then sends the returned `LeanSessionID` header on each request.

## Reading the output

- **Auth fails on every mode, no HTTP codes** → the base URL/tenant is almost
  certainly wrong. Set `E2OPEN_BASE_URL` to your real tenant host.
- **You get `401`/`403`** → the host is right, but the credentials or mode need
  adjusting.
- **You get `200` / data** → you're in. The probe paths in
  `DEFAULT_PROBES` (top of `starter_pull.py`) are best guesses; replace them
  with your tenant's real routes as you discover them.

> Note: the probe paths are generic guesses. E2open route names vary by tenant
> and product (Real-Time Rating, Spot Market, Billing, Communications, etc.),
> so expect to adjust them.
