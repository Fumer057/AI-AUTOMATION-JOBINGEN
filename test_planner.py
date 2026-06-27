import asyncio
import sys
import os
from pathlib import Path
from datetime import date
from src.utils.config_loader import load_config
from src.data.knowledge_store import KnowledgeStore
from src.data.operational_store import OperationalStore
from src.data.memory import Memory
from src.intelligence.planner import ContentPlanner
from src.models.content_state import ContentState

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Overwrite the db paths for testing
    config.storage.knowledge_database_path = "data/test_plan_knowledge.db"
    config.storage.operational_database_path = "data/test_plan_operational.db"
    
    # Clean up test DBs if they exist
    for db_path in [config.storage.knowledge_database_path, config.storage.operational_database_path]:
        path = Path(db_path)
        if path.exists():
            os.remove(path)
            print(f"Removed existing test database: {db_path}")

    print("Initializing Knowledge & Operational Stores...")
    ks = KnowledgeStore(config)
    await ks.initialize()
    
    ops = OperationalStore(config)
    await ops.initialize()
    
    mem = Memory(ops)
    
    # Pre-populate operational history to simulate a deficit:
    # We will log several runs for all pillars except 'Educate'.
    # This should create a deficit for 'Educate' and force the planner to pick an Educate topic.
    print("Simulating historical runs for Opportunity, Proof, Brand, and Culture...")
    pillars_to_run = ["Opportunity", "Proof", "Brand", "Culture"]
    for i, pillar in enumerate(pillars_to_run):
        await ops.log_run(
            run_id=f"run_hist_{i}",
            run_date="2026-06-25",
            pillar=pillar,
            topic_id=f"topic_{pillar.lower()}",
            template_type="insight_card",
            qa_score=8.0,
            qa_attempts=1,
            approved=True,
            output_path="",
            content_state_json="{}",
            artifact_versions_json="{}",
            error_log=None,
            llm_cost_usd=0.01,
            duration_ms=20000
        )
    
    # Initialize Planner
    planner = ContentPlanner(config, registry=None, memory=mem, knowledge_store=ks)
    
    # Create Plan for today (June 27)
    state = ContentState(date=date(2026, 6, 27))
    
    print("\n--- Test Case 1: Deficit Selection (Should pick 'Educate') ---")
    plan = await planner.create_plan(state)
    print(f"Selected Pillar: {plan.pillar}")
    print(f"Selected Topic: {plan.topic} (ID: {plan.topic_id})")
    print(f"Audience: {plan.audience}")
    print(f"Scoring breakdown: Total={plan.scoring.total:.4f}, Deficit={plan.scoring.pillar_deficit:.4f}, Freshness={plan.scoring.freshness:.4f}")
    
    assert plan.pillar == "Educate", f"Expected Educate pillar due to deficit, got {plan.pillar}"
    assert plan.topic_id in ["edu_001", "edu_002", "edu_003"]
    assert "logo_white" in plan.assets_needed
    assert "bg_blue_gradient" in plan.assets_needed
    
    # Mark the picked topic as used and verify it's not chosen again next time
    await ks.mark_topic_used(plan.topic_id, "2026-06-27")
    # Log run to memory
    state.plan = plan
    await mem.log_run(state)
    
    print("\n--- Test Case 2: Cooldown & Cooldown Bypass (Should pick a different Educate topic) ---")
    state2 = ContentState(date=date(2026, 6, 28))
    plan2 = await planner.create_plan(state2)
    print(f"Selected Topic 2: {plan2.topic} (ID: {plan2.topic_id})")
    assert plan2.topic_id != plan.topic_id, "Winner topic ID should be different because the previous is on cooldown!"
    
    # Clean up test DBs
    for db_path in [config.storage.knowledge_database_path, config.storage.operational_database_path]:
        path = Path(db_path)
        if path.exists():
            os.remove(path)
            print(f"Cleaned up test database: {db_path}")
            
    print("\nSUCCESS: Content Planner verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
