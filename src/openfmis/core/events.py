"""Async in-process event bus.

Usage::

    from openfmis.core.events import event_bus

    # Subscribe
    @event_bus.on("plugin.registered")
    async def handle_registered(payload: dict) -> None:
        ...

    # Emit (fire-and-forget, exceptions are logged)
    await event_bus.emit("plugin.registered", {"slug": "my-plugin"})
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def on(self, event: str) -> Callable[[Handler], Handler]:
        """Decorator to register an async handler for *event*."""

        def decorator(fn: Handler) -> Handler:
            self._handlers[event].append(fn)
            return fn

        return decorator

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        self._handlers[event] = [h for h in self._handlers[event] if h is not handler]

    async def emit(self, event: str, payload: dict) -> None:
        """Call all handlers registered for *event* concurrently."""
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            return
        results = await asyncio.gather(*(h(payload) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.exception("Event handler error for %r: %s", event, result)


event_bus = EventBus()
