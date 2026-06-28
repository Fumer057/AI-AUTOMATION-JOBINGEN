import os
import asyncio
import structlog
import litellm
from pathlib import Path
import urllib.request

from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentState

logger = structlog.get_logger(__name__)

class ImageGeneratorPlugin(BasePlugin):
    """
    Hooks into the pipeline right before rendering.
    If the template requires a dynamic background or meme image, this plugin
    uses the Gemini API to generate it and saves it locally.
    """
    
    def name(self) -> str:
        return "image_generator"
        
    def subscriptions(self) -> dict:
        return {"ContentApproved": self.handle_event}

    def __init__(self, config: AppConfig):
        self.config = config
        self.output_base_dir = Path(config.storage.output_dir)

    async def handle_event(self, payload: ContentState):
        logger.info(f"ImageGeneratorPlugin: Received ContentApproved", run_id=payload.run_id)
        
        # Only run for templates that need dynamic images
        template_type = payload.template.template_type
        if template_type not in ["meme", "story"]:
            logger.info("ImageGeneratorPlugin: Skipping, template type does not require dynamic image.", template=template_type)
            return

        image_prompt = payload.generated_copy.image_prompt
        if not image_prompt:
            logger.warning("ImageGeneratorPlugin: Meme/Story template selected but no image_prompt provided by AI!")
            return

        logger.info("ImageGeneratorPlugin: Calling Gemini Image Generation API...", prompt=image_prompt)
        
        run_dir = self.output_base_dir / payload.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        img_path = run_dir / "generated_bg.png"

        try:
            # Using litellm image generation mapping for Gemini (Google Vertex or AI Studio)
            # Make sure GEMINI_API_KEY is in env
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY not found in env! Using mock generated image for testing.")
                # Save a dummy grey image for mock
                with open(img_path, "wb") as f:
                    # just a tiny 1x1 png 
                    f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
                payload.dynamic_assets["background"] = str(img_path.absolute().as_posix())
                return

            # Note: For LiteLLM to use Gemini imagen, model must be "gemini/..." or "vertex_ai/imagegeneration..."
            # Wait, using standard litellm.image_generation
            response = litellm.image_generation(
                prompt=image_prompt,
                model="gemini/imagen-3.0-generate-001",
                n=1,
                size="1080x1080"
            )
            
            image_url = response.data[0].url
            
            # Download the image
            logger.info("ImageGeneratorPlugin: Image generated successfully. Downloading...", url=image_url)
            urllib.request.urlretrieve(image_url, img_path)
            
            # Save the local path to the state so Renderer can inject it via Jinja
            payload.dynamic_assets["background"] = str(img_path.absolute().as_posix())
            logger.info("ImageGeneratorPlugin: Image saved to state.", path=str(img_path))
            
        except Exception as e:
            logger.error("ImageGeneratorPlugin: Failed to generate or download image", error=str(e))
