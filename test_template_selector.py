import asyncio
import sys
import os
from pathlib import Path
from src.utils.config_loader import load_config
from src.data.knowledge_store import KnowledgeStore
from src.foundation.artifact_registry import ArtifactRegistry
from src.intelligence.template_selector import TemplateSelector
from src.models.content_state import ContentPlan, TopicScore

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Overwrite the db path for testing
    config.storage.knowledge_database_path = "data/test_ts_knowledge.db"
    
    # Clean up test DB if it exists
    test_db = Path(config.storage.knowledge_database_path)
    if test_db.exists():
        os.remove(test_db)
        print("Removed existing test database.")

    print("Initializing Knowledge Store & Artifact Registry...")
    ks = KnowledgeStore(config)
    await ks.initialize()
    
    registry = ArtifactRegistry(config)
    
    # Initialize Template Selector
    ts = TemplateSelector(config, registry, ks)

    # 1. Test Normal Template Selection (Topic 'edu_001' suggests 'carousel' which is compatible with 'Educate')
    print("\n--- Test Case 1: Select Compatible Suggested Template ---")
    plan1 = ContentPlan(
        pillar="Educate",
        topic="ATS Resume Blueprint",
        topic_id="edu_001",
        audience="Students",
        suggested_cta="Save this",
        assets_needed=[],
        dimensions="1080x1080",
        scoring=TopicScore(total=0.0, pillar_deficit=0.0, seasonality=0.0, engagement_history=0.0, freshness=0.0, trending=0.0, campaign_priority=0.0)
    )
    selection1 = await ts.select(plan1)
    print(f"Pillar: Educate, Topic ID: edu_001")
    print(f"Selected: {selection1.template_type}")
    print(f"Slide Count: {selection1.slide_count}")
    print(f"Prompt Key: {selection1.prompt_key}")
    
    assert selection1.template_type == "carousel"
    assert selection1.slide_count == 5
    assert selection1.prompt_key == "copywriter_carousel"
    assert "slide_1" in selection1.layout_hints

    # 2. Test Fallback Selection (Topic 'edu_001' has compatible suggested, let's create a custom topic that suggests 'job_drop' for 'Educate' (invalid))
    print("\n--- Test Case 2: Fallback on Incompatible Template ---")
    # We will test using opp_001 (which suggests 'job_drop' but we'll plan it under 'Educate' to force fallback)
    plan2 = ContentPlan(
        pillar="Educate",
        topic="Software Engineering Internship Openings",
        topic_id="opp_001",  # opp_001 suggests 'job_drop' which is incompatible with 'Educate'
        audience="Students",
        suggested_cta="Apply",
        assets_needed=[],
        dimensions="1080x1080",
        scoring=TopicScore(total=0.0, pillar_deficit=0.0, seasonality=0.0, engagement_history=0.0, freshness=0.0, trending=0.0, campaign_priority=0.0)
    )
    selection2 = await ts.select(plan2)
    print(f"Pillar: Educate, Topic ID: opp_001 (suggests job_drop)")
    print(f"Fallback Selected: {selection2.template_type}")
    
    # Educate compatible: ["carousel", "insight_card", "comparison", "mentor_spotlight", "meme"]
    # Since 'job_drop' is not in this list, it should fall back to the first compatible: 'carousel'
    assert selection2.template_type == "carousel"
    assert selection2.slide_count == 5
    assert selection2.prompt_key == "copywriter_carousel"

    # 3. Test Opportunity Selections (Topic 'opp_001' planned under 'Opportunity', suggests 'job_drop' (compatible))
    print("\n--- Test Case 3: Select Compatible Template for Opportunity ---")
    plan3 = ContentPlan(
        pillar="Opportunity",
        topic="Software Engineering Internship Openings",
        topic_id="opp_001",
        audience="Graduates",
        suggested_cta="Apply",
        assets_needed=[],
        dimensions="1080x1350",
        scoring=TopicScore(total=0.0, pillar_deficit=0.0, seasonality=0.0, engagement_history=0.0, freshness=0.0, trending=0.0, campaign_priority=0.0)
    )
    selection3 = await ts.select(plan3)
    print(f"Pillar: Opportunity, Topic ID: opp_001")
    print(f"Selected: {selection3.template_type}")
    print(f"Slide Count: {selection3.slide_count}")
    print(f"Prompt Key: {selection3.prompt_key}")
    
    assert selection3.template_type == "job_drop"
    assert selection3.slide_count == 1
    assert selection3.prompt_key == "copywriter_jobdrop"
    
    # Clean up test DB
    if test_db.exists():
        os.remove(test_db)
        print("Cleaned up test database.")
        
    print("\nSUCCESS: Template Selector verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
