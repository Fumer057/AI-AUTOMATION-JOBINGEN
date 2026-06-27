from typing import Dict, Any, List, Optional
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentPlan, TemplateSelection
from src.foundation.artifact_registry import ArtifactRegistry
from src.data.knowledge_store import KnowledgeStore
import structlog

logger = structlog.get_logger(__name__)

class TemplateSelector:
    """
    Decides the final visual layout format (template) for the content,
    ensuring it is compatible with the selected pillar, mapping it to
    the template-specific prompt key and setting default slide counts.
    """
    def __init__(self, config: AppConfig, registry: ArtifactRegistry, knowledge_store: KnowledgeStore):
        self.config = config
        self.registry = registry
        self.knowledge = knowledge_store
        self.compatibility: Dict[str, List[str]] = config.planner.template_compatibility

    async def select(self, plan: ContentPlan) -> TemplateSelection:
        """
        Determine the layout template type, slide counts, prompt keys, 
        and layout hints for the given content plan.
        """
        logger.info("Selecting template for content plan", topic_id=plan.topic_id, pillar=plan.pillar)
        
        # 1. Fetch the topic details to get the suggested template
        topic = await self.knowledge.get_topic_by_id(plan.topic_id)
        suggested = topic.get("suggested_template") if topic else None
        
        # 2. Get compatible templates for this pillar
        compatible_templates = self.compatibility.get(plan.pillar, [])
        if not compatible_templates:
            raise ValueError(f"No compatible templates configured in config.yaml for pillar: {plan.pillar}")
            
        # 3. Determine final template type
        template_type = "insight_card" # Default fallback
        if suggested and suggested in compatible_templates:
            template_type = suggested
            logger.info("Using suggested template from topic bank", template=template_type)
        else:
            # Fallback to the first compatible template for the pillar
            template_type = compatible_templates[0]
            logger.warning(
                "Suggested template not compatible or missing; falling back to pillar compatible first",
                suggested=suggested,
                fallback=template_type,
                pillar=plan.pillar
            )

        # 4. Determine slide counts
        slide_count = 5 if template_type == "carousel" else 1

        # 5. Resolve copywriter prompt key (registered under config registry)
        prompt_key_map = {
            "insight_card": "copywriter_insight",
            "carousel": "copywriter_carousel",
            "job_drop": "copywriter_jobdrop",
            "comparison": "copywriter_comparison",
            "success_story": "copywriter_success",
            "mentor_spotlight": "copywriter_mentor",
            "meme": "copywriter_meme"
        }
        prompt_key = prompt_key_map.get(template_type, f"copywriter_{template_type}")
        
        # Verify the key is registered in our configuration mapping
        active_prompts = self.registry.active_versions.prompts
        
        # Check if the attribute exists or key exists in model dump dict
        active_keys = active_prompts.keys() if isinstance(active_prompts, dict) else active_prompts.model_dump().keys()
        if prompt_key not in active_keys:
            # If we don't have a template-specific prompt version configured, fallback to generic carousel/insight
            logger.warning("Template-specific prompt key not configured in registry, falling back", prompt_key=prompt_key)
            prompt_key = "copywriter_carousel" if slide_count > 1 else "copywriter_insight"

        # 6. Build layout hints
        layout_hints = self._get_layout_hints(template_type)

        logger.info(
            "Template selection complete",
            template=template_type,
            slides=slide_count,
            prompt_key=prompt_key
        )

        return TemplateSelection(
            template_type=template_type,
            slide_count=slide_count,
            prompt_key=prompt_key,
            layout_hints=layout_hints
        )

    def _get_layout_hints(self, template_type: str) -> Dict[str, str]:
        hints = {
            "carousel": {
                "slide_1": "Bold hook statement focusing on a student pain point. Minimal body text.",
                "slide_2_to_n": "Actionable value step. Focus on one clear rule or illustration per slide.",
                "last_slide": "Clear call to action card with next steps."
            },
            "insight_card": {
                "layout": "Centered headline with bold card highlight. Clean, highly readable card layout."
            },
            "job_drop": {
                "layout": "Grid split showing Job Title, Company Logo placeholder, Location, and Apply CTA."
            },
            "comparison": {
                "layout": "Two-column grid layout contrasting the wrong way vs. the right way."
            },
            "success_story": {
                "layout": "Split layout showing the student's name, landed role, and quoted testimonial."
            },
            "mentor_spotlight": {
                "layout": "Profile highlight showing mentor photo, current company, and their career tip."
            },
            "meme": {
                "layout": "Image/illustration panel on top with bold impact text on bottom."
            }
        }
        return hints.get(template_type, {"layout": "Standard card design"})
