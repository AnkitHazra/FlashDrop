# FlashDrop — temporary file sharing 

FlashDrop is a FastAPI application that accepts a file upload, stores file bytes in a temporary server directory, stores metadata in SQLite, and generates a share URL and QR code. Links expire after **10 minutes from the time the upload completes**. Multiple downloads are allowed until expiry.

## Features

- Responsive upload and download pages
- Upload progress and browser-side file-size check
- Server-side upload-size enforcement (100 MiB by default)
- Unpredictable, URL-safe share tokens
- Shareable link and QR code
- Server-enforced expiration at every share, status, QR, and download request
- Scheduled cleanup every 15 seconds, plus cleanup at startup
- Multiple downloads before expiry
- Optional file-extension allow-list
- Docker deployment with persistent volume for SQLite and temporary files

## Requirements

- Python 3.11+ (Docker uses Python 3.12)
- A writable disk for SQLite and temporary uploads
- For public internet deployment: a domain, HTTPS reverse proxy, and a server with persistent storage

## Run locally

From the project root:

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `PUBLIC_BASE_URL` to your reachable origin. For local-only testing, `PUBLIC_BASE_URL=http://127.0.0.1:8000` works for the browser on the same PC. A phone cannot reach your PC using `127.0.0.1`; use the PC's LAN IP and allow port 8000 through the firewall for LAN tests.

Start the app:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`, then run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Public internet deployment (recommended: Docker + HTTPS reverse proxy)

1. Provision a VPS or server with persistent disk and Docker Compose.
2. Point a DNS A/AAAA record for your domain to the server.
3. Copy this project to the server.
4. Create `.env` from `.env.example` and set `PUBLIC_BASE_URL=https://your-real-domain.example`.
5. Run:

   ```bash
   docker compose up --build -d
   docker compose logs -f quickshare
   ```

6. Configure a reverse proxy such as Caddy or Nginx to proxy HTTPS traffic for your domain to `127.0.0.1:8000`. Keep port 8000 private to the host if the proxy runs on the same machine. Use a valid TLS certificate.
7. Verify `https://your-real-domain.example/health` returns `{"status":"ok"}`.

Do not publish the example domain. Set `PUBLIC_BASE_URL` to your actual public HTTPS origin or QR code generation will be disabled. The application uses the configured origin for QR links to avoid generating links to an internal proxy hostname.

### Minimal Caddy example

Replace `share.example.com` with your domain:

```caddyfile
share.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy can obtain and renew HTTPS certificates automatically when DNS and ports 80/443 are correctly configured.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PUBLIC_BASE_URL` | empty | Public origin used in generated links and QR codes |
| `DATA_DIR` | project root | Persistent data directory |
| `UPLOAD_DIR` | `DATA_DIR/temp_uploads` | Temporary file bytes |
| `DATABASE_PATH` | `DATA_DIR/quickshare.sqlite3` | SQLite metadata database |
| `MAX_FILE_SIZE` | `104857600` | Maximum file size in bytes (100 MiB) |
| `ALLOWED_EXTENSIONS` | empty | Optional comma-separated extension allow-list |
| `CLEANUP_INTERVAL_SECONDS` | `15` | Background cleanup interval |
| `LOG_LEVEL` | `INFO` | Application logging level |

Example extension allow-list:

```env
ALLOWED_EXTENSIONS=pdf,png,jpg,jpeg,zip,txt,docx,xlsx
```

## API

- `GET /` — upload page
- `POST /api/upload` — upload a multipart file; returns JSON with `share_url`, `qr_url`, `expires_at`, and `ttl_seconds`
- `GET /s/{token}` — share/download page
- `GET /api/file/{token}` — download file
- `GET /api/qr/{token}` — PNG QR code (requires `PUBLIC_BASE_URL`)
- `GET /api/status/{token}` — metadata and remaining time
- `GET /health` — health check

## Expiry behavior

The server checks `expires_at` before showing the share page, returning status, serving the QR code, or starting a download. The scheduled task removes expired files and database rows every 15 seconds. Therefore, physical cleanup may lag expiry by up to roughly one cleanup interval under normal conditions, but the server rejects downloads as soon as the expiration timestamp is reached.

A download that started before expiry may continue streaming after the deadline. Preventing that would require a custom streaming response that rechecks the deadline while streaming. This implementation prevents new downloads after expiry.

## Security and production checklist

- Use HTTPS. Share links are bearer secrets: anyone who has the link can download the file.
- Keep `DATA_DIR` on persistent local storage. Do not use ephemeral container storage for production.
- Set an extension allow-list if your use case permits only known file types. Extension checks are not malware scanning.
- Configure reverse-proxy upload body limits to at least the application's limit, or uploads may be rejected by the proxy first.
- Apply rate limiting at the reverse proxy or hosting platform to limit abuse and resource exhaustion.
- Consider malware scanning, quotas, abuse reporting, and authentication for a public anonymous service.
- Do not serve uploaded content inline; downloads use `application/octet-stream` and `nosniff`.
- Back up deployment configuration, but avoid backing up temporary uploads unless intentionally required.
- For multiple app workers or multiple server instances, ensure they share the same persistent filesystem and SQLite database. For higher traffic, migrate metadata to PostgreSQL and use shared object storage.
- SQLite and local disk are suitable for a small deployment, not a large-scale multi-region service.

## Notes

- QR codes are generated dynamically for active tokens; the browser requests the QR image from the server.
- Files are stored under random server-generated names, never the original filename.
- The 10-minute timer starts after the upload has been fully received and saved.
