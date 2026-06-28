import structlog
from typing import Dict, Any, Callable
from collections import defaultdict
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
from src.data.operational_store import OperationalStore

logger = structlog.get_logger(__name__)

class LearningLoopPlugin(BasePlugin):
    """
    Analyzes historical post engagement to generate intelligence multipliers
    (Learning Insights) which the Planner will consume to optimize content.
    """
    def __init__(self, config: AppConfig):
        self.config = config
        self.ops_store = OperationalStore(config)
        self.window_days = 30
        
        # We constrain the multipliers so the AI doesn't completely abandon 
        # formats that have a bad month.
        self.min_multiplier = 0.5
        self.max_multiplier = 1.5

    def name(self) -> str:
        return "learning_loop"

    def subscriptions(self) -> Dict[str, Callable]:
        return {"LearningTriggered": self.on_learning_triggered}

    async def on_learning_triggered(self, state: Any):
        logger.info("LearningLoopPlugin: Analyzing metrics...", window_days=self.window_days)
        
        raw_metrics = await self.ops_store.get_raw_metrics(days=self.window_days)
        if not raw_metrics:
            logger.info("LearningLoopPlugin: No metrics found to analyze.")
            return

        # 1. Aggregate metrics by template and pillar
        template_stats = defaultdict(lambda: {"engagement": 0.0, "count": 0})
        pillar_stats = defaultdict(lambda: {"engagement": 0.0, "count": 0})

        for row in raw_metrics:
            eng_rate = row.get("engagement_rate", 0.0)
            template = row.get("template_type")
            pillar = row.get("pillar")
            
            if template:
                template_stats[template]["engagement"] += eng_rate
                template_stats[template]["count"] += 1
            if pillar:
                pillar_stats[pillar]["engagement"] += eng_rate
                pillar_stats[pillar]["count"] += 1

        # 2. Calculate Baseline
        total_eng = sum(row.get("engagement_rate", 0.0) for row in raw_metrics)
        baseline = total_eng / len(raw_metrics) if raw_metrics else 0.0
        if baseline == 0.0:
            logger.info("LearningLoopPlugin: Baseline is 0, skipping insight generation.")
            return

        # 3. Compute Multipliers
        insights = []
        
        # Helper to compute normalized multiplier
        def calc_multiplier(avg: float) -> float:
            ratio = avg / baseline
            return max(self.min_multiplier, min(self.max_multiplier, ratio))
            
        for template, stat in template_stats.items():
            avg_eng = stat["engagement"] / stat["count"]
            multiplier = calc_multiplier(avg_eng)
            insights.append({
                "insight_id": f"template_{template}",
                "insight_type": "template",
                "insight_value": str(multiplier),
                "confidence": 0.8 if stat["count"] >= 5 else 0.4,
                "sample_size": stat["count"]
            })
            
        for pillar, stat in pillar_stats.items():
            avg_eng = stat["engagement"] / stat["count"]
            multiplier = calc_multiplier(avg_eng)
            insights.append({
                "insight_id": f"pillar_{pillar}",
                "insight_type": "pillar",
                "insight_value": str(multiplier),
                "confidence": 0.8 if stat["count"] >= 5 else 0.4,
                "sample_size": stat["count"]
            })

        # 4. Write back to DB
        await self.ops_store.write_learning_insights(insights)
        logger.info("LearningLoopPlugin: Generated insights", count=len(insights))
