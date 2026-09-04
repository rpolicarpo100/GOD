from __future__ import annotations

import threading
from typing import Any, Callable

from .util import now_iso, uid

Listener = Callable[[str, dict], None]


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[Listener] = []
        self.history: list[dict] = []

    def subscribe(self, fn: Listener) -> Callable[[], None]:
        with self._lock:
            self._subs.append(fn)

        def unsub() -> None:
            with self._lock:
                try:
                    self._subs.remove(fn)
                except ValueError:
                    pass

        return unsub

    def publish(self, kind: str, payload: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for fn in subs:
            try:
                fn(kind, payload)
            except Exception:
                pass

    def emit(self, name: str, level: str, msg: str, **extra: Any) -> dict:
        ev = {"id": uid("ev"), "name": name, "level": level, "msg": msg, "ts": now_iso(), **extra}
        with self._lock:
            self.history.insert(0, ev)
            self.history = self.history[:300]
        try:
            from .store import store

            store.save_event(ev)
        except Exception:
            pass
        self.publish("event", ev)
        return ev


bus = EventBus()
