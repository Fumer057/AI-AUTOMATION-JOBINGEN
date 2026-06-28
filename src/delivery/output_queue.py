import json
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from src.utils.config_loader import AppConfig
from src.models.content_state import ContentState, PipelineStatus
from src.data.operational_store import OperationalStore

logger = structlog.get_logger(__name__)

class OutputQueue:
    """
    Final stage of the pipeline. Packages the generated images and copy,
    writes a manifest, and logs the finalized run to the Operational Store.
    """
    def __init__(self, config: AppConfig, ops_store: OperationalStore):
        self.config = config.storage
        self.ops_store = ops_store
        self.output_base = Path(self.config.output_dir).resolve()
        
    async def process(self, state: ContentState) -> str:
        """
        Processes a fully rendered ContentState.
        Returns the absolute path to the packaged output directory.
        """
        logger.info("Packaging final output", run_id=state.run_id)
        
        if state.status != PipelineStatus.RENDERED:
            logger.warning("Output queue received state not in RENDERED status", status=state.status)
            
        run_dir = self.output_base / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Write the final text payload (for easy copy-pasting to social media)
        payload_path = run_dir / "social_payload.md"
        self._write_payload_markdown(state, payload_path)
        
        # 2. Write the raw state JSON for reproducibility
        state_path = run_dir / "state.json"
        with open(state_path, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))
            
        state.output_dir = str(run_dir)
        state.pack_manifest_path = str(state_path)
        state.status = PipelineStatus.DELIVERED
        
        # 3. Calculate total LLM cost and duration
        total_cost = sum(call.cost_usd for call in state.llm_calls)
        duration = 0
        if state.total_duration_ms:
            duration = state.total_duration_ms
        else:
            duration = int((datetime.utcnow() - state.started_at).total_seconds() * 1000)
            state.total_duration_ms = duration
            
        # 4. Log the run to Operational Store
        plan = state.plan
        qa = state.qa
        
        await self.ops_store.log_run(
            run_id=state.run_id,
            run_date=state.date.isoformat(),
            pillar=plan.pillar if plan else None,
            topic_id=plan.topic_id if plan else None,
            template_type=state.template.template_type if state.template else None,
            qa_score=qa.overall_score if qa else None,
            qa_attempts=state.qa_attempts,
            approved=True if qa and qa.passed else False,
            output_path=str(run_dir),
            content_state_json=state.model_dump_json(),
            artifact_versions_json=json.dumps(state.artifact_versions),
            error_log=json.dumps(state.errors) if state.errors else None,
            llm_cost_usd=total_cost,
            duration_ms=duration
        )
        
        # 5. Log individual LLM calls
        for call in state.llm_calls:
            await self.ops_store.log_llm_call(
                run_id=state.run_id,
                module=call.module,
                model=call.model,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
                latency_ms=call.latency_ms,
                cached=call.cached
            )
            
        logger.info("Output successfully packaged and logged", run_id=state.run_id, path=str(run_dir))
        return str(run_dir)

    def _write_payload_markdown(self, state: ContentState, path: Path):
        """Creates a human-readable markdown file with the final text content and process details."""
        if not state.generated_copy:
            return
            
        copy = state.generated_copy
        plan = state.plan
        qa = state.qa
        
        lines = [
            f"# JobInGen Content Engine Report",
            f"**Run ID**: `{state.run_id}` | **Date**: `{state.date.isoformat()}` | **Status**: `✅ {state.status.name}`",
            "---",
            "## 1. Final Post Assets",
            "### Generated Images"
        ]
        
        for img in state.image_paths:
            img_path = Path(img)
            # Embed image in markdown
            lines.append(f"![{img_path.name}](./{img_path.name})")
            lines.append("")
            
        lines.extend([
            "### Social Media Payload",
            "**Caption:**",
            f"> {copy.caption}",
            "",
            "**Call to Action:**",
            f"> {copy.cta}",
            "",
            "**Hashtags:**",
            f"`{' '.join(copy.hashtags) if copy.hashtags else ''}`",
            "",
            "**Alt Text:**",
            f"> {copy.alt_text}",
            "",
            "---",
            "## 2. Intelligence & Planning",
            f"- **Pillar**: `{plan.pillar if plan else 'N/A'}`",
            f"- **Topic**: {plan.topic if plan else 'N/A'}",
            f"- **Target Audience**: {plan.audience if plan else 'N/A'}",
            f"- **Template Selected**: `{state.template.template_type if state.template else 'N/A'}`",
            ""
        ])
        
        if plan and plan.scoring:
            s = plan.scoring
            lines.extend([
                "**Scoring Breakdown:**",
                f"- Total Score: **{s.total:.2f}**",
                f"- Pillar Deficit: {s.pillar_deficit:.2f}",
                f"- Freshness: {s.freshness:.2f}",
                f"- Engagement History: {s.engagement_history:.2f}",
                ""
            ])
            
        lines.extend([
            "---",
            "## 3. QA & Critic Pass",
            f"- **Overall Score**: `{qa.overall_score if qa else 'N/A'}/10`",
            f"- **Passed on Attempt**: `{state.qa_attempts}`",
            f"- **Feedback**: {qa.feedback if qa else 'N/A'}",
            ""
        ])
        
        if qa and qa.scores:
            lines.append("**Rubric Scores:**")
            for k, v in qa.scores.items():
                lines.append(f"- {k}: {v}/10")
            lines.append("")
            
        lines.extend([
            "---",
            "## 4. LLM Telemetry",
            f"- **Total Generation Time**: `{state.total_duration_ms / 1000 if state.total_duration_ms else 0:.1f}s`",
        ])
        
        total_cost = 0.0
        total_in = 0
        total_out = 0
        for call in state.llm_calls:
            total_cost += call.cost_usd
            total_in += call.input_tokens
            total_out += call.output_tokens
            lines.append(f"- **{call.module}** (`{call.model}`): {call.latency_ms}ms | {call.input_tokens} in / {call.output_tokens} out | Strategy: `{call.strategy_used}`")
            
        lines.extend([
            "",
            f"**Total LLM Cost**: `${total_cost:.5f}`",
            f"**Total Tokens**: {total_in + total_out}"
        ])
            
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
