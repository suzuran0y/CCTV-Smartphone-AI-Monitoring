"""Correlate upload stages without logging credentials, addresses or image contents."""
import re
import time
import uuid

from flask import g, request


def install_upload_diagnostics(app, logger):
    # Register before authentication so total time includes its database checks.
    @app.before_request
    def begin_upload():
        if request.path != "/upload" or request.method != "POST":
            return
        supplied = request.headers.get("X-CamFlow-Upload-ID", "")
        g.upload_id = supplied if re.fullmatch(r"[a-f0-9]{12}", supplied) else uuid.uuid4().hex[:12]
        g.upload_started = time.perf_counter()
        g.upload_bytes = 0
        g.upload_read_ms = None
        g.upload_decode_ms = None
        logger.info("upload begin id=%s declared_bytes=%s", g.upload_id, request.content_length)

    @app.after_request
    def finish_upload(response):
        if not hasattr(g, "upload_started"):
            return response
        elapsed = max(0.0, (time.perf_counter() - g.upload_started) * 1000)
        response.headers["X-CamFlow-Upload-ID"] = g.upload_id
        response.headers["X-Sentinel-Upload-Ms"] = f"{elapsed:.1f}"
        logger.info("upload end id=%s status=%d image_bytes=%d total_ms=%.1f read_ms=%s decode_ms=%s",
                    g.upload_id, response.status_code, g.upload_bytes, elapsed,
                    g.upload_read_ms, g.upload_decode_ms)
        return response
