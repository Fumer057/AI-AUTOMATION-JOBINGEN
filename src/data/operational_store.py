import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiosqlite
from src.utils.config_loader import AppConfig
from src.foundation.metrics_collector import Metric
import structlog

logger = structlog.get_logger(__name__)

class OperationalStore:
    """
    Handles all SQLite read/write operations for the dynamic operational
    run data (run history, metrics, cost analysis, LLM calls, engagement, and insights).
    """
    def __init__(self, config: AppConfig):
        self.config = config.storage
        self.db_path = Path(self.config.operational_database_path)
        self.schema_path = Path(__file__).parent / "schema_operational.sql"

    async def initialize(self):
        """Ensure database directory exists and execute schema DDL."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("Initializing Operational Store", db_path=str(self.db_path))
        
        async with aiosqlite.connect(self.db_path) as conn:
            # Enable foreign keys for cascade deletes
            await conn.execute("PRAGMA foreign_keys = ON;")
            
            # Read and execute schema
            schema_ddl = self.schema_path.read_text(encoding="utf-8")
            await conn.executescript(schema_ddl)
            await conn.commit()

    async def log_run(
        self,
        run_id: str,
        run_date: str,
        pillar: Optional[str],
        topic_id: Optional[str],
        template_type: Optional[str],
        qa_score: Optional[float],
        qa_attempts: int,
        approved: bool,
        output_path: Optional[str],
        content_state_json: str,
        artifact_versions_json: str,
        error_log: Optional[str],
        llm_cost_usd: float,
        duration_ms: int
    ):
        """Insert a new execution run record into generation_history."""
        created_at = datetime.utcnow().isoformat()
        
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO generation_history (
                    run_id, run_date, pillar, topic_id, template_type, 
                    qa_score, qa_attempts, approved, output_path, 
                    content_state_json, artifact_versions_json, error_log, 
                    llm_cost_usd, duration_ms, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, run_date, pillar, topic_id, template_type,
                    qa_score, qa_attempts, 1 if approved else 0, output_path,
                    content_state_json, artifact_versions_json, error_log,
                    llm_cost_usd, duration_ms, created_at
                )
            )
            await conn.commit()
            logger.info("Run history logged", run_id=run_id, date=run_date, qa_score=qa_score)

    async def log_llm_call(
        self,
        run_id: str,
        module: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        cached: bool,
        prompt_hash: Optional[str] = None
    ):
        """Log details of a single LLM API call."""
        called_at = datetime.utcnow().isoformat()
        
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO llm_call_log (
                    run_id, module, model, input_tokens, output_tokens, 
                    cost_usd, latency_ms, cached, prompt_hash, called_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, module, model, input_tokens, output_tokens,
                    cost_usd, latency_ms, 1 if cached else 0, prompt_hash, called_at
                )
            )
            await conn.commit()

    async def write_metrics(self, run_id: str, metrics: List[Metric]):
        """Write a batch of collected pipeline metrics to storage."""
        async with aiosqlite.connect(self.db_path) as conn:
            for metric in metrics:
                await conn.execute(
                    """INSERT INTO pipeline_metrics (run_id, metric_name, metric_value, recorded_at) 
                       VALUES (?, ?, ?, ?)""",
                    (run_id, metric.name, metric.value, metric.recorded_at.isoformat())
                )
            await conn.commit()
            logger.info("Pipeline metrics written", run_id=run_id, count=len(metrics))

    # ── Operational Queries ──

    async def get_recent_runs(self, limit: int = 14) -> List[Dict[str, Any]]:
        """Fetch the most recent run records from history."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM generation_history ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_pillar_counts(self, since_date: str) -> Dict[str, int]:
        """Fetch the counts of generated posts grouped by pillar since a specific date."""
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """SELECT pillar, COUNT(*) FROM generation_history 
                   WHERE run_date >= ? AND approved = 1 
                   GROUP BY pillar""",
                (since_date,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}

    async def get_average_qa_score(self, days: int = 30) -> float:
        """Calculate the average QA score over the last N days."""
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """SELECT AVG(qa_score) FROM generation_history 
                   WHERE created_at >= datetime('now', '-' || ? || ' days') AND approved = 1""",
                (days,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row[0] is not None else 0.0

    async def get_total_cost(self, days: int = 30) -> float:
        """Calculate the total LLM USD cost incurred in the last N days."""
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """SELECT SUM(llm_cost_usd) FROM generation_history 
                   WHERE created_at >= datetime('now', '-' || ? || ' days')""",
                (days,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row[0] is not None else 0.0

    async def upsert_post_metrics(self, run_id: str, platform: str, metrics: Dict[str, Any]):
        """Upsert engagement metrics for a specific post."""
        scored_at = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO engagement_scores (
                    run_id, platform, likes, comments, shares, impressions, engagement_rate, scored_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, platform) DO UPDATE SET
                   likes=excluded.likes,
                   comments=excluded.comments,
                   shares=excluded.shares,
                   impressions=excluded.impressions,
                   engagement_rate=excluded.engagement_rate,
                   scored_at=excluded.scored_at""",
                (
                    run_id, platform, metrics.get("likes", 0), metrics.get("comments", 0), 
                    metrics.get("shares", 0), metrics.get("impressions", 0), 
                    metrics.get("engagement_rate", 0.0), scored_at
                )
            )
            await conn.commit()

    async def get_raw_metrics(self, days: int = 30) -> List[Dict[str, Any]]:
        """Fetch raw engagement scores joined with run history for analysis."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            query = """
                SELECT e.*, g.pillar, g.template_type, g.run_date 
                FROM engagement_scores e
                JOIN generation_history g ON e.run_id = g.run_id
                WHERE e.scored_at >= datetime('now', '-' || ? || ' days')
            """
            async with conn.execute(query, (days,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def write_learning_insights(self, insights: List[Dict[str, Any]]):
        """Write computed learning multipliers (overwrites based on insight_id)."""
        created_at = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            for insight in insights:
                await conn.execute(
                    """INSERT INTO learning_insights (
                        insight_id, insight_type, insight_value, confidence, sample_size, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(insight_id) DO UPDATE SET
                       insight_value=excluded.insight_value,
                       confidence=excluded.confidence,
                       sample_size=excluded.sample_size,
                       created_at=excluded.created_at""",
                    (
                        insight["insight_id"], insight["insight_type"], insight["insight_value"], 
                        insight["confidence"], insight["sample_size"], created_at
                    )
                )
            await conn.commit()

    async def get_learning_insights(self, insight_type: str) -> List[Dict[str, Any]]:
        """Fetch current learning multipliers by type (e.g. 'template', 'pillar')."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM learning_insights WHERE insight_type = ?", (insight_type,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

