"""Viewing through two simultaneous HTTP streams must not serialize image uploads."""
import threading
import urllib.request

import cv2
import numpy as np
from werkzeug.serving import make_server


def test_two_live_streams_do_not_block_uploads(system):
    app, auth, _, cfg, frame, *_ = system
    cfg.set_key("ingest_enabled", True)
    paired = auth.pair(auth.pairing_code(), "synthetic-camera")
    server = make_server("127.0.0.1", 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f"http://127.0.0.1:{server.server_port}"
    streams = []
    try:
        for _ in range(2):
            streams.append(client.open(base + "/stream", timeout=3))
        for value in (10, 80, 150):
            ok, jpeg = cv2.imencode(".jpg", np.full((24, 32, 3), value, dtype=np.uint8))
            assert ok
            data = (b'--probe\r\nContent-Disposition: form-data; name="image"; filename="test.jpg"\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n--probe--\r\n')
            request = urllib.request.Request(base + "/upload", data=data, headers={
                "Authorization": "Bearer " + paired["device_token"],
                "Content-Type": "multipart/form-data; boundary=probe",
            })
            with client.open(request, timeout=3) as response:
                assert response.status == 200
                assert response.read() == b"OK"
            assert abs(float(frame.get_copy().mean()) - value) < 2
        # Both original streams remain readable after the uploads.
        for stream in streams:
            assert stream.read(7) == b"--frame"
    finally:
        for stream in streams:
            stream.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
