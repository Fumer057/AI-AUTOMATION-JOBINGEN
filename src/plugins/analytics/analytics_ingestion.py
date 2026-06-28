import structlog
from typing import Dict, Any, Callable
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.data.operational_store import OperationalStore
from src.plugins.analytics.linkedin_client import LinkedInClient
from src.plugins.analytics.instagram_client import InstagramClient

logger = structlog.get_logger(__name__)

class AnalyticsIngestionPlugin(BasePlugin):
    """
    Ingests post engagement metrics from social platforms (LinkedIn, Instagram) 
    and stores them in the Operational Store for the learning loop.
    """
    def __init__(self, config: AppConfig):
        self.config = config
        self.ops_store = OperationalStore(config)
        
        # Initialize clients with auth from config
        self.linkedin = LinkedInClient(
            access_token=config.social_auth.linkedin.access_token,
            organization_id=config.social_auth.linkedin.organization_id
        )
        self.instagram = InstagramClient(
            access_token=config.social_auth.instagram.access_token,
            account_id=config.social_auth.instagram.account_id
        )

    def name(self) -> str:
        return "analytics_ingestion"

    def subscriptions(self) -> Dict[str, Callable]:
        return {"AnalyticsTriggered": self.on_analytics_triggered}

    async def on_analytics_triggered(self, state: Any):
        logger.info("AnalyticsIngestionPlugin: Fetching cross-platform metrics...")
        
        # 1. Fetch LinkedIn
        li_metrics = await self.linkedin.get_recent_posts_metrics()
        for metric in li_metrics:
            # We map the external platform ID back to our internal run_id.
            # For this mock, we pretend we know the mapping.
            # In a real app, output_queue saves the platform ID mapped to run_id.
            run_id = f"mock_run_{metric['platform_post_id'][-3:]}"
            
            # Simple engagement rate calculation if not provided by API
            if "engagement_rate" not in metric and metric.get("impressions", 0) > 0:
                metric["engagement_rate"] = (metric["likes"] + metric["comments"] + metric["shares"]) / metric["impressions"]
            
            await self.ops_store.upsert_post_metrics(run_id, "linkedin", metric)
            
        # 2. Fetch Instagram
        ig_metrics = await self.instagram.get_recent_posts_metrics()
        for metric in ig_metrics:
            run_id = f"mock_run_{metric['platform_post_id'][-3:]}"
            
            if "engagement_rate" not in metric and metric.get("impressions", 0) > 0:
                metric["engagement_rate"] = (metric["likes"] + metric["comments"] + metric["shares"]) / metric["impressions"]
                
            await self.ops_store.upsert_post_metrics(run_id, "instagram", metric)
            
        logger.info("AnalyticsIngestionPlugin: Completed ingestion", 
                    linkedin_posts=len(li_metrics), instagram_posts=len(ig_metrics))
