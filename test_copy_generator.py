import asyncio
import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.utils.config_loader import load_config
from src.data.knowledge_store import KnowledgeStore
from src.foundation.artifact_registry import ArtifactRegistry
from src.foundation.llm_gateway import LLMGateway
from src.llm.copy_generator import CopyGenerator
from src.models.content_state import ContentPlan, TopicScore, TemplateSelection, CopyOutput, LLMCallLog

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Overwrite the db path for testing
    config.storage.knowledge_database_path = "data/test_cg_knowledge.db"
    
    # Clean up test DB if it exists
    test_db = Path(config.storage.knowledge_database_path)
    if test_db.exists():
        os.remove(test_db)
        print("Removed existing test database.")

    print("Initializing Knowledge Store & Artifact Registry...")
    ks = KnowledgeStore(config)
    await ks.initialize()
    
    registry = ArtifactRegistry(config)
    
    # Set up LLM Gateway mock
    gateway = MagicMock(spec=LLMGateway)
    
    # Copy Generator
    cg = CopyGenerator(config, registry, gateway, ks)

    # 1. Mock standard CopyOutput response
    valid_copy_json = {
        "hook": "Master the ATS Resume!",
        "slides": [
            {"slide_num": 1, "heading": "ATS Mistake", "body": "Don't use tables.", "visual_note": "X icon"},
            {"slide_num": 2, "heading": "ATS Solution", "body": "Use standard fonts.", "visual_note": "check icon"}
        ],
        "caption": "Resumes don't have to be hard.",
        "hashtags": ["#Resume", "#ATS"],
        "cta": "Get our template!",
        "alt_text": "Carousel on ATS resume rules"
    }
    
    parsed_copy = CopyOutput(**valid_copy_json)
    mock_log = LLMCallLog(module="copy_generator", model="openai/gpt-4o", input_tokens=100, output_tokens=50, cost_usd=0.001, latency_ms=500)
    
    # Configure gateway mock
    async def mock_complete(*args, **kwargs):
        # We can extract user_prompt for assertions
        mock_complete.last_user_prompt = kwargs.get("user_prompt", args[2] if len(args) > 2 else "")
        return parsed_copy, mock_log
        
    gateway.complete = mock_complete

    # 2. Test Carousel Generation (Normal)
    print("\n--- Test Case 1: Standard Copy Generation ---")
    plan1 = ContentPlan(
        pillar="Educate",
        topic="ATS-Friendly Resume Blueprint",
        topic_id="edu_001",
        audience="Students",
        suggested_cta="Save this",
        assets_needed=[],
        dimensions="1080x1080",
        scoring=TopicScore(total=0.0, pillar_deficit=0.0, seasonality=0.0, engagement_history=0.0, freshness=0.0, trending=0.0, campaign_priority=0.0)
    )
    template1 = TemplateSelection(
        template_type="carousel",
        slide_count=5,
        prompt_key="copywriter_carousel",
        layout_hints={"slide_1": "Intro"}
    )
    
    res, log = await cg.generate(plan1, template1)
    
    print(f"Hook generated: {res.hook}")
    print(f"Captions: {res.caption}")
    assert res.hook == "Master the ATS Resume!"
    assert log.model == "openai/gpt-4o"
    
    # Assert compile prompt content
    last_prompt = gateway.complete.last_user_prompt
    assert "TARGET PILLAR: Educate" in last_prompt
    assert "ATS-Friendly Resume Blueprint" in last_prompt
    assert "SUGGESTED CTA: Save this" in last_prompt
    assert "TOTAL SLIDES REQUIRED: 5" in last_prompt

    # 3. Test Opportunity Generation with Job Drop (Context Seeding)
    print("\n--- Test Case 2: Copy Generation with Database Job Seeding ---")
    plan2 = ContentPlan(
        pillar="Opportunity",
        topic="Software Engineering Internship Openings",
        topic_id="opp_001",
        audience="Graduates",
        suggested_cta="Apply",
        assets_needed=[],
        dimensions="1080x1350",
        scoring=TopicScore(total=0.0, pillar_deficit=0.0, seasonality=0.0, engagement_history=0.0, freshness=0.0, trending=0.0, campaign_priority=0.0)
    )
    template2 = TemplateSelection(
        template_type="job_drop",
        slide_count=1,
        prompt_key="copywriter_jobdrop",
        layout_hints={"layout": "Job grid"}
    )
    
    # Verify job drop gets jobs context
    _, _ = await cg.generate(plan2, template2)
    last_prompt2 = gateway.complete.last_user_prompt
    print("User prompt snippet with jobs context:")
    print("-" * 40)
    print("\n".join(last_prompt2.split("\n")[:15]))
    print("-" * 40)
    
    assert "ACTIVE FEATURED JOBS FROM DATABASE:" in last_prompt2
    assert "Company: Amazon" in last_prompt2
    assert "Company: Google" in last_prompt2

    # 4. Test Copy Generation with QA critic feedback
    print("\n--- Test Case 3: Retrying with critic feedback ---")
    # Assert QA feedback is appended
    critic_feedback = "The hook was missing emoji. Add a red circle emoji."
    _, _ = await cg.generate(plan1, template1, feedback=critic_feedback)
    last_prompt3 = gateway.complete.last_user_prompt
    
    assert "⚠️ QA CRITIC FEEDBACK FROM PREVIOUS ATTEMPT" in last_prompt3
    assert critic_feedback in last_prompt3
    print("Critic feedback successfully injected!")

    # Clean up test DB
    if test_db.exists():
        os.remove(test_db)
        print("Cleaned up test database.")
        
    print("\nSUCCESS: Copy Generator verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
