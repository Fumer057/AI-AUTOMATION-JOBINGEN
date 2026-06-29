import structlog
import os
import aiohttp
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentState

logger = structlog.get_logger(__name__)

class DiscordNotifierPlugin(BasePlugin):
    """
    Sends a notification to a Discord Webhook when the pipeline finishes rendering.
    Allows the human-in-the-loop to review the final PNGs and copy.
    """
    
    def name(self) -> str:
        return "discord_notifier"
        
    def subscriptions(self) -> dict:
        return {"RenderComplete": self.handle_event}

    def __init__(self, config: AppConfig):
        self.config = config
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    async def handle_event(self, payload: ContentState):
        logger.info("DiscordNotifierPlugin: Received RenderComplete", run_id=payload.run_id)
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL environment variable is missing.")
        

        try:
            # Build the rich embed for Discord
            description = (
                f"**Template**: {payload.template.template_type}\n"
                f"**Hook**: {payload.generated_copy.hook}\n"
                f"**Caption**: {payload.generated_copy.caption}\n"
                f"**Images**: {len(payload.image_paths)} generated"
            )
            
            discord_payload = {
                "content": f"🚀 **New Content Ready for Review!** [Run: `{payload.run_id}`]",
                "embeds": [
                    {
                        "title": payload.plan.topic,
                        "description": description,
                        "color": 3447003  # A nice blue color
                    }
                ]
            }
            
            # Send the request
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=discord_payload) as response:
                    if response.status in (200, 204):
                        logger.info("Discord notification sent successfully.", run_id=payload.run_id)
                    else:
                        logger.error("Failed to send Discord notification.", status=response.status, run_id=payload.run_id)
                        
        except Exception as e:
            logger.error("DiscordNotifierPlugin failed", error=str(e), exc_info=True, run_id=payload.run_id)
