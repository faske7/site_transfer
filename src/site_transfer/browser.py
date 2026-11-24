"""Public-address proxy and bounded Chromium session for authorized references."""
import http.client
import ipaddress
import select
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def origin(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("Expected public HTTP(S) URL without credentials")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port != (443 if parsed.scheme == "https" else 80):
        raise ValueError("Only default HTTP(S) ports are allowed")
    return parsed.scheme, parsed.hostname.lower(), port


def public_addresses(host, port):
    if host.lower().rstrip(".") in {"localhost", "host.docker.internal", "gateway.docker.internal"}:
        raise ValueError("Local host denied")
    addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast for a in addresses):
        raise ValueError("Non-public destination denied")
    return addresses


def public_url(url):
    scheme, host, port = origin(url)
    public_addresses(host, port)
    return scheme, host, port


class PublicProxy(BaseHTTPRequestHandler):
    """Resolve once, connect to the checked IP, and never follow redirects itself."""
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        upstream = None
        try:
            parsed = urlsplit("https://" + self.path)
            if parsed.port != 443 or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("CONNECT restricted to port 443")
            _, host, port = origin("https://" + self.path)
            address = public_addresses(host, port)[0]
            upstream = socket.create_connection((address, port), timeout=10)
        except (OSError, ValueError):
            self.send_error(403, "Destination denied or unavailable")
            return
        try:
            self.send_response(200, "Connection established")
            self.end_headers()
            self.wfile.flush()
            peers = [self.connection, upstream]
            while True:
                readable, _, _ = select.select(peers, [], [], 30)
                if not readable:
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except OSError:
            pass
        finally:
            upstream.close()

    def do_GET(self):
        conn = None
        started = False
        try:
            scheme, host, port = public_url(self.path)
            if scheme != "http":
                raise ValueError("Expected HTTP proxy request")
            parsed = urlsplit(self.path)
            conn = http.client.HTTPConnection(public_addresses(host, port)[0], port, timeout=15)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            headers = {k: v for k, v in self.headers.items() if k.lower() not in {
                "host", "connection", "proxy-connection", "proxy-authorization", "transfer-encoding", "content-length", "upgrade"
            }}
            headers["Host"] = parsed.netloc
            conn.request(self.command, target, headers=headers)
            response = conn.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {"connection", "transfer-encoding", "keep-alive", "upgrade", "proxy-authenticate"}:
                    self.send_header(key, value)
            self.end_headers()
            started = True
            if self.command != "HEAD":
                while data := response.read(65536):
                    self.wfile.write(data)
        except (OSError, ValueError, http.client.HTTPException):
            if not started:
                self.send_error(403, "Destination denied or unavailable")
        finally:
            if conn:
                conn.close()

    do_HEAD = do_GET


@contextmanager
def chromium():
    from playwright.sync_api import sync_playwright
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), PublicProxy)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                proxy={"server": f"http://127.0.0.1:{proxy.server_port}", "bypass": "<-loopback>"},
                args=["--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
            )
            try:
                yield browser
            finally:
                browser.close()
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=2)


def context_for(browser, viewport, source_origin):
    context = browser.new_context(
        viewport={"width": viewport["width"], "height": viewport["height"]},
        device_scale_factor=1, is_mobile=viewport["width"] < 600,
        has_touch=viewport["width"] < 600, service_workers="block", accept_downloads=False,
    )
    def guard(route):
        request = route.request
        try:
            destination = origin(request.url)
            allowed = request.method in {"GET", "HEAD"} and (
                not request.is_navigation_request() or destination == source_origin)
        except ValueError:
            allowed = False
        if allowed:
            route.continue_()
        else:
            route.abort()
    context.route("**/*", guard)
    context.route_web_socket("**/*", lambda ws: ws.close())
    return context
