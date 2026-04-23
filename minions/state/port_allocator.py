"""Port allocator: bind-probe based free-port discovery."""
from __future__ import annotations

import socket

from minions.errors import PortError


class PortAllocator:
    """Find a free TCP port in [port_min, port_max] via bind-probe."""

    def __init__(self, port_min: int = 37596, port_max: int = 37999) -> None:
        self.port_min = port_min
        self.port_max = port_max

    def _is_free(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

    def allocate(self, retired_ports: set[int]) -> int:
        """Return the first free port not in *retired_ports*.

        Raises ``PortError`` if no free port is available.
        """
        for port in range(self.port_min, self.port_max + 1):
            if port in retired_ports:
                continue
            if self._is_free(port):
                return port
        raise PortError(f"No free port in range {self.port_min}–{self.port_max}.")
