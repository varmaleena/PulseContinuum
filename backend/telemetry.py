import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Telemetry:
    def __init__(self) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=1000)
        self.subscribers: set[asyncio.Queue] = set()
        self.sequence = 0
        self.loop: asyncio.AbstractEventLoop | None = None

    def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        self.sequence += 1
        item = {'id': self.sequence, 'timestamp': now(), **event}
        self.events.append(item)
        logging.getLogger('pulse.telemetry').info(json.dumps(item, default=str))
        def publish():
            for queue in tuple(self.subscribers):
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(item)
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(publish)
        else:
            publish()
        return item


telemetry = Telemetry()
