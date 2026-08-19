# pc/app/net/net_discovery.py
import socket
import threading
from typing import Optional

DISCOVERY_PORT = 37020


def _get_local_ip_for_peer(peer_ip: str) -> str:
    """Infer local outbound IP for the peer's subnet (no actual packets sent)."""
    tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        tmp.connect((peer_ip, 9))
        return tmp.getsockname()[0]
    finally:
        tmp.close()


def start_discovery_responder(
    http_port: int,
    daemon: bool = True,
    stop_event: Optional[threading.Event] = None,
    discovery_port: int = DISCOVERY_PORT,
    logger=None,
) -> threading.Thread:
    """
    Start a UDP discovery responder:
      - Phone sends: FIND_PHONECAM_SERVER
      - PC replies:  PHONECAM_SERVER http://<ip>:<port>

    The optional stop_event lets the responder exit during a graceful server
    shutdown. discovery_port is configurable to keep the protocol testable
    without changing the production default.
    """
    def run():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(0.5)
            s.bind(("0.0.0.0", discovery_port))
            if logger:
                logger.info(f"discovery responder listening on UDP {discovery_port}")

            while stop_event is None or not stop_event.is_set():
                try:
                    data, addr = s.recvfrom(1024)
                except socket.timeout:
                    continue

                msg = data.decode("utf-8", errors="ignore").strip()
                if msg == "FIND_PHONECAM_SERVER":
                    try:
                        ip = _get_local_ip_for_peer(addr[0])
                        reply = f"PHONECAM_SERVER http://{ip}:{http_port}"
                        s.sendto(reply.encode("utf-8"), addr)
                        if logger:
                            logger.info(f"discovery response sent to {addr[0]}:{addr[1]} -> {reply}")
                    except OSError as e:
                        if logger:
                            logger.warning(f"discovery response failed for {addr[0]}: {e}")
        except OSError as e:
            if stop_event is None or not stop_event.is_set():
                if logger:
                    logger.error(f"discovery responder failed: {e}")
        finally:
            s.close()

    t = threading.Thread(target=run, daemon=daemon, name="discovery-responder")
    t.start()
    return t
