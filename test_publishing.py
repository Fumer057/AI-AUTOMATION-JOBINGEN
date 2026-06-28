import asyncio
import os
from src.pipeline.orchestrator import Orchestrator
from src.models.content_state import ContentState, ContentPlan, TemplateSelection, CopyOutput, SlideContent

async def test_publishing():
    # Do not set any API keys so they all run in DRY_RUN / Mock modes
    
    orchestrator = Orchestrator("config.yaml")
    await orchestrator.initialize()
    
    # Manually create a ContentState that is in DELIVERED status
    state = ContentState(date="2026-06-28", run_id="test_publish_01")
    
    # Mock Planner Output
    from src.models.content_state import TopicScore
    state.plan = ContentPlan(
        pillar="Community",
        topic="Meme about debugging",
        topic_id="meme_topic",
        audience="Developers",
        suggested_cta="Follow for more",
        assets_needed=[],
        dimensions="1080x1080",
        scoring=TopicScore(total=95.0, pillar_deficit=0, seasonality=0, engagement_history=0, freshness=0, trending=0, campaign_priority=0)
    )
    
    # Select meme template
    state.template = TemplateSelection(
        template_type="meme",
        slide_count=1,
        prompt_key="meme_v1",
        layout_hints={}
    )
    
    # Mock CopyOutput
    state.generated_copy = CopyOutput(
        hook="When the code works...",
        slides=[
            SlideContent(slide_num=1, heading="Wait what?", body="When the code compiles on the first try and you have no idea why.", visual_note="Confused dev")
        ],
        caption="Relatable content.",
        hashtags=["#coding", "#dev"],
        cta="Drop a like!",
        alt_text="A meme about coding",
        image_prompt="A dramatic movie poster of a confused software engineer staring at a green terminal"
    )
    
    # Mock Image Paths (what Playwright would return)
    state.image_paths = [
        r"C:\Users\risha\OneDrive\Desktop\AI AUTOMATION JOBINGEN\output\test_publish_01\slide_01.png"
    ]
    
    print("--- Firing RenderComplete Event (Triggers Publishing & Notifications) ---")
    await orchestrator.bus.emit("RenderComplete", state)

if __name__ == "__main__":
    asyncio.run(test_publishing())
