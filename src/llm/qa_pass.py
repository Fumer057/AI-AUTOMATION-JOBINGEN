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
        self.config = config
        self.llm_config = config.llm
        self.critic_config = getattr(config, "critic", None)
        self.registry = registry
        self.gateway = gateway
        # Initialize default threshold from config if available
        self.pass_threshold = getattr(self.critic_config, "pass_threshold", 7.0) if self.critic_config else 7.0

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
        # 1. Load active QA critic prompt
        prompt_artifact = self.registry.get("prompts", "qa_critic")
        system_prompt = prompt_artifact.content.get("system_prompt", "You are the QA Critic.")
        
        # 2. Load active rubric v2 from registry
        rubric_artifact = self.registry.get("rubrics", "critic")
        rubric_data = rubric_artifact.content
        rubric_version = rubric_artifact.version
        
        # Dynamic pass threshold from rubric or fallback to config
        pass_threshold = rubric_data.get("pass_threshold", self.pass_threshold)
        
        # 3. Format the payload for the Critic
        user_prompt = self._compile_eval_prompt(plan, template, copy, rubric_data, pass_threshold)
        
        # 4. Invoke LLM Gateway to generate QAReport
        # We use strict evaluation temperature
        temp = self.llm_config.temperatures.critic
        
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
            max_tokens=2000,
            use_fallback=True
        )
        
        # Determine strict pass logic: if LLM says passed but score < threshold, fail it.
        is_passed = eval_obj.passed and (eval_obj.overall_score >= pass_threshold)
        
        # Ensure scores dictionary has expected keys
        expected_keys = list(rubric_data.get("criteria", {}).keys())
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
            logger.warning("QA Failed", score=report.overall_score, feedback=report.feedback)
        else:
            logger.info("QA Passed", score=report.overall_score)
            
        return report, log

    def _compile_eval_prompt(
        self,
        plan: ContentPlan,
        template: TemplateSelection,
        copy: CopyOutput,
        rubric_data: Dict[str, Any],
        pass_threshold: float
    ) -> str:
        """Format the generated copy and plan context for the evaluator dynamically using the rubric."""
        
        criteria = rubric_data.get("criteria", {})
        rubric_lines = []
        for name, info in criteria.items():
            desc = info.get("description", "")
            weight = info.get("weight", 0.0)
            guide = info.get("score_guide", {})
            guide_str = ""
            if guide:
                guide_str = "\n".join([f"    - {k}: {v}" for k, v in guide.items()])
            rubric_lines.append(f"- {name} (Weight: {weight}): {desc}")
            if guide_str:
                rubric_lines.append(f"  Score Guide:\n{guide_str}")
        
        rubric_instructions = "\n".join(rubric_lines)
        
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
            "Evaluate on a scale of 1.0 to 10.0 for the following categories according to their weight and guide:",
            rubric_instructions,
            "",
            f"Provide an 'overall_score' (weighted average of the category scores based on the weights above).",
            f"Set 'passed' to true only if the overall_score >= {pass_threshold} and there are NO structural errors.",
            "Provide specific, actionable 'feedback' on what to fix if it fails."
        ]

        return "\n".join(prompt_lines)
