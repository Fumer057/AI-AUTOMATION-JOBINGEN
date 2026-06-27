import asyncio
import sys
import os
from pathlib import Path
from datetime import date
from src.utils.config_loader import load_config
from src.data.operational_store import OperationalStore
from src.data.memory import Memory
from src.models.content_state import (
    ContentState, PipelineStatus, ContentPlan, TopicScore,
    TemplateSelection, CopyOutput, SlideContent, QAReport, LLMCallLog
)

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Overwrite the db path for testing
    config.storage.operational_database_path = "data/test_memory_db.db"
    
    # Clean up test DB if it exists
    test_db = Path(config.storage.operational_database_path)
    if test_db.exists():
        os.remove(test_db)
        print("Removed existing test database.")

    print("Initializing Operational Store...")
    ops = OperationalStore(config)
    await ops.initialize()
    
    print("Initializing Memory Module...")
    mem = Memory(ops)
    
    # 1. Construct a mock ContentState object representing a successful pipeline run
    state = ContentState(run_id="run_100", date=date.today())
    state.status = PipelineStatus.DELIVERED
    
    state.plan = ContentPlan(
        pillar="Educate",
        topic="ATS Resume tips",
        topic_id="edu_001",
        audience="Students",
        suggested_cta="Save this",
        assets_needed=["logo"],
        dimensions="1080x1080",
        scoring=TopicScore(
            total=1.0, pillar_deficit=0.4, seasonality=0.1,
            engagement_history=0.1, freshness=0.2, trending=0.1, campaign_priority=0.1
        )
    )
    
    state.template = TemplateSelection(
        template_type="carousel",
        slide_count=3,
        prompt_key="copywriter_carousel_v2",
        layout_hints={}
    )
    
    state.generated_copy = CopyOutput(
        hook="Avoid this!",
        slides=[SlideContent(slide_num=1, heading="Slide A", body="Text", visual_note="")],
        caption="Sample Caption",
        hashtags=["#Career"],
        cta="Save it",
        alt_text="Alt text"
    )
    
    state.qa = QAReport(
        overall_score=8.8,
        passed=True,
        attempt=1,
        scores={"brand": 9.0},
        feedback="Great",
        rubric_version="v2"
    )
    
    state.qa_attempts = 1
    state.output_dir = "output/test_run/"
    state.total_duration_ms = 35000
    state.artifact_versions = {"planner_prompt": "v4"}
    
    # Add some mock LLM call logs
    state.llm_calls = [
        LLMCallLog(module="generator", model="openai/gpt-4o", input_tokens=1000, output_tokens=500, cost_usd=0.0075, latency_ms=1800),
        LLMCallLog(module="critic", model="openai/gpt-4o", input_tokens=800, output_tokens=300, cost_usd=0.0045, latency_ms=1200)
    ]
    
    # 2. Test Logging Run from ContentState
    print("\n--- Test Case 1: Log Full ContentState ---")
    await mem.log_run(state)
    
    # Verify records exist in DB
    runs = await ops.get_recent_runs(limit=1)
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run_100"
    assert runs[0]["approved"] == 1
    assert runs[0]["llm_cost_usd"] == 0.012  # 0.0075 + 0.0045
    print("ContentState logged and summarized accurately!")

    # 3. Test Cooldown Verification
    print("\n--- Test Case 2: Cooldown Checks ---")
    on_cooldown = await mem.is_topic_on_cooldown("edu_001", cooldown_days=30)
    not_on_cooldown = await mem.is_topic_on_cooldown("edu_999", cooldown_days=30)
    
    assert on_cooldown is True
    assert not_on_cooldown is False
    print("Cooldown checks validated successfully!")

    # 4. Test Topic ID memory fetching
    print("\n--- Test Case 3: Get Recent Topic IDs ---")
    recent_ids = await mem.get_recent_topic_ids(days=7)
    assert "edu_001" in recent_ids
    assert len(recent_ids) == 1
    print(f"Recent topic IDs set: {recent_ids}")

    # 5. Test Pillar Ratios
    print("\n--- Test Case 4: Get Pillar Distribution Ratios ---")
    dist = await mem.get_pillar_distribution(days=7)
    print(f"Pillar ratios in memory: {dist}")
    assert dist.get("Educate") == 1.0  # Only 1 run, which is Educate

    # 6. Test Format Performance tracking
    print("\n--- Test Case 5: Get Layout Formats Performance ---")
    perf = await mem.get_format_performance()
    print(f"Layout performance: {perf}")
    assert perf.get("carousel") == 8.8
    
    # Clean up test DB
    if test_db.exists():
        os.remove(test_db)
        print("Cleaned up test database.")
        
    print("\nSUCCESS: Memory Module verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
