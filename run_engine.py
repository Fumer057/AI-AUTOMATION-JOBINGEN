import asyncio
import os
import argparse
import structlog
from datetime import date
from pathlib import Path
from src.pipeline.orchestrator import Orchestrator

# Configure structured logging for console
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=True)
    ]
)

logger = structlog.get_logger(__name__)

async def main():
    parser = argparse.ArgumentParser(description="Run the JobInGen Content Engine End-to-End")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    parser.add_argument("--mock-date", type=str, help="YYYY-MM-DD to mock the run date")
    args = parser.parse_args()
    
    run_date = date.fromisoformat(args.mock_date) if args.mock_date else None
    
    # Verify GEMINI_API_KEY for the core AI Engine (Text generation)
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        logger.warning("No LLM API Key found (GEMINI_API_KEY or OPENAI_API_KEY). The Planner and Copywriter plugins will likely fail unless you are using a local LLM.")
        
    logger.info("Initializing JobInGen Orchestrator...")
    orchestrator = Orchestrator(args.config)
    await orchestrator.initialize()
    
    from src.models.content_state import ContentState
    dummy_state = ContentState(date=run_date or date.today())
    
    logger.info("Triggering Ingestion Plugins...")
    await orchestrator.bus.emit("IngestionTriggered", dummy_state)
    
    logger.info("Starting Main Pipeline Run...")
    try:
        # Run the full pipeline from Plan -> Render -> Publish
        final_state = await orchestrator.run(mock_date=run_date)
        
        logger.info(
            "Engine Run Completed Successfully!",
            run_id=final_state.run_id,
            status=final_state.status.name,
            output_dir=final_state.output_dir
        )
        
    except Exception as e:
        logger.error("Engine Run Failed", error=str(e), exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
