from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import yaml
from pathlib import Path

class RegistryActiveConfig(BaseModel):
    prompts: Dict[str, str]
    rubrics: Dict[str, str]
    schemas: Dict[str, str]
    templates: Dict[str, str]

class RegistryConfig(BaseModel):
    dir: str
    active: RegistryActiveConfig

class AssetsConfig(BaseModel):
    dir: str
    manifest: str

class RateLimitConfig(BaseModel):
    rpm: int
    tpm: int

class CacheConfig(BaseModel):
    enabled: bool
    ttl_seconds: int

class ProviderConfig(BaseModel):
    provider: str
    model: str

class LLMTemperatures(BaseModel):
    generate: float
    retry: float
    critic: float
    planner: float

class LLMMaxTokens(BaseModel):
    single: int
    carousel: int

class LLMConfig(BaseModel):
    primary: ProviderConfig
    fallback: ProviderConfig
    temperatures: LLMTemperatures
    max_tokens: LLMMaxTokens
    timeout_seconds: int
    max_api_retries: int
    cache: CacheConfig
    rate_limit: Dict[str, RateLimitConfig]

class BrandColors(BaseModel):
    primary: str
    white: str
    accent: str
    bg_dark: str
    text: str

class BrandConfig(BaseModel):
    colors: BrandColors
    font_heading: str
    font_body: str

class ScoreWeights(BaseModel):
    pillar_deficit: float
    seasonality: float
    engagement: float
    freshness: float
    trending: float
    campaign: float

class SeasonalityRule(BaseModel):
    months: List[int]
    boost_pillars: List[str]
    boost_factor: float

class PlannerConfig(BaseModel):
    pillars: Dict[str, float]
    history_window_days: int
    topic_cooldown_days: int
    score_weights: ScoreWeights
    seasonality_rules: List[SeasonalityRule]
    template_compatibility: Dict[str, List[str]]

class CriticRubricWeights(BaseModel):
    brand_voice: float
    hook_strength: float
    value_density: float
    cta_quality: float
    no_cringe: float
    hashtag_caption: float

class CriticConfig(BaseModel):
    pass_threshold: float
    max_retries: int
    rubric_weights: CriticRubricWeights

class DimensionsConfig(BaseModel):
    width: int
    height: int

class RendererConfig(BaseModel):
    browser: str
    dimensions: Dict[str, DimensionsConfig]
    templates_dir: str
    output_format: str
    quality: int

class StorageConfig(BaseModel):
    knowledge_database_path: str
    operational_database_path: str
    output_dir: str
    seed_data_dir: str
    checkpoint_enabled: bool

class SlackConfig(BaseModel):
    enabled: bool
    webhook_url: Optional[str] = None

class WhatsAppConfig(BaseModel):
    enabled: bool
    api_url: Optional[str] = None

class NotionConfig(BaseModel):
    enabled: bool
    api_key: Optional[str] = None
    database_id: Optional[str] = None

class NotificationsConfig(BaseModel):
    slack: SlackConfig
    whatsapp: WhatsAppConfig
    notion: NotionConfig

class ScheduleConfig(BaseModel):
    cron: str
    timezone: str

class PluginConfig(BaseModel):
    enabled: bool

class PluginsConfig(BaseModel):
    linkedin_publish: PluginConfig
    job_ingestion: PluginConfig
    instagram_publish: PluginConfig
    trend_ingestion: PluginConfig
    analytics_loop: PluginConfig

class LinkedInAuthConfig(BaseModel):
    access_token: str
    organization_id: str

class InstagramAuthConfig(BaseModel):
    access_token: str
    account_id: str

class SocialAuthConfig(BaseModel):
    linkedin: LinkedInAuthConfig
    instagram: InstagramAuthConfig

class AppConfig(BaseModel):
    registry: RegistryConfig
    assets: AssetsConfig
    llm: LLMConfig
    brand: BrandConfig
    planner: PlannerConfig
    critic: CriticConfig
    renderer: RendererConfig
    storage: StorageConfig
    notifications: NotificationsConfig
    schedule: ScheduleConfig
    plugins: PluginsConfig
    social_auth: SocialAuthConfig

def load_config(path: str = "config.yaml") -> AppConfig:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    # Auto-detect and adapt LLM provider dynamically based on environment keys
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if "llm" in data:
        if openai_key and not gemini_key:
            data["llm"]["primary"]["provider"] = "openai"
            data["llm"]["primary"]["model"] = "gpt-5.5"
            data["llm"]["fallback"]["provider"] = "openai"
            data["llm"]["fallback"]["model"] = "gpt-5.4-mini"
        elif gemini_key and not openai_key:
            data["llm"]["primary"]["provider"] = "gemini"
            data["llm"]["primary"]["model"] = "gemini-3.5-flash"
            data["llm"]["fallback"]["provider"] = "gemini"
            data["llm"]["fallback"]["model"] = "gemini-3.5-flash"
            
    return AppConfig(**data)
