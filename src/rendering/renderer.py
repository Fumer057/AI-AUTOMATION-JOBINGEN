import os
from pathlib import Path
from typing import List
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
import structlog
from src.utils.config_loader import AppConfig
from src.models.content_state import RenderSpec

logger = structlog.get_logger(__name__)

class DesignRenderer:
    """
    Ingests a RenderSpec, renders it through Jinja2 HTML templates,
    and uses Playwright to snapshot high-quality PNGs of each slide.
    """
    def __init__(self, config: AppConfig):
        self.config = config.renderer
        self.output_config = config.storage
        self.templates_dir = Path(self.config.templates_dir).resolve()
        
        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}, attempting to use relative path.")
            # Fallback to local relative if absolute fails (e.g., config not resolved correctly)
            self.templates_dir = Path.cwd() / self.config.templates_dir
            
        self.env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
        self.output_dir = Path(self.output_config.output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def render(self, spec: RenderSpec, run_id: str) -> List[str]:
        """
        Renders the given spec into HTML and takes screenshots.
        Returns a list of absolute paths to the saved PNG files.
        """
        logger.info("Starting design rendering", template=spec.template, slides=len(spec.slides))
        
        # 1. Resolve template name (e.g. "carousel" -> "carousel_v6.html")
        template_filename = f"{spec.template}_{spec.template_version}.html"
        
        # 2. Render HTML via Jinja
        try:
            template = self.env.get_template(template_filename)
        except Exception as e:
            logger.error("Failed to load template file", template=template_filename, error=str(e))
            raise e
            
        html_content = template.render(spec=spec)
        
        # We need a temporary HTML file for Playwright to load locally 
        # so it resolves base.css and local images in the templates dir
        temp_html_path = self.templates_dir / f"temp_{run_id}.html"
        try:
            with open(temp_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            # 3. Launch Playwright
            image_paths = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                
                # Retina scale factor for ultra crisp images
                page = await browser.new_page(device_scale_factor=2)
                
                # Load the local HTML file (requires file:/// scheme on windows)
                file_url = f"file:///{str(temp_html_path).replace(os.sep, '/')}"
                await page.goto(file_url, wait_until="networkidle")
                
                # Wait for custom fonts to load (especially google fonts)
                await page.evaluate("document.fonts.ready")
                
                # Find all slides
                slides = await page.query_selector_all(".slide")
                logger.info("Found slide elements", count=len(slides))
                
                # Ensure output directory for this run exists
                run_out_dir = self.output_dir / run_id
                run_out_dir.mkdir(parents=True, exist_ok=True)
                
                # Snapshot each slide
                for i, slide_el in enumerate(slides):
                    slide_num = spec.slides[i].slide_num if i < len(spec.slides) else i + 1
                    out_path = run_out_dir / f"slide_{slide_num:02d}.{self.config.output_format}"
                    
                    # Take screenshot of the exact bounding box of the slide element
                    await slide_el.screenshot(
                        path=str(out_path),
                        type=self.config.output_format, 
                        quality=100 if self.config.output_format == "jpeg" else None
                    )
                    image_paths.append(str(out_path))
                    logger.debug("Saved slide image", slide=slide_num, path=str(out_path))
                    
                await browser.close()
                
            logger.info("Successfully rendered all slides", total_images=len(image_paths), run_id=run_id)
            return image_paths
            
        finally:
            # Cleanup temporary HTML file
            if temp_html_path.exists():
                temp_html_path.unlink()
