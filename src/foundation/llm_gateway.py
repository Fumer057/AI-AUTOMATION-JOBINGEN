import time
import hashlib
import json
import asyncio
import re
from typing import Type, Tuple, Optional, Dict, Any, List
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass
import litellm
from cachetools import TTLCache
import structlog

from src.models.content_state import LLMCallLog
from src.utils.config_loader import AppConfig

logger = structlog.get_logger(__name__)

# --- Data Models ---

class ModelCapabilities(BaseModel):
    native_json: bool
    markdown: bool
    repair: bool

@dataclass
class StrategyResult:
    raw_response: Any
    parsed_object: Optional[BaseModel]
    strategy: str
    repair_attempts: int
    validation_failures: int

# --- Registries ---

class CapabilityRegistry:
    def __init__(self, config_capabilities: Dict[str, dict] = None):
        self._capabilities = {
            "gemini-1.5-flash": ModelCapabilities(native_json=True, markdown=True, repair=True),
            "gemini/gemini-1.5-flash": ModelCapabilities(native_json=True, markdown=True, repair=True),
            "claude-3-5-sonnet-20240620": ModelCapabilities(native_json=True, markdown=True, repair=True),
            "anthropic/claude-3-5-sonnet-20240620": ModelCapabilities(native_json=True, markdown=True, repair=True),
            "antigravity-preview-05-2026": ModelCapabilities(native_json=False, markdown=True, repair=True),
            "gemini/antigravity-preview-05-2026": ModelCapabilities(native_json=False, markdown=True, repair=True),
        }
        if config_capabilities:
            for k, v in config_capabilities.items():
                self._capabilities[k] = ModelCapabilities(**v)

    def get(self, model: str) -> ModelCapabilities:
        return self._capabilities.get(model, ModelCapabilities(native_json=True, markdown=True, repair=True))


# --- Circuit Breaker ---

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 10, ttl_seconds: int = 300):
        self.threshold = failure_threshold
        # Stores model_strategy -> failure count
        self._failures = TTLCache(maxsize=1000, ttl=ttl_seconds)

    def record_failure(self, model: str, strategy: str):
        key = f"{model}::{strategy}"
        count = self._failures.get(key, 0)
        self._failures[key] = count + 1

    def record_success(self, model: str, strategy: str):
        key = f"{model}::{strategy}"
        if key in self._failures:
            del self._failures[key]

    def is_open(self, model: str, strategy: str) -> bool:
        key = f"{model}::{strategy}"
        return self._failures.get(key, 0) >= self.threshold


# --- Providers ---

class StructuredOutputProvider:
    name: str = "base"
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        output_model: Type[BaseModel],
        temperature: float,
        max_tokens: int,
        timeout: int,
        previous_result: Optional[StrategyResult] = None
    ) -> StrategyResult:
        raise NotImplementedError()
        
    async def _api_call_with_backoff(self, func, attempt=1, max_retries=3):
        try:
            return await func()
        except (litellm.RateLimitError, litellm.Timeout, litellm.APIConnectionError) as e:
            if attempt >= max_retries:
                raise e
            # Exponential backoff (1s, 2s, 4s...)
            await asyncio.sleep(2 ** (attempt - 1))
            return await self._api_call_with_backoff(func, attempt + 1, max_retries)


class NativeJSONProvider(StructuredOutputProvider):
    name = "native"
    
    async def generate(self, system_prompt: str, user_prompt: str, model: str, output_model: Type[BaseModel], temperature: float, max_tokens: int, timeout: int, previous_result: Optional[StrategyResult] = None) -> StrategyResult:
        loop = asyncio.get_event_loop()
        
        async def _call():
            return await loop.run_in_executor(
                None,
                lambda: litellm.completion(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                    response_format={"type": "json_object"}
                )
            )
            
        response = await self._api_call_with_backoff(_call)
        content = response.choices[0].message.content
        parsed_object = output_model.model_validate_json(content)
        
        return StrategyResult(raw_response=response, parsed_object=parsed_object, strategy=self.name, repair_attempts=0, validation_failures=0)


class MarkdownProvider(StructuredOutputProvider):
    name = "markdown"
    
    async def generate(self, system_prompt: str, user_prompt: str, model: str, output_model: Type[BaseModel], temperature: float, max_tokens: int, timeout: int, previous_result: Optional[StrategyResult] = None) -> StrategyResult:
        modified_system_prompt = system_prompt + "\n\nCRITICAL: You must respond ONLY with raw JSON wrapped in a ```json codeblock. Do not include any other conversational text."
        
        loop = asyncio.get_event_loop()
        async def _call():
            return await loop.run_in_executor(
                None,
                lambda: litellm.completion(
                    model=model,
                    messages=[{"role": "system", "content": modified_system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=temperature, max_tokens=max_tokens, timeout=timeout
                )
            )
            
        response = await self._api_call_with_backoff(_call)
        content = response.choices[0].message.content
        
        extracted_json = self.extract_json_block(content)
        parsed_object = output_model.model_validate_json(extracted_json)
        
        return StrategyResult(raw_response=response, parsed_object=parsed_object, strategy=self.name, repair_attempts=0, validation_failures=0)
        
    @staticmethod
    def extract_json_block(text: str) -> str:
        lines = text.split("\n")
        in_block = False
        json_lines = []
        for line in lines:
            line_strip = line.strip().lower()
            if line_strip.startswith("```json") or line_strip.startswith("``` json") or line_strip == "```":
                if not in_block:
                    in_block = True
                    continue
                else:
                    break
            elif in_block and line.strip().startswith("```"):
                break
            elif in_block:
                json_lines.append(line)
                
        if not json_lines:
            return text.strip()
            
        return "\n".join(json_lines)


class RepairProvider(StructuredOutputProvider):
    name = "repair"
    
    async def generate(self, system_prompt: str, user_prompt: str, model: str, output_model: Type[BaseModel], temperature: float, max_tokens: int, timeout: int, previous_result: Optional[StrategyResult] = None) -> StrategyResult:
        
        if not previous_result or not previous_result.raw_response:
            raise ValueError("Repair provider requires a previous failed result")
            
        failed_content = getattr(previous_result.raw_response.choices[0].message, "content", "")
        # Assuming the caller passes the validation error inside the user_prompt for the repair call? 
        # Actually, let's keep it clean. The strategy loop should pass the exact failed content and error, 
        # but to keep the interface uniform, the StrategySelector can modify the prompts before calling generate().
        
        loop = asyncio.get_event_loop()
        async def _call():
            return await loop.run_in_executor(
                None,
                lambda: litellm.completion(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=temperature, max_tokens=max_tokens, timeout=timeout
                )
            )
            
        response = await self._api_call_with_backoff(_call)
        content = response.choices[0].message.content
        
        extracted_json = MarkdownProvider.extract_json_block(content)
        parsed_object = output_model.model_validate_json(extracted_json)
        
        return StrategyResult(raw_response=response, parsed_object=parsed_object, strategy=self.name, 
                              repair_attempts=previous_result.repair_attempts + 1, 
                              validation_failures=previous_result.validation_failures)


# --- Selector ---

class StrategySelector:
    def __init__(self, registry: CapabilityRegistry, circuit_breaker: CircuitBreaker):
        self.registry = registry
        self.circuit_breaker = circuit_breaker
        self.providers = {
            "native": NativeJSONProvider(),
            "markdown": MarkdownProvider(),
            "repair": RepairProvider()
        }

    def build_pipeline(self, model: str) -> List[StructuredOutputProvider]:
        caps = self.registry.get(model)
        pipeline = []
        
        if caps.native_json and not self.circuit_breaker.is_open(model, "native"):
            pipeline.append(self.providers["native"])
            
        if caps.markdown and not self.circuit_breaker.is_open(model, "markdown"):
            pipeline.append(self.providers["markdown"])
            
        # Repair is handled dynamically in the orchestration loop, but we can return it as an available fallback provider
        return pipeline


# --- LLM Gateway ---

class LLMGateway:
    """
    Abstractions for all LLM interactions, handling retries, caching, 
    fallback logic, cost tracking, and structured validation using capability tiers.
    """
    def __init__(self, config: AppConfig):
        self.config = config.llm
        self.cache_config = self.config.cache
        
        self.registry = CapabilityRegistry()
        self.circuit_breaker = CircuitBreaker()
        self.selector = StrategySelector(self.registry, self.circuit_breaker)
        self.repair_provider = RepairProvider()
        
        # Setup in-memory cache if enabled
        if self.cache_config.enabled:
            self._cache = TTLCache(maxsize=1000, ttl=self.cache_config.ttl_seconds)
            logger.info("LLM Caching initialized", ttl_seconds=self.cache_config.ttl_seconds)
        else:
            self._cache = None
            logger.info("LLM Caching is disabled")

    def _get_cache_key(self, system_prompt: str, user_prompt: str, model: str) -> str:
        raw_key = f"{system_prompt}||{user_prompt}||{model}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def complete(
        self,
        module_name: str,
        system_prompt: str,
        user_prompt: str,
        output_model: Type[BaseModel],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_fallback: bool = True
    ) -> Tuple[BaseModel, LLMCallLog]:
        
        primary_config = self.config.primary
        fallback_config = self.config.fallback
        
        # --- True Offline Mock Mode Check ---
        import os
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("[DRY RUN] No LLM API keys found. Returning mocked response for", module=module_name)
            return self._get_mock_response(module_name, output_model), LLMCallLog(
                module=module_name, model="mock-offline-llm", input_tokens=0, output_tokens=0,
                cost_usd=0.0, latency_ms=10, cached=True, strategy_used="mock"
            )
        
        model = f"{primary_config.provider}/{primary_config.model}"
        
        if self._cache is not None:
            cache_key = self._get_cache_key(system_prompt, user_prompt, model)
            cached_data = self._cache.get(cache_key)
            if cached_data:
                cached_obj, call_log = cached_data
                logger.info("LLM Cache Hit", module=module_name, model=model)
                log_clone = call_log.model_copy()
                log_clone.cached = True
                return cached_obj, log_clone

        result = await self._execute_pipeline(
            system_prompt, user_prompt, model, output_model, temperature, max_tokens, module_name
        )
        
        if not result.success and use_fallback:
            fallback_model = f"{fallback_config.provider}/{fallback_config.model}"
            logger.warning("Primary LLM pipeline failed, triggering full fallback", module=module_name, fallback_model=fallback_model)
            result = await self._execute_pipeline(
                system_prompt, user_prompt, fallback_model, output_model, temperature, max_tokens, module_name
            )
            
        if not result.success:
            raise ValueError(f"LLM pipeline failed for {module_name}. Error: {result.exception_type}")

        call_log = result
        parsed_object = getattr(result, "_parsed_object", None)

        if self._cache is not None:
            cache_key = self._get_cache_key(system_prompt, user_prompt, call_log.model)
            self._cache[cache_key] = (parsed_object, call_log)

        logger.info(
            "LLM call finished",
            module=module_name,
            model=call_log.model,
            strategy=call_log.strategy_used,
            success=call_log.success,
            latency_ms=call_log.latency_ms
        )

        return parsed_object, call_log


    async def _execute_pipeline(
        self, system_prompt, user_prompt, model, output_model, temperature, max_tokens, module_name
    ) -> LLMCallLog:
        
        timeout = self.config.timeout_seconds
        pipeline = self.selector.build_pipeline(model)
        
        start_time = time.monotonic()
        validation_failures = 0
        last_result: Optional[StrategyResult] = None
        last_error = None
        
        for strategy in pipeline:
            try:
                result = await strategy.generate(
                    system_prompt, user_prompt, model, output_model, temperature, max_tokens, timeout
                )
                self.circuit_breaker.record_success(model, strategy.name)
                
                # Success! Pack and return
                return self._build_log(module_name, model, result, start_time, validation_failures, success=True)
                
            except ValidationError as e:
                validation_failures += 1
                self.circuit_breaker.record_failure(model, strategy.name)
                logger.warning(f"{strategy.name} validation failed", error=str(e), model=model)
                
                # We have raw content but failed validation, we can trigger the RepairProvider here
                # (unless we're out of repair retries)
                # Store the failed raw_response in a dummy StrategyResult for the repair provider
                failed_raw = getattr(e, "_raw_response", None) # if provider attached it
                # Actually, the simplest way is to catch it inside the gateway loop. But since providers raise it, 
                # we don't have the raw response unless we inject it into the exception. 
                # Let's adjust: Provider can't easily return raw response on raise. 
                # For this MVP, if it fails validation, we skip to the next strategy in the pipeline.
                pass
                
            except Exception as e:
                self.circuit_breaker.record_failure(model, strategy.name)
                logger.warning(f"{strategy.name} failed", error=str(e), model=model)
                last_error = str(e)
                
        return self._build_log(module_name, model, None, start_time, validation_failures, success=False, error=last_error)

    def _build_log(self, module, model, result: Optional[StrategyResult], start_time, val_fails, success=True, error=None) -> LLMCallLog:
        latency = int((time.monotonic() - start_time) * 1000)
        in_t = 0
        out_t = 0
        cost = 0.0
        
        if result and result.raw_response:
            usage = getattr(result.raw_response, "usage", None)
            in_t = getattr(usage, "prompt_tokens", 0) if usage else 0
            out_t = getattr(usage, "completion_tokens", 0) if usage else 0
            try: cost = litellm.completion_cost(completion_response=result.raw_response)
            except Exception: pass
            
        log = LLMCallLog(
            module=module,
            model=model,
            input_tokens=in_t,
            output_tokens=out_t,
            cost_usd=cost,
            latency_ms=latency,
            cached=False,
            strategy_used=result.strategy if result else "none",
            repair_attempts=result.repair_attempts if result else 0,
            validation_failures=val_fails,
            success=success,
            exception_type=error
        )
        if result:
            setattr(log, "_parsed_object", result.parsed_object)
        return log

    def _get_mock_response(self, module_name: str, output_model: Type[BaseModel]) -> BaseModel:
        from src.models.content_state import ContentPlan, TemplateSelection, CopyOutput, QAReport, SlideContent, TopicScore
        model_name = output_model.__name__
        if model_name == "ContentPlan":
            return ContentPlan(pillar="Community", topic="Meme about debugging", topic_id="meme_01", audience="Developers", suggested_cta="Follow!", assets_needed=[], dimensions="1080x1080", scoring=TopicScore(total=99.0, pillar_deficit=0, seasonality=0, engagement_history=0, freshness=0, trending=0, campaign_priority=0))
        elif model_name == "TemplateSelection":
            return TemplateSelection(template_type="meme", slide_count=1, prompt_key="meme_v1", layout_hints={})
        elif model_name == "CopyOutput":
            return CopyOutput(hook="When it works...", slides=[SlideContent(slide_num=1, heading="Wait", body="Why?", visual_note="Dev")], caption="Trap", hashtags=["#dev"], cta="Like!", alt_text="meme", image_prompt="dev")
        elif model_name == "QAEvalResult":
            return output_model(overall_score=9.5, passed=True, scores={}, feedback="Looks great!")
        else:
            raise ValueError(f"No mock configured for {model_name}")
