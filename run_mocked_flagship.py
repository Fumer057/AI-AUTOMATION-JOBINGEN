import asyncio
from datetime import date
import structlog
from src.pipeline.orchestrator import Orchestrator
from src.models.content_state import ContentState, ContentPlan, TopicScore, TemplateSelection, CopyOutput, QAReport, SlideContent, LLMCallLog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=True)
    ]
)
logger = structlog.get_logger(__name__)

async def main():
    logger.info("Initializing Orchestrator for Flagship Mock Run...")
    orchestrator = Orchestrator("config.yaml")
    await orchestrator.initialize()
    
    # 1. Mock Planner
    async def mock_create_plan(*args, **kwargs):
        return ContentPlan.model_construct(
            pillar="Opportunity",
            topic="JobInGen Flagship Training: Full Stack & Data Analytics",
            topic_id="flagship-training",
            audience="Job seekers and professionals",
            suggested_cta="Register via link in comments!",
            assets_needed=[],
            dimensions="1080x1350",
            scoring=TopicScore.model_construct(total=100.0, pillar_deficit=0, seasonality=0, engagement_history=0, freshness=0, trending=0, campaign_priority=100.0)
        )
    orchestrator.planner.create_plan = mock_create_plan
    
    # 2. Mock Template Selector
    async def mock_select_template(*args, **kwargs):
        return TemplateSelection.model_construct(
            template_type="carousel",
            slide_count=4,
            prompt_key="copywriter_carousel",
            layout_hints={}
        )
    orchestrator.template_selector.select = mock_select_template
    
    # 3. Mock Copy Generator
    async def mock_generate(*args, **kwargs):
        copy = CopyOutput.model_construct(
            hook="Stop applying blindly. Learn what actually gets you hired.",
            slides=[
                SlideContent.model_construct(
                    slide_num=1,
                    heading="The Flagship Program",
                    body="We noticed a massive gap between what bootcamp grads know and what top tech companies expect.\n\nSo we built the JobInGen Flagship Training Program.\n\nNot just courses. A complete ecosystem to land you a job.",
                    visual_note="Bold and clean."
                ),
                SlideContent.model_construct(
                    slide_num=2,
                    heading="Two High-Demand Tracks",
                    body="Choose your weapon:\n\n1️⃣ **Full Stack Web Development** (React, Node, DBs)\n2️⃣ **Data Analytics** (SQL, Python, PowerBI)\n\nMaster the exact tech stacks hiring managers are looking for right now.",
                    visual_note="Bullet points"
                ),
                SlideContent.model_construct(
                    slide_num=3,
                    heading="More Than Just Code",
                    body="✅ **Live Mentorship** from industry experts\n✅ **Hackathons** to build real-world proof\n✅ **Placement Assistance** to get you in the door\n\nStop learning in a vacuum. Start building a career.",
                    visual_note="Checkmarks"
                ),
                SlideContent.model_construct(
                    slide_num=4,
                    heading="Ready to Level Up?",
                    body="Seats are strictly limited for the next cohort.\n\nDon't let another month pass you by.\n\nClick the link in the comments to claim your spot and transform your career trajectory.",
                    visual_note="CTA style"
                )
            ],
            caption="The tech job market is brutal right now. But the people with the RIGHT skills and the RIGHT proof of work are still getting hired every single day. \n\nThat's exactly why we created the JobInGen Flagship Training Program. \n\nWe cover Data Analytics and Full Stack Web Dev. We give you live mentorship. We host hackathons. And we help you with placements. \n\nLink in comments to join the next cohort! 👇\n\n#JobInGen #DataAnalytics #FullStack #TechCareers",
            hashtags=["#JobInGen", "#DataAnalytics", "#FullStack"],
            cta="Register via link in comments!",
            alt_text="Carousel about JobInGen Flagship Training"
        )
        dummy_log = LLMCallLog(module="copy_generator", model="mock", input_tokens=0, output_tokens=0, cost_usd=0.0, latency_ms=0)
        return copy, dummy_log
    orchestrator.generator.generate = mock_generate
    
    # 4. Mock QA Pass
    async def mock_qa(*args, **kwargs):
        report = QAReport.model_construct(
            overall_score=10.0,
            passed=True,
            attempt=1,
            scores={"clarity": 10.0, "impact": 10.0},
            feedback="Looks amazing!",
            rubric_version="v2"
        )
        dummy_log = LLMCallLog(module="critic", model="mock", input_tokens=0, output_tokens=0, cost_usd=0.0, latency_ms=0)
        return report, dummy_log
    orchestrator.qa.evaluate = mock_qa
    
    # Let the rest of the pipeline run natively!
    logger.info("Starting Pipeline...")
    final_state = await orchestrator.run()
    logger.info("MOCKED PIPELINE FINISHED", output_dir=final_state.output_dir)

if __name__ == "__main__":
    asyncio.run(main())
