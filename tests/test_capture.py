import socket

import pytest

from site_transfer.browser import origin, public_addresses
from site_transfer.discovery import normalize, seed_routes


def test_origin_and_routes():
    expected = origin("https://example.com")
    assert normalize("https://example.com/a", "/b?q=2#x", expected) == "https://example.com/b"
    assert normalize("https://example.com", "https://other.example/x", expected) is None
    assert normalize("https://example.com", "javascript:alert(1)", expected) is None
    assert normalize("https://example.com", "https://example.com:8443/a", expected) is None


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1", "192.168.1.2"])
def test_private_dns_denied(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0,0,0,"",(address,443))])
    with pytest.raises(ValueError):
        public_addresses("example.com", 443)


def test_public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0,0,0,"",("8.8.8.8",443))])
    assert public_addresses("example.com",443) == ["8.8.8.8"]


def test_bounded_seeds():
    config = {"source":{"url":"https://example.com","pages":["/","/a","/b","https://other.example"]},
              "discovery":{"max_pages":2}}
    assert seed_routes(config) == (["https://example.com/","https://example.com/a"],2)
