"""Exercise the pinned HTTPS transport and the real subprocess supervisor offline."""

import socket
import ssl
import subprocess
import time
from io import BytesIO

import pytest

from subpoena.api import webhook_transport as transport

URL = "https://receiver.example.test/hook?key=synthetic-secret"
PUBLIC = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "::1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::1",
    ],
)
def test_rejects_entire_dns_answer_with_nonpublic_address(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [PUBLIC, (*PUBLIC[:4], (address, 443))]
    )

    def forbidden(*args):
        pytest.fail("blocked DNS answer must prevent any socket connection")

    monkeypatch.setattr(socket, "socket", forbidden)
    with pytest.raises(transport.BlockedDestination):
        transport._send(URL, b"{}", "event", 2.0)


@pytest.mark.parametrize("bad_cert", [False, True])
def test_single_lookup_pinned_tcp_tls_hostname_host_header_and_no_redirect(monkeypatch, bad_cert):
    lookups = []
    connects = []
    writes = []

    def resolve(host, port, *, type):
        lookups.append((host, port, type))
        if len(lookups) > 1:
            return [(*PUBLIC[:4], ("127.0.0.1", 443))]
        return [PUBLIC]

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def settimeout(self, timeout):
            assert timeout == 2.0

        def connect(self, address):
            connects.append(address)

        def sendall(self, data):
            writes.append(data)

        def makefile(self, mode):
            return BytesIO(
                b"HTTP/1.1 307 Temporary Redirect\r\n"
                b"Location: https://elsewhere.example.test/\r\nContent-Length: 0\r\n\r\n"
            )

        def close(self):
            pass

    def make_socket(family, kind):
        assert (family, kind) == (socket.AF_INET, socket.SOCK_STREAM)
        return Socket()

    def wrap(context, raw, *, server_hostname):
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        assert server_hostname == "receiver.example.test"
        if bad_cert:
            raise ssl.SSLCertVerificationError("synthetic hostname mismatch")
        return raw

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.test")
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "socket", make_socket)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap)
    if bad_cert:
        with pytest.raises(ssl.SSLCertVerificationError):
            transport._send(URL, b"{}", "event", 2.0)
        assert writes == []
    else:
        assert transport._send(URL, b"{}", "event", 2.0) == 307
        request = b"".join(writes)
        assert request.startswith(b"POST /hook?key=synthetic-secret HTTP/1.1\r\n")
        assert b"Host: receiver.example.test\r\n" in request
        assert b"Idempotency-Key: event\r\n" in request
        assert request.endswith(b"\r\n\r\n{}")
    assert lookups == [("receiver.example.test", 443, socket.SOCK_STREAM)]
    assert connects == [("8.8.8.8", 443)]


@pytest.mark.parametrize("phase", ["dns", "read"])
def test_total_deadline_kills_and_reaps_stalled_transport(monkeypatch, tmp_path, phase):
    dns = """
import socket

def stalled_dns(*args, **kwargs):
    mark_entered()
    time.sleep(3)
    raise AssertionError("DNS ran past deadline")

socket.getaddrinfo = stalled_dns
"""
    read = """
import http.client
import socket

socket.getaddrinfo = lambda *a, **kw: [(socket.AF_INET, 1, 6, "", ("8.8.8.8", 443))]
from subpoena.api.webhook_transport import _PinnedConnection
_PinnedConnection.request = lambda *a, **kw: None

def trickle(*args):
    mark_entered()
    for _ in range(60):
        time.sleep(0.05)
        # Each read makes progress inside a normal socket timeout.
    raise AssertionError("read ran past deadline")

http.client.HTTPConnection.getresponse = trickle
"""
    marker = tmp_path / "entered"
    mark = f"\ndef mark_entered():\n    open({str(marker)!r}, 'w').close()\n"
    command = transport._CHILD_COMMAND.replace(
        "_child(remaining)", mark + (dns if phase == "dns" else read) + "\n_child(remaining)"
    )
    monkeypatch.setattr(transport, "_CHILD_COMMAND", command)
    processes = []
    popen = subprocess.Popen

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        transport.post(URL, b"{}", "event", 1.2)
    assert time.monotonic() - start < 2
    assert marker.exists()
    assert len(processes) == 1
    assert processes[0].returncode is not None


def test_child_watchdog_exits_without_parent_cancellation(tmp_path):
    import json
    import signal
    import sys

    marker = tmp_path / "waiting"
    command = transport._CHILD_COMMAND.replace(
        "_child(remaining)",
        f"open({str(marker)!r}, 'w').close()\ntime.sleep(10)",
    )
    with subprocess.Popen(
        [sys.executable, "-c", command, str(time.monotonic() + 1.2)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            process.communicate(json.dumps([URL, "{}", "event"]).encode(), timeout=3)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        assert process.returncode == -signal.SIGALRM
        assert marker.exists()
