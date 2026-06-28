import asyncio
from src.pipeline.orchestrator import Orchestrator
from src.utils.config_loader import load_config
from src.models.content_state import ContentState

async def test_analytics():
    # Orchestrator takes a string path, not the config object itself
    orchestrator = Orchestrator("config.yaml")
    
    # Initialize DB schema
    await orchestrator.memory.ops_store.initialize()
    
    state = ContentState(date="2026-06-28")
    
    # Insert mock generation history so the JOIN succeeds
    await orchestrator.memory.ops_store.log_run(
        run_id="mock_run_123", run_date="2026-06-27", pillar="Educate", topic_id="t1", 
        template_type="carousel", qa_score=8.5, qa_attempts=1, approved=True, 
        output_path="test", content_state_json="{}", artifact_versions_json="{}", 
        error_log="", llm_cost_usd=0.01, duration_ms=100
    )
    await orchestrator.memory.ops_store.log_run(
        run_id="mock_run_456", run_date="2026-06-25", pillar="Opportunity", topic_id="t2", 
        template_type="job_drop", qa_score=7.0, qa_attempts=1, approved=True, 
        output_path="test", content_state_json="{}", artifact_versions_json="{}", 
        error_log="", llm_cost_usd=0.01, duration_ms=100
    )
    await orchestrator.memory.ops_store.log_run(
        run_id="mock_run_987", run_date="2026-06-27", pillar="Educate", topic_id="t3", 
        template_type="insight_card", qa_score=9.0, qa_attempts=1, approved=True, 
        output_path="test", content_state_json="{}", artifact_versions_json="{}", 
        error_log="", llm_cost_usd=0.01, duration_ms=100
    )
    
    # Trigger Analytics Ingestion
    print("--- Triggering Analytics Ingestion ---")
    await orchestrator.bus.emit("AnalyticsTriggered", state)
    
    # Trigger Learning Loop
    print("\n--- Triggering Learning Loop ---")
    await orchestrator.bus.emit("LearningTriggered", state)
    
    # Verify DB outputs
    print("\n--- Verification ---")
    metrics = await orchestrator.memory.ops_store.get_raw_metrics(days=30)
    print(f"Raw Metrics count: {len(metrics)}")
    for m in metrics:
        print(f" - {m['platform']} | run_id={m['run_id']} | impressions={m['impressions']} | likes={m['likes']} | eng_rate={m['engagement_rate']:.3f}")
        
    insights_t = await orchestrator.memory.ops_store.get_learning_insights("template")
    insights_p = await orchestrator.memory.ops_store.get_learning_insights("pillar")
    
    print("\nLearned Insights (Templates):")
    for row in insights_t:
        print(f" - {row['insight_id']} -> {row['insight_value']} (n={row['sample_size']})")
        
    print("\nLearned Insights (Pillars):")
    for row in insights_p:
        print(f" - {row['insight_id']} -> {row['insight_value']} (n={row['sample_size']})")

if __name__ == "__main__":
    asyncio.run(test_analytics())
