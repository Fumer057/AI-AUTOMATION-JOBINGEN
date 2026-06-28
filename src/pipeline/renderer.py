import os
import asyncio
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
import structlog
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentState

logger = structlog.get_logger(__name__)

class Renderer:
    """
    Takes the final approved ContentState and uses Jinja2 + Playwright 
    to render pixel-perfect PNG images for social media publishing.
    """
    def __init__(self, config: AppConfig):
        self.config = config.renderer
        self.brand = config.brand
        self.templates_dir = Path(self.config.templates_dir)
        self.output_base_dir = Path(config.storage.output_dir)
        
        # Setup Jinja environment
        self.jinja_env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
        
        # Ensure output dir exists
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

    async def render(self, state: ContentState) -> str:
        """
        Renders the entire ContentState into one or more PNG files.
        Returns the absolute path to the directory containing the rendered images.
        """
        if not state.qa or not state.copy_data:
            raise ValueError("Cannot render: Missing QA approval or Copy data.")
            
        run_id = state.run_id
        run_dir = self.output_base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        template_type = state.template.template_type
        
        # Determine the dimension based on template.
        # Carousels/memes might be 1080x1350, insight cards might be 1080x1080
        dim_key = "1080x1350" if template_type in ["carousel", "meme", "job_drop"] else "1080x1080"
        dims = self.config.dimensions.get(dim_key, self.config.dimensions.get("1080x1080"))
        
        # Setup context for Jinja
        context = {
            "brand": self.brand,
            "dimensions": dims,
            "plan": state.plan,
            "total_slides": len(state.copy_data.get("slides", [])),
            # This is populated by ImageGenerator plugin if dynamic image is requested
            "image_url": state.copy_data.get("dynamic_image_url") 
        }

        # Select HTML template (fallback to carousel if specific one doesn't exist)
        html_template_name = f"{template_type}.html"
        if not (self.templates_dir / html_template_name).exists():
            logger.warning(f"Template {html_template_name} not found, falling back to carousel.html")
            html_template_name = "carousel.html"
            
        jinja_template = self.jinja_env.get_template(html_template_name)
        
        logger.info("Renderer: Starting headless browser...", template=html_template_name, dims=dim_key)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": dims.width, "height": dims.height})
            
            slides = state.copy_data.get("slides", [])
            for i, slide in enumerate(slides):
                slide_num = i + 1
                
                # Update context for this specific slide
                context["slide"] = slide
                context["slide_number"] = slide_num
                
                # Render HTML string
                html_content = jinja_template.render(**context)
                
                # Load into Playwright
                await page.set_content(html_content, wait_until="networkidle")
                
                # Save screenshot
                output_path = run_dir / f"slide_{slide_num:02d}.{self.config.output_format}"
                await page.screenshot(
                    path=str(output_path),
                    type="png" if self.config.output_format == "png" else "jpeg",
                    quality=self.config.quality if self.config.output_format == "jpeg" else None
                )
                
                logger.info(f"Rendered slide {slide_num}/{len(slides)}", path=str(output_path))
                
            await browser.close()
            
        # Save state to output dir
        state.output_dir = str(run_dir.absolute())
        return state.output_dir
