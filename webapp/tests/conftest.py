"""Shared fixtures for the web API and browser tests."""

from __future__ import annotations

import threading

import pytest

from webapp.server import LocalServer


@pytest.fixture(scope='module')
def web_server():
    server = LocalServer(('127.0.0.1', 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()
    server.server_close()
