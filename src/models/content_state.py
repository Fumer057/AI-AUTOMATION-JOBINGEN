from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from enum import Enum
from uuid import uuid4

class PipelineStatus(str, Enum):
    INITIALIZED  = "initialized"
    PLANNED      = "planned"
    TEMPLATE_SET = "template_set"
    DRAFTED      = "drafted"
    QA_PASSED    = "qa_passed"
    QA_FAILED    = "qa_failed"
    RENDER_SPEC  = "render_spec_built"
    RENDERED     = "rendered"
    DELIVERED    = "delivered"
    FAILED       = "failed"

class TopicScore(BaseModel):
    """Output of the Planner scoring engine."""
    total: float
    pillar_deficit: float
    seasonality: float
    engagement_history: float
    freshness: float
    trending: float
    campaign_priority: float

class ContentPlan(BaseModel):
    pillar: str
    topic: str
    topic_id: str
    audience: str
    suggested_cta: str
    assets_needed: list[str]
    dimensions: str                        # "1080x1080"
    scoring: TopicScore

class TemplateSelection(BaseModel):
    template_type: str                     # "carousel", "job_drop", etc.
    slide_count: int
    prompt_key: str                        # e.g., "copywriter_carousel_v2"
    layout_hints: dict

class SlideContent(BaseModel):
    slide_num: int
    heading: str
    body: str
    visual_note: str

class CopyOutput(BaseModel):
    hook: str
    slides: list[SlideContent]
    caption: str
    hashtags: list[str]
    cta: str
    alt_text: str
    image_prompt: Optional[str] = None

class QAReport(BaseModel):
    overall_score: float
    passed: bool
    attempt: int
    scores: dict[str, float] = Field(default_factory=dict, description="Scores out of 10 for each rubric dimension")
    feedback: str
    rubric_version: str

class SlideRenderData(BaseModel):
    slide_num: int
    heading: str
    body: str
    layout: str
    accent_color: Optional[str] = None
    icon: Optional[str] = None

class RenderSpec(BaseModel):
    """Deterministic input to the Renderer."""
    template: str
    template_version: str                  
    dimensions: dict
    brand_colors: dict
    font_family: str
    logo_path: str
    assets: dict[str, str]
    dynamic_assets: dict[str, str] = Field(default_factory=dict)
    slides: list[SlideRenderData]

class LLMCallLog(BaseModel):
    module: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    cached: bool = False
    strategy_used: str = "native"
    repair_attempts: int = 0
    validation_failures: int = 0
    success: bool = True
    exception_type: Optional[str] = None
    prompt_version: Optional[str] = None

class ContentState(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    date: date
    status: PipelineStatus = PipelineStatus.INITIALIZED
    started_at: datetime = Field(default_factory=datetime.utcnow)

    # Step 1: Planner
    plan: Optional[ContentPlan] = None

    # Step 2: Template Selector
    template: Optional[TemplateSelection] = None

    # Step 3: Generator
    generated_copy: Optional[CopyOutput] = None

    # Step 4: Critic
    qa: Optional[QAReport] = None
    qa_attempts: int = 0

    # Step 5: RenderSpec Builder
    render_spec: Optional[RenderSpec] = None
    dynamic_assets: dict[str, str] = Field(default_factory=dict)

    # Step 6: Renderer
    image_paths: list[str] = Field(default_factory=list)

    # Step 7: Queue
    output_dir: Optional[str] = None
    pack_manifest_path: Optional[str] = None

    # Observability
    llm_calls: list[LLMCallLog] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    total_duration_ms: Optional[int] = None

    # Artifact versions used (for reproducibility)
    artifact_versions: dict[str, str] = Field(default_factory=dict)
