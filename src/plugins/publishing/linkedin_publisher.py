import structlog
import os
import aiohttp
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentState

logger = structlog.get_logger(__name__)

class LinkedInPublisherPlugin(BasePlugin):
    """
    Publishes rendered images and copy to LinkedIn using the LinkedIn V2 API.
    Supports Dry Run mode if credentials are not provided.
    """
    
    def name(self) -> str:
        return "linkedin_publisher"
        
    def subscriptions(self) -> dict:
        return {"RenderComplete": self.handle_event}

    def __init__(self, config: AppConfig):
        self.config = config
        self.access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        self.author_urn = os.environ.get("LINKEDIN_AUTHOR_URN")  # e.g., urn:li:person:12345
        self.is_dry_run = not (self.access_token and self.author_urn)

    async def handle_event(self, payload: ContentState):
        logger.info("LinkedInPublisherPlugin: Received RenderComplete", run_id=payload.run_id)
        if not self.access_token or not self.author_urn:
            raise ValueError("LINKEDIN_ACCESS_TOKEN or LINKEDIN_AUTHOR_URN environment variable is missing.")
        
        # Build the post text
        post_text = (
            f"{payload.generated_copy.hook}\n\n"
            f"{payload.generated_copy.caption}\n\n"
            f"{payload.generated_copy.cta}\n\n"
            f"{' '.join(payload.generated_copy.hashtags)}"
        )

        try:
            # 1. Register Upload for each image
            image_urns = []
            async with aiohttp.ClientSession() as session:
                for img_path in payload.image_paths:
                    register_payload = {
                        "registerUploadRequest": {
                            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                            "owner": self.author_urn,
                            "serviceRelationships": [
                                {
                                    "relationshipType": "OWNER",
                                    "identifier": "urn:li:userGeneratedContent"
                                }
                            ]
                        }
                    }
                    
                    headers = {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                        "X-Restli-Protocol-Version": "2.0.0"
                    }
                    
                    async with session.post(
                        "https://api.linkedin.com/v2/assets?action=registerUpload", 
                        json=register_payload, 
                        headers=headers
                    ) as resp:
                        if resp.status not in (200, 201):
                            logger.error("Failed to register image upload on LinkedIn", status=resp.status)
                            continue
                            
                        data = await resp.json()
                        upload_mechanism = data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
                        upload_url = upload_mechanism["uploadUrl"]
                        asset_urn = data["value"]["asset"]
                        
                        # 2. Upload the actual image bytes
                        with open(img_path, "rb") as f:
                            img_bytes = f.read()
                            
                        upload_headers = {"Authorization": f"Bearer {self.access_token}"}
                        async with session.put(upload_url, data=img_bytes, headers=upload_headers) as upload_resp:
                            if upload_resp.status in (200, 201):
                                image_urns.append(asset_urn)
                            else:
                                logger.error("Failed to upload image bytes to LinkedIn", status=upload_resp.status)

                if not image_urns:
                    logger.error("No images successfully uploaded to LinkedIn. Aborting post.", run_id=payload.run_id)
                    return

                # 3. Create the UGC Post
                share_media = []
                for urn in image_urns:
                    share_media.append({
                        "status": "READY",
                        "description": {"text": payload.generated_copy.alt_text},
                        "media": urn,
                        "title": {"text": payload.plan.topic}
                    })

                ugc_payload = {
                    "author": self.author_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": post_text
                            },
                            "shareMediaCategory": "IMAGE",
                            "media": share_media
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                    }
                }

                async with session.post(
                    "https://api.linkedin.com/v2/ugcPosts",
                    json=ugc_payload,
                    headers=headers
                ) as post_resp:
                    if post_resp.status in (200, 201):
                        logger.info("Successfully published to LinkedIn! 🎉", run_id=payload.run_id)
                    else:
                        resp_text = await post_resp.text()
                        logger.error("Failed to create LinkedIn post", status=post_resp.status, response=resp_text)

        except Exception as e:
            logger.error("LinkedInPublisherPlugin failed", error=str(e), exc_info=True, run_id=payload.run_id)
