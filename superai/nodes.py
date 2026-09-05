"""Node Registry — capability-based device architecture.

Each node declares its capabilities:
- audio.input (microphone)
- audio.output (speaker)
- camera
- display
- network
- context (location, sensors)
- compute (CPU/GPU)
- storage

Future devices (Samsung A23, etc.) will register here.
Currently only local node exists.
"""
from __future__ import annotations

import threading
from typing import Any

from .util import now_iso

# Node capability types
CAPABILITIES = [
    "audio.input",
    "audio.output",
    "camera",
    "display",
    "network",
    "context",
    "compute.cpu",
    "compute.gpu",
    "storage",
]

class NodeRegistry:
    """Registry of connected nodes with capabilities."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._nodes: dict[str, dict] = {}
    
    def register(self, node_id: str, name: str, location: str,
                 capabilities: list[str], **meta: Any) -> dict:
        """Register a node with its capabilities."""
        # Validate capabilities
        invalid = [c for c in capabilities if c not in CAPABILITIES]
        if invalid:
            return {"ok": False, "error": f"Unknown capabilities: {invalid}"}
        
        with self._lock:
            self._nodes[node_id] = {
                "id": node_id,
                "name": name,
                "location": location,
                "capabilities": capabilities,
                "status": "online",
                "last_seen": now_iso(),
                "meta": meta,
            }
        return {"ok": True, "node": self._nodes[node_id]}
    
    def unregister(self, node_id: str) -> dict:
        """Remove a node."""
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                return {"ok": True}
        return {"ok": False, "error": "node not found"}
    
    def heartbeat(self, node_id: str, **status: Any) -> dict:
        """Update node heartbeat."""
        with self._lock:
            if node_id not in self._nodes:
                return {"ok": False, "error": "node not found"}
            self._nodes[node_id]["last_seen"] = now_iso()
            self._nodes[node_id]["status"] = "online"
            self._nodes[node_id]["meta"].update(status)
        return {"ok": True}
    
    def get(self, node_id: str) -> dict | None:
        """Get node info."""
        with self._lock:
            return self._nodes.get(node_id)
    
    def list_nodes(self, capability: str | None = None) -> list[dict]:
        """List nodes, optionally filtered by capability."""
        with self._lock:
            nodes = list(self._nodes.values())
        if capability:
            nodes = [n for n in nodes if capability in n.get("capabilities", [])]
        return nodes
    
    def has_capability(self, capability: str) -> bool:
        """Check if any node has the given capability."""
        with self._lock:
            return any(capability in n.get("capabilities", []) for n in self._nodes.values())
    
    def get_capable_nodes(self, capability: str) -> list[dict]:
        """Get all nodes with a specific capability."""
        with self._lock:
            return [n for n in self._nodes.values() if capability in n.get("capabilities", [])]
    
    def status(self) -> dict:
        """Get registry status."""
        with self._lock:
            nodes = list(self._nodes.values())
        return {
            "kind": "MEASURED",
            "n_nodes": len(nodes),
            "nodes": nodes,
            "available_capabilities": CAPABILITIES,
            "ts": now_iso(),
        }


# Global registry
registry = NodeRegistry()


# Register local node on import
registry.register(
    "local",
    "Local Server",
    "sandbox",
    ["compute.cpu", "network", "storage"],
    os_type="linux",
    note="Primary node — GOD runs here",
)
