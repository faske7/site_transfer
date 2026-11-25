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
    if not isinstance(url, str) or "\\" in url or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError("Invalid URL characters")
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("Expected public HTTP(S) URL without credentials")
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    if port != (443 if parsed.scheme == "https" else 80):
        raise ValueError("Only default HTTP(S) ports are allowed")
    return parsed.scheme, parsed.hostname.lower(), port


# Transition mechanisms can encapsulate a private IPv4 destination. Reject them
# rather than trusting the outer IPv6 address's global flag.
_DENIED_V6 = tuple(ipaddress.ip_network(n) for n in (
    "::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48", "2001::/32", "2002::/16",
))


def is_public_address(value):
    try:
        if "%" in value:
            return False
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if address.version == 6:
        return not address.is_site_local and not any(address in net for net in _DENIED_V6)
    return True


def public_addresses(host, port):
    if host.lower().rstrip(".") in {"localhost", "host.docker.internal", "gateway.docker.internal"}:
        raise ValueError("Local host denied")
    addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not is_public_address(a) for a in addresses):
        raise ValueError("Non-public destination denied")
    return addresses


def public_url(url):
    scheme, host, port = origin(url)
    public_addresses(host, port)
    return scheme, host, port


def forwarded_headers(headers):
    # RFC hop-by-hop header names may also be nominated by Connection.
    nominated = {part.strip().lower() for value in headers.get_all("Connection", [])
                 for part in value.split(",")}
    excluded = nominated | {"host", "connection", "proxy-connection", "proxy-authorization",
        "transfer-encoding", "content-length", "upgrade", "keep-alive", "te", "trailer",
        "expect"}
    return {k: v for k, v in headers.items() if k.lower() not in excluded}


class PublicProxy(BaseHTTPRequestHandler):
    """Resolve once, connect to the checked IP, and never follow redirects itself."""
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        upstream = None
        try:
            parsed = urlsplit("https://" + self.path)
            if ("\\" in self.path or any(ord(c) < 33 or ord(c) == 127 for c in self.path)
                    or parsed.port != 443 or parsed.path or parsed.query or parsed.fragment):
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
            scheme, host, port = origin(self.path)
            if scheme != "http":
                raise ValueError("Expected HTTP proxy request")
            parsed = urlsplit(self.path)
            address = public_addresses(host, port)[0]
            conn = http.client.HTTPConnection(address, port, timeout=15)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            headers = forwarded_headers(self.headers)
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
