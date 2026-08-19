import socket
import threading
import time

from app.net.net_discovery import start_discovery_responder


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_discovery_responder_replies_and_stops():
    discovery_port = _free_udp_port()
    stop_event = threading.Event()
    thread = start_discovery_responder(
        http_port=8000,
        stop_event=stop_event,
        discovery_port=discovery_port,
    )

    reply = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(0.2)
            deadline = time.time() + 2.0
            while time.time() < deadline and reply is None:
                client.sendto(b"FIND_PHONECAM_SERVER", ("127.0.0.1", discovery_port))
                try:
                    data, _ = client.recvfrom(1024)
                    reply = data.decode("utf-8")
                except socket.timeout:
                    continue
    finally:
        stop_event.set()
        thread.join(timeout=2.0)

    assert reply == "PHONECAM_SERVER http://127.0.0.1:8000"
    assert not thread.is_alive()
