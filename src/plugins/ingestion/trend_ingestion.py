import structlog
import httpx
import xml.etree.ElementTree as ET
import hashlib
from datetime import datetime
from typing import List, Any
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.data.knowledge_store import KnowledgeStore

logger = structlog.get_logger(__name__)

class TrendIngestionPlugin(BasePlugin):
    """
    Ingests trending topics into the Knowledge Store via RSS.
    """
    def __init__(self, config: AppConfig):
        self.config = config
        self.knowledge_store = KnowledgeStore(config)
        # Using a reliable RSS feed for jobs/tech as a default
        self.rss_url = "https://news.ycombinator.com/rss"

    def name(self) -> str:
        return "trend_ingestion"

    def subscriptions(self) -> dict[str, Any]:
        return {"IngestionTriggered": self.on_ingestion}

    async def on_ingestion(self, state: Any):
        logger.info("TrendIngestionPlugin: Fetching trends...", url=self.rss_url)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.rss_url, timeout=10.0)
                response.raise_for_status()
                
            root = ET.fromstring(response.text)
            count = 0
            # Parse standard RSS 2.0 format
            for item in root.findall(".//item")[:10]: # Limit to top 10 trends
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                
                if not title:
                    continue
                    
                # Generate a stable ID for the topic
                topic_id = f"trend_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                
                topic_data = {
                    "topic_id": topic_id,
                    "pillar": "Educate", # Defaulting to Educate for trends
                    "topic_title": title,
                    "topic_context": f"Trend source: {link}",
                    "suggested_template": "insight_card",
                    "source": "rss_ingestion",
                    "active": 1,
                    "ingested_at": datetime.utcnow().isoformat()
                }
                
                await self.knowledge_store.upsert_topic(topic_data)
                count += 1
                
            logger.info("TrendIngestionPlugin: Ingested trends", count=count)
        except Exception as e:
            logger.error("TrendIngestionPlugin: Failed to fetch trends", error=str(e))
