"""Deadline-supervised HTTPS delivery with a single DNS resolution per attempt."""

from __future__ import annotations

import http.client
import ipaddress
import json
import signal
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit


class BlockedDestination(Exception):
    pass


class CertificateError(Exception):
    pass


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        # Exclude mapped, translation and transition ranges.
        return ip in ipaddress.ip_network("2000::/3") and not (ip.sixtofour or ip.teredo)
    return ip not in ipaddress.ip_network("192.0.0.0/24")


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: tuple, family: int, timeout: float) -> None:
        super().__init__(host, port=443, timeout=timeout)
        self._address = address
        self._family = family

    def connect(self) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_default_certs()
        with socket.socket(self._family, socket.SOCK_STREAM) as raw:
            raw.settimeout(self.timeout)
            raw.connect(self._address)
            self.sock = context.wrap_socket(raw, server_hostname=self.host)


def _send(url: str, payload: bytes, event_id: str, timeout: float) -> int:
    target = urlsplit(url)
    host = target.hostname
    answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not answers or any(
        family not in (socket.AF_INET, socket.AF_INET6) or not _public(address[0])
        for family, _, _, _, address in answers
    ):
        raise BlockedDestination
    family, _, _, _, address = answers[0]
    conn = _PinnedConnection(host, address, family, timeout)
    try:
        path = target.path or "/"
        if target.query:
            path += "?" + target.query
        conn.request(
            "POST",
            path,
            body=payload,
            headers={
                "Host": target.netloc,
                "Content-Type": "application/json",
                "Idempotency-Key": event_id,
                "Connection": "close",
            },
        )
        with conn.getresponse() as response:
            return response.status
    finally:
        conn.close()


def supported() -> bool:
    return all(hasattr(signal, name) for name in ("setitimer", "SIGALRM", "pthread_sigmask"))


def _child(timeout: float) -> None:
    """Read secrets from stdin and emit only a status or a fixed error code."""
    url, payload, event_id = json.load(sys.stdin)
    try:
        status = _send(url, payload.encode(), event_id, timeout)
    except BlockedDestination:
        result = "blocked"
    except ssl.SSLCertVerificationError:
        result = "certificate"
    except TimeoutError:
        result = "timeout"
    except (OSError, http.client.HTTPException):
        result = "transport"
    else:
        result = str(status)
    sys.stdout.write(result)


# Arm the orphan watchdog before importing the app package. Use the same
# monotonic deadline in both processes, including interpreter startup.
_CHILD_COMMAND = """
import signal
import sys
import time

remaining = float(sys.argv[1]) - time.monotonic()
if remaining <= 0:
    sys.exit(1)
signal.signal(signal.SIGALRM, signal.SIG_DFL)
signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
signal.setitimer(signal.ITIMER_REAL, remaining)
from subpoena.api.webhook_transport import _child
_child(remaining)
"""


def post(url: str, payload: bytes, event_id: str, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    data = json.dumps([url, payload.decode(), event_id]).encode()
    with subprocess.Popen(
        [sys.executable, "-c", _CHILD_COMMAND, str(deadline)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            out, _ = process.communicate(data, timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise TimeoutError from None
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    if time.monotonic() >= deadline or out == b"timeout" or process.returncode == -signal.SIGALRM:
        raise TimeoutError
    if out == b"blocked":
        raise BlockedDestination
    if out == b"certificate":
        raise CertificateError
    if process.returncode or not out.isdigit():
        raise OSError("Webhook transport failed")
    return int(out)
