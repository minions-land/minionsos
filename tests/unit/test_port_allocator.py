"""Unit tests for minions.state.port_allocator (PortAllocator).

Tests: bind-probe in 37596-37999, skip retired ports.
"""

from __future__ import annotations

import socket

import pytest

port_allocator = pytest.importorskip("minions.state.port_allocator")
PortAllocator = port_allocator.PortAllocator

PORT_MIN = 37596
PORT_MAX = 37999


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def allocator() -> PortAllocator:
    return PortAllocator(port_min=PORT_MIN, port_max=PORT_MAX)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _bind_port(port: int) -> socket.socket:
    """Bind a real socket to a port so the allocator sees it as in-use.

    We deliberately do NOT set ``SO_REUSEADDR``: on Linux that option lets the
    allocator's own bind-probe succeed on the same port and incorrectly
    conclude the port is free, which breaks these tests in CI.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def _reserve_free_port() -> tuple[socket.socket, int]:
    """Bind port 0 so the OS hands us a currently-free ephemeral port.

    Returns the still-listening socket plus its port number. Using an OS-
    assigned port keeps these tests independent of whatever happens to be
    running on the hard-coded 37596 on a dev machine (e.g. a live
    MinionsOS project or VS Code).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRangeConstraint:
    def test_allocated_port_in_range(self, allocator: PortAllocator) -> None:
        port = allocator.allocate(retired_ports=set())
        assert PORT_MIN <= port <= PORT_MAX

    def test_raises_when_range_exhausted(self) -> None:
        # Reserve a currently-free OS-assigned port and build a tiny
        # 1-port range around it so nothing in the range is free.
        sock, busy_port = _reserve_free_port()
        try:
            tiny = PortAllocator(port_min=busy_port, port_max=busy_port)
            with pytest.raises(Exception):
                tiny.allocate(retired_ports=set())
        finally:
            sock.close()


class TestBindProbe:
    def test_skips_bound_port(self) -> None:
        """Allocator must skip a port that is already bound."""
        # Reserve an OS-assigned free port, then build a 2-port range
        # whose first port is that (now-bound) port. Avoids colliding
        # with real processes (e.g. a live project on 37596).
        sock, busy_port = _reserve_free_port()
        try:
            alloc = PortAllocator(port_min=busy_port, port_max=busy_port + 1)
            port = alloc.allocate(retired_ports=set())
            assert port != busy_port
            assert busy_port < port <= busy_port + 1
        finally:
            sock.close()

    def test_returns_free_port(self, allocator: PortAllocator) -> None:
        port = allocator.allocate(retired_ports=set())
        # Verify the returned port is actually bindable (i.e., was free).
        sock = _bind_port(port)
        sock.close()


class TestRetiredPorts:
    def test_skips_retired_port(self, allocator: PortAllocator) -> None:
        retired = {PORT_MIN}
        port = allocator.allocate(retired_ports=retired)
        assert port != PORT_MIN

    def test_skips_multiple_retired_ports(self, allocator: PortAllocator) -> None:
        # Retire the first 10 ports in range.
        retired = set(range(PORT_MIN, PORT_MIN + 10))
        port = allocator.allocate(retired_ports=retired)
        assert port not in retired
        assert PORT_MIN + 10 <= port <= PORT_MAX

    def test_raises_when_all_retired(self) -> None:
        tiny = PortAllocator(port_min=PORT_MIN, port_max=PORT_MIN)
        with pytest.raises(Exception):
            tiny.allocate(retired_ports={PORT_MIN})


class TestIdempotency:
    def test_two_allocations_return_different_ports(self, allocator: PortAllocator) -> None:
        """Caller is responsible for tracking used ports, but two sequential
        allocations with the first port excluded should differ."""
        p1 = allocator.allocate(retired_ports=set())
        p2 = allocator.allocate(retired_ports={p1})
        assert p1 != p2
