from typing import Dict, Any, List, Optional
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentPlan, TemplateSelection, CopyOutput, RenderSpec, SlideRenderData
from src.foundation.asset_manager import AssetManager
from src.foundation.artifact_registry import ArtifactRegistry
import structlog

logger = structlog.get_logger(__name__)

class RenderSpecBuilder:
    """
    Transforms the abstract ContentState (plan, template, copy) into a 
    deterministic RenderSpec that the Renderer can inject into Jinja2 templates.
    """
    def __init__(self, config: AppConfig, registry: ArtifactRegistry, asset_manager: AssetManager):
        self.config = config
        self.registry = registry
        self.assets = asset_manager

    def build(self, plan: ContentPlan, template: TemplateSelection, copy: CopyOutput, dynamic_assets: dict[str, str] = None) -> RenderSpec:
        logger.info("Building RenderSpec", template=template.template_type, slides=template.slide_count)
        
        dynamic_assets = dynamic_assets or {}
        
        # 1. Resolve active template version
        # Currently, templates in registry are managed slightly differently, but we can extract version from config
        # or assume the config has the active version.
        active_version = self.config.registry.active.templates.get(template.template_type, "unknown")
        
        # 2. Resolve dimensions
        dim_key = plan.dimensions
        dimensions = self.config.renderer.dimensions.get(dim_key, {"width": 1080, "height": 1080})
        
        # 3. Resolve base brand properties
        brand_colors = self.config.brand.colors
        font_family = self.config.brand.font_heading
        
        # 4. Resolve Logo and required assets
        # E.g. get the absolute path to the white logo variant
        try:
            logo_path = self.assets.get_logo(variant="white")
        except ValueError:
            logo_path = "" # Fallback if no logo configured
            
        resolved_assets = self.assets.resolve(plan.assets_needed)
        
        # 5. Build Slide Data
        slides = self._build_slide_data(copy, template.template_type, resolved_assets)
        
        spec = RenderSpec(
            template=template.template_type,
            template_version=active_version,
            dimensions=dimensions.model_dump() if hasattr(dimensions, 'model_dump') else dimensions,
            brand_colors=brand_colors.model_dump() if hasattr(brand_colors, 'model_dump') else brand_colors,
            font_family=font_family,
            logo_path=logo_path,
            assets=resolved_assets,
            dynamic_assets=dynamic_assets,
            slides=slides
        )
        return spec
        
    def _build_slide_data(self, copy: CopyOutput, template_type: str, resolved_assets: Dict[str, str]) -> List[SlideRenderData]:
        """
        Maps abstract copy slides into specific layout variants depending on the template type
        and slide position (e.g. title slide vs content vs CTA).
        """
        slides_data = []
        total_slides = len(copy.slides)
        
        for slide in copy.slides:
            layout = "default"
            
            # Layout Mapping Logic
            if template_type == "carousel":
                if slide.slide_num == 1:
                    layout = "title_slide"
                elif slide.slide_num == total_slides:
                    layout = "cta_slide"
                else:
                    layout = "content_slide"
            elif template_type == "job_drop":
                layout = "job_card"
            elif template_type == "comparison":
                layout = "two_column"
            elif template_type == "insight_card":
                layout = "centered_quote"
                
            accent = self._pick_accent(slide.slide_num)
            icon = self._match_icon(slide.visual_note, resolved_assets)
                    
            slide_data = SlideRenderData(
                slide_num=slide.slide_num,
                heading=slide.heading,
                body=slide.body,
                layout=layout,
                accent_color=accent,
                icon=icon
            )
            slides_data.append(slide_data)
            
        return slides_data

    def _pick_accent(self, slide_num: int) -> str:
        """Resolve dynamic accent colors from brand color config."""
        colors = self.config.brand.colors
        accent = colors.get("accent", "#3E92CC") if isinstance(colors, dict) else getattr(colors, "accent", "#3E92CC")
        return accent

    def _match_icon(self, visual_note: str, resolved_assets: Dict[str, str]) -> Optional[str]:
        """Match icons from the resolved asset registry based on visual note description keywords."""
        if not visual_note:
            return None
        note = visual_note.lower()
        if "email" in note or "mail" in note or "letter" in note or "envelope" in note:
            return resolved_assets.get("icon_email")
        if "check" in note or "done" in note or "success" in note or "tick" in note or "correct" in note:
            return resolved_assets.get("icon_check")
        return None
