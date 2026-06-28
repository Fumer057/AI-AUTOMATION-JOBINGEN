import structlog
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Any
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.data.knowledge_store import KnowledgeStore

logger = structlog.get_logger(__name__)

class JobIngestionPlugin(BasePlugin):
    """
    Ingests job listings into the Knowledge Store from a CSV inbox.
    """
    def __init__(self, config: AppConfig):
        self.config = config
        self.knowledge_store = KnowledgeStore(config)
        self.inbox_file = Path("data/inbox/jobs.csv")

    def name(self) -> str:
        return "job_ingestion"

    def subscriptions(self) -> dict[str, Any]:
        return {"IngestionTriggered": self.on_ingestion}

    async def on_ingestion(self, state: Any):
        logger.info("JobIngestionPlugin: Checking for new jobs...")
        if not self.inbox_file.exists():
            logger.info("JobIngestionPlugin: No jobs.csv found in data/inbox/")
            return
            
        with open(self.inbox_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                job_data = {
                    "job_id": row.get("job_id", "").strip(),
                    "company": row.get("company", "").strip(),
                    "role": row.get("role", "").strip(),
                    "location": row.get("location", "").strip(),
                    "link": row.get("link", "").strip(),
                    "posted_date": row.get("posted_date", "").strip(),
                    "featured": int(row.get("featured", 0)),
                    "source": "csv_inbox",
                    "active": 1,
                    "ingested_at": datetime.utcnow().isoformat()
                }
                
                if not job_data["job_id"]:
                    continue
                    
                await self.knowledge_store.upsert_job(job_data)
                count += 1
                
        logger.info("JobIngestionPlugin: Ingested jobs", count=count)
