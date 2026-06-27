from datetime import date
from typing import List, Dict, Any, Optional, Tuple, Set
from src.utils.config_loader import AppConfig
from src.models.content_state import ContentPlan, TopicScore, ContentState
from src.data.knowledge_store import KnowledgeStore
from src.data.memory import Memory
import structlog

logger = structlog.get_logger(__name__)

class ContentPlanner:
    """
    Scoring engine that selects today's topic, pillar, and suggested template.
    Uses argmax(score) over historical deficits, seasonality rules, freshness, 
    and format performance from Memory.
    """
    def __init__(self, config: AppConfig, registry: Any, memory: Memory, knowledge_store: KnowledgeStore):
        self.config = config.planner
        self.memory = memory
        self.knowledge = knowledge_store
        # Registry isn't strictly needed for metadata-based planning in Phase 1, 
        # but matches Orchestrator constructor contract.
        self.registry = registry

    async def create_plan(self, state: ContentState) -> ContentPlan:
        """
        Analyze current state (date, memory, topics bank) to score all available topics
        and select the one with the highest computed score.
        """
        run_date = state.date
        logger.info("Starting topic selection scoring", date=run_date.isoformat())

        # 1. Fetch parameters from Memory
        recent_topics = await self.memory.get_recent_topic_ids(self.config.history_window_days)
        actual_pillar_distribution = await self.memory.get_pillar_distribution(self.config.history_window_days)
        format_performance = await self.memory.get_format_performance()
        calendar_config = await self.knowledge.get_calendar_config()

        # 2. Get all candidate topics from Knowledge Store
        all_topics: List[Dict[str, Any]] = []
        for pillar in self.config.pillars.keys():
            topics = await self.knowledge.get_available_topics(pillar)
            all_topics.extend(topics)

        if not all_topics:
            raise ValueError("No topics available in topics_bank! Seed data or add topics.")

        scored_candidates: List[Tuple[Dict[str, Any], TopicScore]] = []

        # 3. Score each topic
        for topic in all_topics:
            topic_id = topic["topic_id"]
            
            # Check cooldown constraint
            is_on_cooldown = await self.memory.is_topic_on_cooldown(topic_id, self.config.topic_cooldown_days)
            if is_on_cooldown:
                logger.debug("Topic excluded due to active cooldown", topic_id=topic_id)
                continue

            score_breakdown = self._score_topic(
                topic,
                run_date,
                actual_pillar_distribution,
                format_performance,
                calendar_config,
                recent_topics
            )
            scored_candidates.append((topic, score_breakdown))

        if not scored_candidates:
            raise ValueError("All available topics are on active cooldown! Reduce cooldown window or add topics.")

        # 4. Pick top scoring candidate (argmax)
        scored_candidates.sort(key=lambda x: x[1].total, reverse=True)
        winner_topic, winner_score = scored_candidates[0]

        logger.info(
            "Selected winning topic",
            topic_id=winner_topic["topic_id"],
            title=winner_topic["topic_title"],
            pillar=winner_topic["pillar"],
            score=winner_score.total
        )

        # 5. Build suggested CTA, audience, and assets checklist based on pillar rules
        audience = self._determine_audience(winner_topic["pillar"])
        suggested_cta = self._determine_suggested_cta(winner_topic["pillar"])
        assets_needed = self._determine_assets_needed(winner_topic["pillar"])

        return ContentPlan(
            pillar=winner_topic["pillar"],
            topic=winner_topic["topic_title"],
            topic_id=winner_topic["topic_id"],
            audience=audience,
            suggested_cta=suggested_cta,
            assets_needed=assets_needed,
            dimensions="1080x1080",
            scoring=winner_score
        )

    def _score_topic(
        self,
        topic: Dict[str, Any],
        run_date: date,
        pillar_distribution: Dict[str, float],
        format_performance: Dict[str, float],
        calendar_config: Dict[str, Dict[str, Any]],
        recent_topics: Set[str]
    ) -> TopicScore:
        weights = self.config.score_weights
        pillar = topic["pillar"]
        topic_id = topic["topic_id"]

        # A. Pillar Deficit
        target_weight = self.config.pillars.get(pillar, 0.0)
        actual_weight = pillar_distribution.get(pillar, 0.0)
        deficit = max(0.0, target_weight - actual_weight)
        # Normalize deficit to 0.0 - 1.0 (since target_weight max is 1.0, deficit max is 1.0)
        pillar_deficit_score = deficit

        # B. Seasonality
        seasonality_score = 0.1 # default base
        month = run_date.month
        for rule in self.config.seasonality_rules:
            if month in rule.months and pillar in rule.boost_pillars:
                seasonality_score = 1.0 * rule.boost_factor
                break

        # C. Engagement History
        template = topic.get("suggested_template")
        engagement_score = 0.5 # default base (neutral)
        if template and template in format_performance:
            # Scale average QA score (usually 0-10) to 0-1
            engagement_score = format_performance[template] / 10.0

        # D. Freshness
        freshness_score = 1.0 # default if never used
        last_used_str = topic.get("last_used")
        times_used = topic.get("times_used", 0) or 0
        if last_used_str:
            try:
                last_used_date = date.fromisoformat(last_used_str)
                days_since = (run_date - last_used_date).days
                # Scale: 0 days -> 0.0, 90+ days -> 1.0
                freshness_score = min(1.0, days_since / 90.0)
            except Exception:
                freshness_score = 0.5
        
        # Adjust freshness downwards slightly if heavily repeated
        if times_used > 0:
            freshness_score = max(0.0, freshness_score - (times_used * 0.05))

        # E. Trending & Campaign Priority (Future Plugins)
        trending_score = 0.0
        campaign_score = 0.0

        # F. Compute Weighted Sum
        total = (
            weights.pillar_deficit   * pillar_deficit_score +
            weights.seasonality      * seasonality_score    +
            weights.engagement       * engagement_score     +
            weights.freshness        * freshness_score      +
            weights.trending         * trending_score       +
            weights.campaign         * campaign_score
        )

        return TopicScore(
            total=total,
            pillar_deficit=pillar_deficit_score,
            seasonality=seasonality_score,
            engagement_history=engagement_score,
            freshness=freshness_score,
            trending=trending_score,
            campaign_priority=campaign_score
        )

    def _determine_audience(self, pillar: str) -> str:
        mapping = {
            "Educate": "final-year students looking for interview prep tips",
            "Opportunity": "students and recent graduates actively seeking tech roles",
            "Proof": "skeptical students who need proof that the JobInGen process works",
            "Brand": "students seeking to build professional network proof-of-work",
            "Culture": "young developers and college students navigating corporate shifts"
        }
        return mapping.get(pillar, "college students preparing for placements")

    def _determine_suggested_cta(self, pillar: str) -> str:
        mapping = {
            "Educate": "Save this post for your next application prep!",
            "Opportunity": "Apply using the link in our bio today!",
            "Proof": "DM us 'GROWTH' to kickstart your prep!",
            "Brand": "Visit our website to view our placement programs!",
            "Culture": "Share this with a classmate who needs to see this!"
        }
        return mapping.get(pillar, "Follow JobInGen for daily placement tips!")

    def _determine_assets_needed(self, pillar: str) -> List[str]:
        # Always require logo and base background
        base = ["logo_white", "bg_blue_gradient"]
        mapping = {
            "Educate": ["icon_email", "icon_check"],
            "Opportunity": ["icon_check"],
            "Proof": ["icon_check"],
            "Brand": ["icon_check"],
            "Culture": ["icon_email"]
        }
        return base + mapping.get(pillar, [])
