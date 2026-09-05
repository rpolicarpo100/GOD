"""P2.6 — Network Access Control.

Controls:
- Outbound connections (default: blocked)
- Inbound connections (default: localhost only)
- DNS resolution (restricted)
- Port scanning prevention

Principle: localhost by default, LAN only with explicit flag.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
from typing import Any

from .util import now_iso

# ═══════════════════════════════
# NETWORK POLICY
# ═══════════════════════════════

# Always allowed hosts
_ALWAYS_ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
}

# Blocked ports (security)
_BLOCKED_PORTS = {
    22,    # SSH
    23,    # Telnet
    25,    # SMTP (spam)
    445,   # SMB
    3389,  # RDP
   5900,  # VNC
   6379,  # Redis (if external)
   27017, # MongoDB (if external)
}

# Allowed outbound ports
_ALLOWED_OUTBOUND_PORTS = {
    80,    # HTTP
   443,   # HTTPS
   53,    # DNS
   8080,  # Common HTTP alt
}

# Rate limit for connection attempts
_MAX_CONNECTIONS_PER_MINUTE = 30


class NetworkController:
    """Control network access."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._connection_log: list[dict] = []
        self._connection_counts: dict[str, list[float]] = {}
        self._policy = {
            "allow_outbound": False,
            "allow_lan": False,
            "allow_remote": False,
        }
    
    def set_policy(
        self,
        allow_outbound: bool = False,
        allow_lan: bool = False,
        allow_remote: bool = False,
    ):
        """Set network policy."""
        with self._lock:
            self._policy = {
                "allow_outbound": allow_outbound,
                "allow_lan": allow_lan,
                "allow_remote": allow_remote,
            }
    
    def check_connection(
        self,
        host: str,
        port: int,
        direction: str = "outbound",
        reason: str = "",
    ) -> dict:
        """Check if a network connection is allowed."""
        import time
        now = time.time()
        
        # Normalize host
        host_lower = host.lower()
        
        # Always allowed: localhost
        if host_lower in _ALWAYS_ALLOWED_HOSTS:
            return {
                "ok": True,
                "kind": "MEASURED",
                "host": host,
                "port": port,
                "zone": "localhost",
            }
        
        # Check blocked ports
        if port in _BLOCKED_PORTS:
            self._log_connection(host, port, direction, False, "blocked_port")
            return {
                "ok": False,
                "kind": "MEASURED",
                "reason": f"Blocked port: {port}",
            }
        
        # Check if LAN
        is_lan = self._is_lan(host)
        
        if is_lan:
            if not self._policy.get("allow_lan"):
                self._log_connection(host, port, direction, False, "lan_blocked")
                return {
                    "ok": False,
                    "kind": "MEASURED",
                    "reason": "LAN access not enabled (use --lan flag)",
                }
        else:
            # Remote host
            if not self._policy.get("allow_remote"):
                self._log_connection(host, port, direction, False, "remote_blocked")
                return {
                    "ok": False,
                    "kind": "MEASURED",
                    "reason": "Remote access not enabled",
                }
        
        # Check rate limit
        with self._lock:
            key = f"{host}:{port}"
            if key not in self._connection_counts:
                self._connection_counts[key] = []
            
            # Clean old entries
            self._connection_counts[key] = [
                t for t in self._connection_counts[key]
                if now - t <60
            ]
            
            if len(self._connection_counts[key]) >= _MAX_CONNECTIONS_PER_MINUTE:
                self._log_connection(host, port, direction, False, "rate_limited")
                return {
                    "ok": False,
                    "kind": "MEASURED",
                    "reason": f"Rate limit exceeded ({_MAX_CONNECTIONS_PER_MINUTE}/min)",
                }
            
            self._connection_counts[key].append(now)
        
        # Check outbound policy
        if direction == "outbound" and not self._policy.get("allow_outbound"):
            # Check if port is in allowed list
            if port not in _ALLOWED_OUTBOUND_PORTS:
                self._log_connection(host, port, direction, False, "outbound_blocked")
                return {
                    "ok": False,
                    "kind": "MEASURED",
                    "reason": f"Outbound port {port} not in allowed list",
                }
        
        self._log_connection(host, port, direction, True, "allowed")
        return {
            "ok": True,
            "kind": "MEASURED",
            "host": host,
            "port": port,
            "zone": "lan" if is_lan else "remote",
        }
    
    def _is_lan(self, host: str) -> bool:
        """Check if host is on LAN."""
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private
        except ValueError:
            # Hostname — try to resolve
            try:
                resolved = socket.gethostbyname(host)
                ip = ipaddress.ip_address(resolved)
                return ip.is_private
            except Exception:
                return False
    
    def _log_connection(
        self,
        host: str,
        port: int,
        direction: str,
        allowed: bool,
        reason: str,
    ):
        """Log a connection attempt."""
        with self._lock:
            self._connection_log.append({
                "ts": now_iso(),
                "host": host,
                "port": port,
                "direction": direction,
                "allowed": allowed,
                "reason": reason,
            })
            # Keep log size manageable
            if len(self._connection_log) >1000:
                self._connection_log = self._connection_log[-500:]
    
    def get_connection_log(self, limit: int =50) -> list[dict]:
        """Get recent connection log."""
        with self._lock:
            return list(reversed(self._connection_log[-limit:]))
    
    def get_stats(self) -> dict:
        """Get network control statistics."""
        with self._lock:
            total = len(self._connection_log)
            allowed = sum(1 for c in self._connection_log if c["allowed"])
            blocked = total - allowed
            
            return {
                "kind": "MEASURED",
                "policy": self._policy.copy(),
                "total_connections": total,
                "allowed": allowed,
                "blocked": blocked,
                "ts": now_iso(),
            }


# Global controller
_controller = NetworkController()


def get_controller() -> NetworkController:
    """Get the global network controller."""
    return _controller


def check_connection(host: str, port: int, direction: str = "outbound") -> dict:
    """Check if a connection is allowed."""
    return _controller.check_connection(host, port, direction)


def set_network_policy(
    allow_outbound: bool = False,
    allow_lan: bool = False,
    allow_remote: bool = False,
):
    """Set network policy."""
    _controller.set_policy(allow_outbound, allow_lan, allow_remote)


def format_network_check(result: dict) -> str:
    """Format network check for display."""
    if result.get("ok"):
        return f"✓ Allowed: {result.get('host')}:{result.get('port')} ({result.get('zone')})"
    return f"✗ Blocked: {result.get('reason')}"
