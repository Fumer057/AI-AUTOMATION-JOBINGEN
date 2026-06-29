import httpx
import structlog
from typing import Dict, Any, List
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)

class InstagramClient:
    def __init__(self, access_token: str, account_id: str):
        self.access_token = access_token
        self.account_id = account_id
        self.base_url = "https://graph.facebook.com/v19.0"

    async def get_recent_posts_metrics(self) -> List[Dict[str, Any]]:
        """
        Fetch media metrics for recent Instagram posts via Graph API.
        Returns a list of standardized metric dictionaries.
        """
        if not self.access_token or not self.account_id:
            raise ValueError("Instagram API credentials (IG_ACCESS_TOKEN or IG_USER_ID) not configured.")

        logger.info("InstagramClient: Fetching recent post metrics", account_id=self.account_id)
        
        async with httpx.AsyncClient() as client:
            media_url = f"{self.base_url}/{self.account_id}/media"
            params = {"access_token": self.access_token}
            response = await client.get(media_url, params=params)
            response.raise_for_status()
            
            media_data = response.json().get("data", [])
            results = []
            
            for media in media_data[:5]:
                media_id = media["id"]
                fields_url = f"{self.base_url}/{media_id}"
                fields_params = {
                    "fields": "id,timestamp,like_count,comments_count",
                    "access_token": self.access_token
                }
                f_resp = await client.get(fields_url, params=fields_params)
                f_resp.raise_for_status()
                f_data = f_resp.json()
                
                try:
                    insights_url = f"{self.base_url}/{media_id}/insights"
                    insights_params = {
                        "metric": "impressions,reach",
                        "access_token": self.access_token
                    }
                    i_resp = await client.get(insights_url, params=insights_params)
                    i_resp.raise_for_status()
                    i_data = i_resp.json().get("data", [])
                    insights_dict = {item["name"]: item["values"][0]["value"] for item in i_data}
                except Exception as e:
                    logger.warning("Failed to fetch insights for media", media_id=media_id, error=str(e))
                    insights_dict = {"impressions": 0, "reach": 0}
                
                results.append({
                    "platform_post_id": media_id,
                    "impressions": insights_dict.get("impressions", 0),
                    "likes": f_data.get("like_count", 0),
                    "comments": f_data.get("comments_count", 0),
                    "shares": 0,  # IG Graph API doesn't support shares easily
                    "timestamp": f_data.get("timestamp")
                })
            
            return results
