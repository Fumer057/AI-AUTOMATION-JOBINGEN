import asyncio
import structlog
from src.utils.config_loader import load_config
from src.pipeline.orchestrator import Orchestrator
from src.data.knowledge_store import KnowledgeStore

async def test_ingestion():
    # Orchestrator takes config_path as string
    orchestrator = Orchestrator("config.yaml")
    
    # Initialize DB schema
    await orchestrator.knowledge.initialize()
    
    from src.models.content_state import ContentState
    state = ContentState(date="2026-06-28")
    # Trigger Ingestion
    print("--- Triggering Ingestion ---")
    await orchestrator.bus.emit("IngestionTriggered", state)


    
    # Verify jobs
    print("--- Fetching Jobs ---")
    jobs = await orchestrator.knowledge.get_featured_jobs()
    for job in jobs:
        print(f"Job: {job['job_id']} | {job['role']} at {job['company']}")
        
    # Verify topics (Trends are default Educate pillar)
    print("--- Fetching Trending Topics ---")
    topics = await orchestrator.knowledge.get_available_topics("Educate")
    for t in topics:
        if t["source"] == "rss_ingestion":
            print(f"Trend: {t['topic_title']} (ID: {t['topic_id']})")
            
if __name__ == "__main__":
    asyncio.run(test_ingestion())
