import asyncio
from typing import Dict, List, Callable, Awaitable
from collections import defaultdict
from src.models.content_state import ContentState
import structlog

logger = structlog.get_logger(__name__)

class EventBus:
    """
    Decoupled event broker allowing plugins and observers to subscribe
    to key lifecycle events of the JobInGen content pipeline.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[ContentState], Awaitable[None]]]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable[[ContentState], Awaitable[None]]):
        """
        Subscribe to a pipeline event.
        
        Args:
            event_name: Name of the event (e.g., 'PlanCreated', 'Delivered')
            callback: Async function taking ContentState as parameter
        """
        self._subscribers[event_name].append(callback)
        logger.info("Event subscribed", pipeline_event=event_name, callback=callback.__name__)

    async def emit(self, event_name: str, state: ContentState):
        """
        Emit a pipeline event to all registered subscribers.
        Subscribers are invoked concurrently, and exceptions are isolated 
        so subscriber crashes do not fail the core pipeline.
        
        Args:
            event_name: Name of the event being emitted
            state: The current ContentState object
        """
        subscribers = self._subscribers[event_name]
        if not subscribers:
            return

        logger.info("Emitting event", pipeline_event=event_name, subscribers_count=len(subscribers), run_id=state.run_id)

        # Run all subscribers concurrently, catching exceptions to isolate failures
        tasks = [self._safe_invoke(callback, event_name, state) for callback in subscribers]
        await asyncio.gather(*tasks)

    async def _safe_invoke(self, callback: Callable[[ContentState], Awaitable[None]], event_name: str, state: ContentState):
        try:
            await callback(state)
        except Exception as e:
            logger.error(
                "Subscriber failed",
                pipeline_event=event_name,
                callback=callback.__name__,
                error=str(e),
                run_id=state.run_id,
                exc_info=True
            )
