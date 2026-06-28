import asyncio
import os
from src.pipeline.orchestrator import Orchestrator
from src.models.content_state import ContentState, ContentPlan, TemplateSelection, CopyOutput, SlideContent, TopicScore

async def test_rendering():
    # Do not set GEMINI_API_KEY so it triggers the fallback local dummy image generator
    
    orchestrator = Orchestrator("config.yaml")
    await orchestrator.initialize()
    
    # Manually create a ContentState that is in QA_PASSED status
    state = ContentState(date="2026-06-28", run_id="test_render_01")
    
    # Mock Planner Output
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
    
    print("--- Firing ContentApproved Event (Triggers Gemini Image Generator) ---")
    await orchestrator.bus.emit("ContentApproved", state)
    
    print(f"\nDynamic Assets after generation: {state.dynamic_assets}")
    
    print("\n--- Running RenderSpec Builder ---")
    state.render_spec = orchestrator.rs_builder.build(state.plan, state.template, state.generated_copy, state.dynamic_assets)
    
    print("\n--- Firing Playwright Renderer ---")
    image_paths = await orchestrator.renderer.render(state.render_spec, state.run_id)
    
    print(f"\nRender successful! Output paths:")
    for p in image_paths:
        print(p)

if __name__ == "__main__":
    asyncio.run(test_rendering())
