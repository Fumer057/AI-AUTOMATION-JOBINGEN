import asyncio
import sys
import os
from pathlib import Path
from src.utils.config_loader import load_config
from src.data.operational_store import OperationalStore
from src.foundation.metrics_collector import Metric

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Overwrite the db path for testing
    config.storage.operational_database_path = "data/test_operational.db"
    
    # Clean up test DB if it exists
    test_db = Path(config.storage.operational_database_path)
    if test_db.exists():
        os.remove(test_db)
        print("Removed existing test database.")

    print("Initializing Operational Store...")
    ops = OperationalStore(config)
    await ops.initialize()
    
    run_id = "test_run_001"
    run_date = "2026-06-27"
    
    # 1. Log a pipeline run
    print("\n--- Test Case 1: Log Run History ---")
    await ops.log_run(
        run_id=run_id,
        run_date=run_date,
        pillar="Educate",
        topic_id="edu_001",
        template_type="carousel",
        qa_score=8.5,
        qa_attempts=1,
        approved=True,
        output_path="output/2026-06-27/",
        content_state_json="{}",
        artifact_versions_json="{}",
        error_log=None,
        llm_cost_usd=0.0123,
        duration_ms=45200
    )
    
    recent = await ops.get_recent_runs(limit=1)
    assert len(recent) == 1
    assert recent[0]["run_id"] == run_id
    assert recent[0]["qa_score"] == 8.5
    print("Run history logged and retrieved successfully!")
    
    # 2. Log an LLM call
    print("\n--- Test Case 2: Log LLM Call ---")
    await ops.log_llm_call(
        run_id=run_id,
        module="generator",
        model="openai/gpt-4o",
        input_tokens=1500,
        output_tokens=800,
        cost_usd=0.0115,
        latency_ms=2500,
        cached=False,
        prompt_hash="xyz123"
    )
    print("LLM call logged successfully!")

    # 3. Log metrics
    print("\n--- Test Case 3: Write Pipeline Metrics ---")
    metrics = [
        Metric(name="pipeline.duration_ms", value=45200.0),
        Metric(name="llm.cost_usd", value=0.0123)
    ]
    await ops.write_metrics(run_id=run_id, metrics=metrics)
    print("Pipeline metrics logged successfully!")
    
    # 4. Run calculations
    print("\n--- Test Case 4: Execute Analytical Queries ---")
    counts = await ops.get_pillar_counts(since_date="2026-06-01")
    avg_score = await ops.get_average_qa_score(days=7)
    total_cost = await ops.get_total_cost(days=7)
    
    print(f"Pillar counts: {counts}")
    print(f"Average QA Score: {avg_score}")
    print(f"Total Cost: ${total_cost:.5f}")
    
    assert counts.get("Educate") == 1
    assert avg_score == 8.5
    assert total_cost == 0.0123
    
    # Clean up test DB after test
    if test_db.exists():
        os.remove(test_db)
        print("Cleaned up test database.")
        
    print("\nSUCCESS: Operational Store verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
