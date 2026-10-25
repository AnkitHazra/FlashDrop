import asyncio
import logging
import os
import time

from app.database import connection
from app.config import CLEANUP_INTERVAL_SECONDS, UPLOAD_DIR

logger = logging.getLogger(__name__)


def cleanup_expired_files():
    now = time.time()
    deleted = 0
    with connection() as conn:
        rows = conn.execute(
            "SELECT token, stored_name FROM files WHERE expires_at <= ?", (now,)
        ).fetchall()

        for row in rows:
            path = UPLOAD_DIR / row["stored_name"]
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not delete expired file %s", row["stored_name"])
                # Keep metadata so a later cleanup attempt can retry.
                continue
            conn.execute("DELETE FROM files WHERE token = ?", (row["token"],))
            deleted += 1

    # Remove orphaned files left by interrupted uploads or crashes.
    try:
        with os.scandir(UPLOAD_DIR) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue
                try:
                    if now - entry.stat(follow_symlinks=False).st_mtime > 3600:
                        # Files are UUID-named and should not live longer than their TTL.
                        # One hour provides a recovery window for interrupted writes.
                        os.unlink(entry.path)
                except OSError:
                    logger.debug("Could not inspect orphan file %s", entry.path)
    except OSError:
        logger.exception("Could not scan upload directory")

    return deleted


async def cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_files)
        except Exception:
            logger.exception("Scheduled cleanup failed")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
