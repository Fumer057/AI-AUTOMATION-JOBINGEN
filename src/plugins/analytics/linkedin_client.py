import httpx
import structlog
from typing import Dict, Any, List
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)

class LinkedInClient:
    def __init__(self, access_token: str, organization_id: str):
        self.access_token = access_token
        self.organization_id = organization_id
        self.base_url = "https://api.linkedin.com/v2"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0"
        }

    async def get_recent_posts_metrics(self) -> List[Dict[str, Any]]:
        """
        Fetch organizational page statistics for recent posts.
        In a real scenario, this queries organizationalEntityShareStatistics.
        Returns a list of standardized metric dictionaries.
        """
        if not self.access_token or not self.organization_id:
            raise ValueError("LinkedIn API credentials (LINKEDIN_ACCESS_TOKEN or LINKEDIN_AUTHOR_URN) not configured.")

        logger.info("LinkedInClient: Fetching recent post metrics", org_id=self.organization_id)
        
        async with httpx.AsyncClient() as client:
            org_urn = f"urn:li:organization:{self.organization_id}" if not self.organization_id.startswith("urn:") else self.organization_id
            url = f"{self.base_url}/organizationalEntityShareStatistics"
            params = {
                "q": "organizationalEntity",
                "organizationalEntity": org_urn
            }
            response = await client.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json().get("elements", [])
            results = []
            for element in data:
                share_urn = element.get("share")
                stats = element.get("totalShareStatistics", {})
                results.append({
                    "platform_post_id": share_urn,
                    "impressions": stats.get("clickCount", 0),
                    "likes": stats.get("likeCount", 0),
                    "comments": stats.get("commentCount", 0),
                    "shares": stats.get("shareCount", 0),
                    "timestamp": datetime.utcnow().isoformat()
                })
            return results
