import asyncio
import logging
import mimetypes
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import qrcode
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.cleanup import cleanup_expired_files, cleanup_loop
from app.config import (
    ALLOWED_EXTENSIONS, MAX_FILE_SIZE, PUBLIC_BASE_URL, TTL_SECONDS, UPLOAD_DIR
)
from app.database import connection, init_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app_stop = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    cleanup_expired_files()
    task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="QuickShare", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def clean_display_name(name: str) -> str:
    # Never use user-provided names as disk paths or response header values.
    name = (name or "download").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in "\r\n")
    name = name.strip().strip(".")
    return name[:180] or "download"


def get_share(token: str):
    with connection() as conn:
        row = conn.execute("SELECT * FROM files WHERE token = ?", (token,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="This share link does not exist or has expired.")
    if time.time() >= row["expires_at"]:
        # Best-effort immediate removal; scheduled cleanup is the fallback.
        try:
            (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not immediately remove expired file")
        with connection() as conn:
            conn.execute("DELETE FROM files WHERE token = ?", (token,))
        raise HTTPException(status_code=410, detail="This share link has expired.")
    return row


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "max_file_mb": MAX_FILE_SIZE // (1024 * 1024),
        },
    )

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    original_name = clean_display_name(file.filename or "download")
    suffix = Path(original_name).suffix.lower().lstrip(".")

    if ALLOWED_EXTENSIONS and suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="This file extension is not allowed by the server configuration."
        )

    token = secrets.token_urlsafe(24)
    stored_name = f"{uuid.uuid4().hex}.bin"
    destination = UPLOAD_DIR / stored_name
    size = 0
    created_at = None
    expires_at = None
    content_type = file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

    try:
        # Stream to disk in bounded chunks; do not load the whole upload into RAM.
        with destination.open("xb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB."
                    )
                output.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="Empty files are not allowed.")

        # The 10-minute lifetime starts after the upload has completed.
        created_at = time.time()
        expires_at = created_at + TTL_SECONDS
        with connection() as conn:
            conn.execute(
                """INSERT INTO files
                   (token, original_name, stored_name, size_bytes, content_type, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (token, original_name, stored_name, size, content_type, created_at, expires_at)
            )
    except Exception:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove incomplete upload")
        raise
    finally:
        await file.close()

    # Prefer a configured public URL behind a reverse proxy. Otherwise use request origin.
    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    share_url = f"{base_url}/s/{token}"
    return {
        "token": token,
        "filename": original_name,
        "size_bytes": size,
        "share_url": share_url,
        "qr_url": f"/api/qr/{token}",
        "expires_at": expires_at,
        "ttl_seconds": TTL_SECONDS,
    }


@app.get("/api/qr/{token}")
async def qr_code(token: str):
    get_share(token)  # QR endpoint also expires server-side.
    base_url = PUBLIC_BASE_URL
    if not base_url:
        # Use configured public base URL in production to avoid proxy-host ambiguity.
        raise HTTPException(
            status_code=503,
            detail="Set PUBLIC_BASE_URL to your public HTTPS origin to enable QR generation."
        )
    share_url = f"{base_url}/s/{token}"
    image = qrcode.make(share_url)
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/s/{token}", response_class=HTMLResponse)
async def share_page(request: Request, token: str):
    row = get_share(token)

    return templates.TemplateResponse(
        request=request,
        name="download.html",
        context={
            "token": token,
            "filename": row["original_name"],
            "size_bytes": row["size_bytes"],
            "expires_at_ms": int(row["expires_at"] * 1000),
            "qr_url": f"/api/qr/{token}",
        },
    )

@app.get("/api/file/{token}")
async def download_file(token: str):
    row = get_share(token)
    path = UPLOAD_DIR / row["stored_name"]
    if not path.is_file():
        with connection() as conn:
            conn.execute("DELETE FROM files WHERE token = ?", (token,))
        raise HTTPException(status_code=410, detail="The file is no longer available.")

    # Starlette streams the file and safely handles Content-Disposition.
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=row["original_name"],
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/status/{token}")
async def share_status(token: str):
    row = get_share(token)
    remaining = max(0, int(row["expires_at"] - time.time()))
    return {
        "filename": row["original_name"],
        "size_bytes": row["size_bytes"],
        "expires_at": row["expires_at"],
        "remaining_seconds": remaining,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    template_name = (
        "download.html"
        if request.url.path.startswith("/s/")
        else "index.html"
    )

    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "error": exc.detail,
            "max_file_mb": MAX_FILE_SIZE // (1024 * 1024),
        },
        status_code=exc.status_code,
    )