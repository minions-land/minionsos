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
    """Bind a real socket to a port so the allocator sees it as in-use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    return sock


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRangeConstraint:
    def test_allocated_port_in_range(self, allocator: PortAllocator) -> None:
        port = allocator.allocate(retired_ports=set())
        assert PORT_MIN <= port <= PORT_MAX

    def test_raises_when_range_exhausted(self) -> None:
        # Use a tiny range of 1 port and bind it so nothing is free.
        tiny = PortAllocator(port_min=PORT_MIN, port_max=PORT_MIN)
        sock = _bind_port(PORT_MIN)
        try:
            with pytest.raises(Exception):
                tiny.allocate(retired_ports=set())
        finally:
            sock.close()


class TestBindProbe:
    def test_skips_bound_port(self, allocator: PortAllocator) -> None:
        """Allocator must skip a port that is already bound."""
        # Bind the first port in range so allocator must skip it.
        sock = _bind_port(PORT_MIN)
        try:
            port = allocator.allocate(retired_ports=set())
            assert port != PORT_MIN
            assert PORT_MIN < port <= PORT_MAX
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
