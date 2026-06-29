import asyncio
import os
import argparse
import structlog
from datetime import date
from pathlib import Path
from src.pipeline.orchestrator import Orchestrator
from src.models.content_state import ContentState, ContentPlan, TopicScore

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=True)
    ]
)
logger = structlog.get_logger(__name__)

async def main():
    logger.info("Initializing JobInGen Orchestrator...")
    orchestrator = Orchestrator("config.yaml")
    await orchestrator.initialize()
    
    run_date = date.today()
    state = ContentState(date=run_date)
    
    # MOCK THE PLANNER TO FORCE "FLAGSHIP TRAINING"
    async def mock_create_plan(*args, **kwargs):
        return ContentPlan(
            pillar="Opportunity",
            topic="JobInGen Flagship Training: Full Stack & Data Analytics",
            topic_id="flagship-training",
            audience="Students, freshers, and professionals looking to upskill",
            suggested_cta="Check out the link in the comments to register for the flagship training!",
            assets_needed=[],
            dimensions="1080x1080",
            scoring=TopicScore(total=100.0, pillar_deficit=0, seasonality=0, engagement_history=0, freshness=0, trending=0, campaign_priority=100.0)
        )
    orchestrator.planner.create_plan = mock_create_plan
    
    # ALSO FORCE THE TEMPLATE TO CAROUSEL OR INSIGHT CARD
    # Let's see what templates are available for Opportunity. 
    # By default, template_selector will pick a valid one. Let's just let the pipeline run!
    
    logger.info("Starting Pipeline for Flagship Training...")
    try:
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
