"""Regression tests for the bounded public proxy, API and desktop bundle policy."""
from email.message import Message
import importlib.util
from pathlib import Path
import socket

import pytest

from site_transfer.browser import origin, public_addresses, is_public_address, forwarded_headers


@pytest.mark.parametrize("value", ["::ffff:8.8.8.8", "64:ff9b::a00:1", "64:ff9b:1::1",
                                    "2002:0808:0808::1", "2001:0:4136:e378::1",
                                    "fec0::1", "fe80::1%eth0", "not-an-ip"])
def test_transition_and_special_addresses_denied(value):
    assert not is_public_address(value)


@pytest.mark.parametrize("value", ["8.8.8.8", "2606:4700:4700::1111"])
def test_normal_public_addresses(value):
    assert is_public_address(value)


def test_mixed_dns_denied(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (0,0,0,"",("8.8.8.8",443)), (0,0,0,"",("10.0.0.1",443))])
    with pytest.raises(ValueError):
        public_addresses("example.com",443)


@pytest.mark.parametrize("url", ["https://example.com:0/", "https://example.com\\@other.example/",
                                 "https://example.com/\n", "https://user:pass@example.com/"])
def test_ambiguous_url_rejected(url):
    with pytest.raises(ValueError):
        origin(url)


def test_hop_by_hop_headers_removed():
    headers=Message()
    headers["Connection"]="X-Internal, keep-alive"
    headers["X-Internal"]="private"
    headers["Proxy-Authorization"]="secret"
    headers["Host"]="wrong.example"
    headers["Accept"]="text/html"
    assert forwarded_headers(headers)=={"Accept":"text/html"}


def test_cross_origin_read_denied():
    pytest.importorskip("fastapi")
    pytest.importorskip("celery")
    pytest.importorskip("psycopg")
    from fastapi.testclient import TestClient
    from site_transfer.server.api import app
    client=TestClient(app,base_url="http://localhost")
    assert client.get("/health/live",headers={"Sec-Fetch-Site":"cross-site"}).status_code==403
    assert client.get("/health/live",headers={"Sec-Fetch-Site":"same-site"}).status_code==403
    assert client.get("/health/live",headers={"Origin":"http://localhost:9999"}).status_code==403
    result=client.get("/health/live",headers={"Sec-Fetch-Site":"same-origin"})
    assert result.status_code==200
    assert result.headers["cache-control"]=="no-store"
    assert result.headers["x-frame-options"]=="DENY"
    assert result.headers["cross-origin-resource-policy"]=="same-origin"


def test_bundle_inputs():
    script=Path(__file__).resolve().parents[1]/"desktop/scripts/check-runtime-inputs.py"
    spec=importlib.util.spec_from_file_location("bundle_inputs",script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check_records(["100644 blob abc\tsrc/site_transfer/cli.py"])
    for record in ["120000 blob abc\tfrontend/link", "160000 commit abc\tfrontend/submodule",
                   "100644 blob abc\tfrontend/.env.local", "100644 blob abc\tsrc/private.pem",
                   "100644 blob abc\tfrontend/node_modules/pkg/index.js"]:
        with pytest.raises(ValueError):
            module.check_records([record])
