from typing import Dict, Any, List, Optional, Tuple
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentPlan, TemplateSelection, CopyOutput, LLMCallLog
from src.foundation.artifact_registry import ArtifactRegistry
from src.foundation.llm_gateway import LLMGateway
from src.data.knowledge_store import KnowledgeStore
import json
import structlog

logger = structlog.get_logger(__name__)

class CopyGenerator:
    """
    Thin compiler layer that loads template-specific prompts, gathers database context,
    formats user requirements, and uses the LLM Gateway to generate structured CopyOutput.
    """
    def __init__(
        self,
        config: AppConfig,
        registry: ArtifactRegistry,
        gateway: LLMGateway,
        knowledge_store: KnowledgeStore
    ):
        self.config = config.llm
        self.registry = registry
        self.gateway = gateway
        self.knowledge = knowledge_store

    async def generate(
        self,
        plan: ContentPlan,
        template: TemplateSelection,
        feedback: Optional[str] = None
    ) -> Tuple[CopyOutput, LLMCallLog]:
        """
        Gathers context from Knowledge Store, compiles the prompt,
        invokes the LLM via LLM Gateway, and returns parsed copy output + call logs.
        """
        logger.info("Generating post copy", topic_id=plan.topic_id, template=template.template_type)
        
        # 1. Load active template-specific prompt
        prompt_artifact = self.registry.get("prompts", template.prompt_key)
        system_prompt = prompt_artifact.content.get("system_prompt", "You are a creative strategist.")
        
        # 2. Gather database context if applicable
        additional_context = await self._gather_context(plan, template)
        
        # Fetch the topic details to extract context
        topic_details = await self.knowledge.get_topic_by_id(plan.topic_id)
        
        # 3. Format user prompt
        user_prompt = self._compile_user_prompt(plan, template, topic_details, additional_context, feedback)
        
        # 4. Invoke LLM Gateway for structured generation
        temp = self.config.temperatures.generate if not feedback else self.config.temperatures.retry
        
        copy_obj, log = await self.gateway.complete(
            module_name="copy_generator",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_model=CopyOutput,
            temperature=temp,
            max_tokens=self.config.max_tokens.carousel if template.slide_count > 1 else self.config.max_tokens.single,
            use_fallback=True
        )
        
        return copy_obj, log

    async def _gather_context(self, plan: ContentPlan, template: TemplateSelection) -> str:
        """Fetch supplemental jobs or testimonial context from Knowledge database."""
        context_parts = []
        
        if template.template_type == "job_drop" or plan.pillar == "Opportunity":
            jobs = await self.knowledge.get_featured_jobs()
            if jobs:
                context_parts.append("ACTIVE FEATURED JOBS FROM DATABASE:")
                for job in jobs:
                    context_parts.append(
                        f"- Company: {job['company']}\n"
                        f"  Role: {job['role']}\n"
                        f"  Location: {job['location']}\n"
                        f"  Apply Link: {job['link']}\n"
                        f"  Posted Date: {job['posted_date']}"
                    )
        elif template.template_type == "success_story" or plan.pillar == "Proof":
            testi = await self.knowledge.get_random_testimonial()
            if testi:
                context_parts.append("STUDENT TESTIMONIAL FROM DATABASE:")
                context_parts.append(
                    f"- Name: {testi['name']}\n"
                    f"  Role Landed: {testi['role_landed']}\n"
                    f"  Quote: \"{testi['quote']}\""
                )
                
        return "\n".join(context_parts)

    def _compile_user_prompt(
        self,
        plan: ContentPlan,
        template: TemplateSelection,
        topic_details: Optional[Dict[str, Any]],
        additional_context: str,
        feedback: Optional[str] = None
    ) -> str:
        """Format post variables and guidelines into the final instruction prompt."""
        context = topic_details.get("topic_context", "") if topic_details else ""
        
        prompt_lines = [
            f"TARGET PILLAR: {plan.pillar}",
            f"TOPIC TITLE: {plan.topic}",
            f"TOPIC CONTEXT / BACKGROUND INFORMATION:",
            context,
            ""
        ]

        if additional_context:
            prompt_lines.extend([additional_context, ""])

        prompt_lines.extend([
            f"TARGET AUDIENCE: {plan.audience}",
            f"SUGGESTED CTA: {plan.suggested_cta}",
            f"LAYOUT FORMAT: {template.template_type}",
            f"TOTAL SLIDES REQUIRED: {template.slide_count}",
            f"LAYOUT STYLE HINTS:",
            json.dumps(template.layout_hints, indent=2),
            ""
        ])

        if feedback:
            prompt_lines.extend([
                "⚠️ QA CRITIC FEEDBACK FROM PREVIOUS ATTEMPT (YOU MUST FIX THIS):",
                feedback,
                ""
            ])

        prompt_lines.append(
            "Produce a structured JSON output conforming EXACTLY to the following schema keys:\n"
            "- hook: Strong social media hook/headline\n"
            "- slides: List of slides containing slide_num, heading, body, and visual_note\n"
            "- caption: Body text description for the social post\n"
            "- hashtags: List of relevant hashtags (max 5)\n"
            "- cta: Specific call to action\n"
            "- alt_text: Text description of the visual presentation for accessibility"
        )

        return "\n".join(prompt_lines)
