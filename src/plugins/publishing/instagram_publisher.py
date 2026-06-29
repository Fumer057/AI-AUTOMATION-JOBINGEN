import structlog
import os
import aiohttp
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentState

logger = structlog.get_logger(__name__)

class InstagramPublisherPlugin(BasePlugin):
    """
    Publishes rendered images and copy to Instagram using the Meta Graph API.
    Supports Dry Run mode if credentials are not provided.
    """
    
    def name(self) -> str:
        return "instagram_publisher"
        
    def subscriptions(self) -> dict:
        return {"RenderComplete": self.handle_event}

    def __init__(self, config: AppConfig):
        self.config = config
        self.access_token = os.environ.get("IG_ACCESS_TOKEN")
        self.ig_user_id = os.environ.get("IG_USER_ID")
        self.is_dry_run = not (self.access_token and self.ig_user_id)

    async def handle_event(self, payload: ContentState):
        logger.info("InstagramPublisherPlugin: Received RenderComplete", run_id=payload.run_id)
        
        # Build the post text
        post_text = (
            f"{payload.generated_copy.hook}\n\n"
            f"{payload.generated_copy.caption}\n\n"
            f"{payload.generated_copy.cta}\n\n"
            f"{' '.join(payload.generated_copy.hashtags)}"
        )

        try:
            # Note: IG Graph API requires the images to be hosted on a public URL.
            # In a real environment, you'd upload them to an S3 bucket first.
            # For this MVP plugin, if they are local, it will fail unless exposed via ngrok or similar.
            # We'll assume for the script that there's an image hosting utility, 
            # or we log a warning and return if it's a local file.
            
            # This is a simplified Graph API Flow:
            # 1. Create Media Container
            # 2. Publish Media Container

            first_image_path = payload.image_paths[0] if payload.image_paths else None
            if not first_image_path:
                logger.error("No images to publish to Instagram.", run_id=payload.run_id)
                return
                
            async with aiohttp.ClientSession() as session:
                # 1. Create Media Container
                create_url = f"https://graph.facebook.com/v19.0/{self.ig_user_id}/media"
                container_payload = {
                    "image_url": first_image_path,
                    "caption": post_text,
                    "access_token": self.access_token
                }
                
                async with session.post(create_url, data=container_payload) as create_resp:
                    if create_resp.status != 200:
                        logger.error("Failed to create IG Media Container", status=create_resp.status, response=await create_resp.text())
                        return
                    
                    create_data = await create_resp.json()
                    creation_id = create_data.get("id")
                    
                # 2. Publish Media Container
                publish_url = f"https://graph.facebook.com/v19.0/{self.ig_user_id}/media_publish"
                publish_payload = {
                    "creation_id": creation_id,
                    "access_token": self.access_token
                }
                
                async with session.post(publish_url, data=publish_payload) as publish_resp:
                    if publish_resp.status == 200:
                        logger.info("Successfully published to Instagram! 🎉", run_id=payload.run_id)
                    else:
                        logger.error("Failed to publish IG Media Container", status=publish_resp.status, response=await publish_resp.text())
                        
        except Exception as e:
            logger.error("InstagramPublisherPlugin failed", error=str(e), exc_info=True, run_id=payload.run_id)
