import asyncio
import sys
from datetime import date
from src.models.content_state import ContentState, PipelineStatus
from src.foundation.event_bus import EventBus

# Setup simple structured logging console output for verification
import structlog
structlog.configure(
    processors=[structlog.processors.JSONRenderer()]
)

async def test_subscriber_success(state: ContentState):
    print(f"[Sub1] Received state for date: {state.date}, status: {state.status}")
    await asyncio.sleep(0.1)
    print("[Sub1] Finished processing successfully")

async def test_subscriber_fail(state: ContentState):
    print("[Sub2] Processing but going to fail...")
    raise ValueError("Sample error in plugin handler!")

async def main():
    print("Initializing Event Bus...")
    bus = EventBus()
    
    # Register subscribers
    bus.subscribe("PlanCreated", test_subscriber_success)
    bus.subscribe("PlanCreated", test_subscriber_fail)
    
    state = ContentState(date=date.today())
    state.status = PipelineStatus.PLANNED
    
    print("\nEmitting 'PlanCreated' event...")
    await bus.emit("PlanCreated", state)
    
    print("\nEvent emission complete. Pipeline survived the crash in Sub2.")
    print("SUCCESS: Event Bus behaves correctly!")

if __name__ == "__main__":
    asyncio.run(main())
