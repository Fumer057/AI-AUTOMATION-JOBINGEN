import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set
import aiosqlite
from src.data.operational_store import OperationalStore
from src.models.content_state import ContentState, PipelineStatus
import structlog

logger = structlog.get_logger(__name__)

class Memory:
    """
    Query manager built on top of the Operational Store.
    Translates historical run logs and metrics into actionable memory 
    for the Content Planner scoring engine.
    """
    def __init__(self, ops_store: OperationalStore):
        self.ops_store = ops_store
        self.db_path = ops_store.db_path

    async def get_recent_topic_ids(self, days: int = 14) -> Set[str]:
        """Fetch a set of topic IDs used in the last N days."""
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """SELECT topic_id FROM generation_history 
                   WHERE created_at >= datetime('now', '-' || ? || ' days') 
                   AND approved = 1 AND topic_id IS NOT NULL""",
                (days,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}

    async def is_topic_on_cooldown(self, topic_id: str, cooldown_days: int = 30) -> bool:
        """Check if a topic has been used within the configured cooldown window."""
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """SELECT 1 FROM generation_history 
                   WHERE topic_id = ? AND approved = 1 
                   AND created_at >= datetime('now', '-' || ? || ' days')
                   LIMIT 1""",
                (topic_id, cooldown_days)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def get_pillar_distribution(self, days: int = 14) -> Dict[str, float]:
        """
        Calculate actual pillar ratios generated in the last N days.
        Returns a dictionary of actual ratios: e.g. {'Educate': 0.45, 'Opportunity': 0.20, ...}
        """
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """SELECT pillar, COUNT(*) FROM generation_history 
                   WHERE created_at >= datetime('now', '-' || ? || ' days') 
                   AND approved = 1 AND pillar IS NOT NULL
                   GROUP BY pillar""",
                (days,)
            ) as cursor:
                rows = await cursor.fetchall()
                
                counts = {row[0]: row[1] for row in rows}
                total = sum(counts.values())
                
                if total == 0:
                    return {}
                    
                return {pillar: count / total for pillar, count in counts.items()}

    async def get_format_performance(self) -> Dict[str, float]:
        """
        Return performance multipliers by template type from the Learning Module.
        Used by the Planner scoring engine to rank layout options.
        """
        insights = await self.ops_store.get_learning_insights("template")
        # Map insight_id (e.g. "template_carousel") to float multiplier
        # Stripping the "template_" prefix
        perf = {}
        for row in insights:
            template_name = row["insight_id"].replace("template_", "")
            try:
                perf[template_name] = float(row["insight_value"])
            except ValueError:
                pass
        return perf

    async def get_pillar_multipliers(self) -> Dict[str, float]:
        """
        Return performance multipliers by pillar from the Learning Module.
        """
        insights = await self.ops_store.get_learning_insights("pillar")
        # Map insight_id (e.g. "pillar_Educate") to float multiplier
        perf = {}
        for row in insights:
            pillar_name = row["insight_id"].replace("pillar_", "")
            try:
                perf[pillar_name] = float(row["insight_value"])
            except ValueError:
                pass
        return perf

    async def log_run(self, state: ContentState):
        """
        Log the complete status of a finished pipeline run into the Operational database,
        automatically extracting metadata, LLM logs, and details.
        """
        # Serialize state parts
        plan_dict = state.plan.model_dump() if state.plan else {}
        template_dict = state.template.model_dump() if state.template else {}
        qa_dict = state.qa.model_dump() if state.qa else {}
        
        # Log basic run details
        await self.ops_store.log_run(
            run_id=state.run_id,
            run_date=state.date.isoformat(),
            pillar=state.plan.pillar if state.plan else None,
            topic_id=state.plan.topic_id if state.plan else None,
            template_type=state.template.template_type if state.template else None,
            qa_score=state.qa.overall_score if state.qa else None,
            qa_attempts=state.qa_attempts,
            approved=(state.status == PipelineStatus.DELIVERED),
            output_path=state.output_dir,
            content_state_json=state.model_dump_json(),
            artifact_versions_json=json.dumps(state.artifact_versions),
            error_log="\n".join(state.errors) if state.errors else None,
            llm_cost_usd=sum(log.cost_usd for log in state.llm_calls),
            duration_ms=state.total_duration_ms or 0
        )
        
        # Log individual LLM calls
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
            
        logger.info("Memory logged completed run", run_id=state.run_id, status=state.status.value)
