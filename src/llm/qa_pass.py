from typing import Dict, Any, Tuple
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentPlan, TemplateSelection, CopyOutput, QAReport, LLMCallLog
from src.foundation.artifact_registry import ArtifactRegistry
from src.foundation.llm_gateway import LLMGateway
import json
import structlog

logger = structlog.get_logger(__name__)

class QAPass:
    """
    Evaluates the generated copy against a strict rubric.
    Ensures brand safety, structural compliance, and high quality.
    """
    def __init__(
        self,
        config: AppConfig,
        registry: ArtifactRegistry,
        gateway: LLMGateway,
    ):
        self.config = config.llm
        self.registry = registry
        self.gateway = gateway
        self.pass_threshold = 8.0 # Minimum overall score to pass

    async def evaluate(
        self,
        plan: ContentPlan,
        template: TemplateSelection,
        copy: CopyOutput,
        attempt: int
    ) -> Tuple[QAReport, LLMCallLog]:
        """
        Runs the QA evaluation using the LLM Gateway and returns a QAReport + metrics.
        """
        logger.info("Running QA evaluation", topic_id=plan.topic_id, attempt=attempt)
        
        # 1. Load active QA critic prompt/rubric
        prompt_artifact = self.registry.get("prompts", "qa_critic")
        system_prompt = prompt_artifact.content.get("system_prompt", "You are the QA Critic.")
        rubric_version = prompt_artifact.version
        
        # 2. Format the payload for the Critic
        user_prompt = self._compile_eval_prompt(plan, template, copy)
        
        # 3. Invoke LLM Gateway to generate QAReport
        # We use strict evaluation temperature
        temp = self.config.temperatures.evaluate
        
        # QAReport doesn't include rubric_version and attempt in the generation (we inject those)
        # So we create an internal Pydantic model just for the LLM output, or let the LLM generate a subset
        
        from pydantic import BaseModel
        class QAEvalResult(BaseModel):
            overall_score: float
            passed: bool
            scores: dict[str, float]
            feedback: str

        eval_obj, log = await self.gateway.complete(
            module_name="qa_pass",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_model=QAEvalResult,
            temperature=temp,
            max_tokens=500,
            use_fallback=True
        )
        
        # Determine strict pass logic: if LLM says passed but score < threshold, fail it.
        is_passed = eval_obj.passed and (eval_obj.overall_score >= self.pass_threshold)
        
        # Ensure scores dictionary has expected keys
        expected_keys = ["hook_strength", "brand_voice", "structural_compliance", "engagement_potential"]
        scores = eval_obj.scores or {k: eval_obj.overall_score for k in expected_keys}
        
        report = QAReport(
            overall_score=eval_obj.overall_score,
            passed=is_passed,
            attempt=attempt,
            scores=scores,
            feedback=eval_obj.feedback,
            rubric_version=rubric_version
        )
        
        if not report.passed:
            logger.warn("QA Failed", score=report.overall_score, feedback=report.feedback)
        else:
            logger.info("QA Passed", score=report.overall_score)
            
        return report, log

    def _compile_eval_prompt(
        self,
        plan: ContentPlan,
        template: TemplateSelection,
        copy: CopyOutput
    ) -> str:
        """Format the generated copy and plan context for the evaluator."""
        
        prompt_lines = [
            "EVALUATION TARGET:",
            "Please review the following generated content against the required plan and constraints.",
            "",
            "--- ORIGINAL PLAN ---",
            f"PILLAR: {plan.pillar}",
            f"TOPIC: {plan.topic}",
            f"AUDIENCE: {plan.audience}",
            f"EXPECTED CTA: {plan.suggested_cta}",
            "",
            "--- TEMPLATE CONSTRAINTS ---",
            f"TYPE: {template.template_type}",
            f"REQUIRED SLIDES: {template.slide_count}",
            "",
            "--- GENERATED COPY TO EVALUATE ---",
            json.dumps(copy.model_dump(), indent=2),
            "",
            "--- RUBRIC & INSTRUCTIONS ---",
            "Evaluate on a scale of 1.0 to 10.0 for the following categories:",
            "1. hook_strength: Does the hook grab attention immediately?",
            "2. brand_voice: Is it professional yet approachable for students?",
            "3. structural_compliance: Does it strictly follow the slide counts and template instructions?",
            "4. engagement_potential: Will this drive comments, saves, or clicks?",
            "",
            f"Provide an 'overall_score' (average or weighted).",
            f"Set 'passed' to true only if the overall_score >= {self.pass_threshold} and there are NO structural errors.",
            "Provide specific, actionable 'feedback' on what to fix if it fails."
        ]

        return "\n".join(prompt_lines)
