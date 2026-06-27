import time
import hashlib
import json
import asyncio
from typing import Type, Tuple, Optional
from pydantic import BaseModel
import litellm
from cachetools import TTLCache
import structlog

from src.models.content_state import LLMCallLog
from src.utils.config_loader import AppConfig

logger = structlog.get_logger(__name__)

class LLMGateway:
    """
    Abstractions for all LLM interactions, handling retries, caching, 
    fallback logic, cost tracking, and structured validation.
    """
    def __init__(self, config: AppConfig):
        self.config = config.llm
        self.cache_config = self.config.cache
        
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
        """
        Send a completion request to the configured LLM, validate output schema,
        track cost and latency, and handle API retries/fallbacks.
        """
        primary_config = self.config.primary
        fallback_config = self.config.fallback
        
        model = f"{primary_config.provider}/{primary_config.model}"
        
        # Check cache
        if self._cache is not None:
            cache_key = self._get_cache_key(system_prompt, user_prompt, model)
            cached_data = self._cache.get(cache_key)
            if cached_data:
                cached_obj, call_log = cached_data
                logger.info("LLM Cache Hit", module=module_name, model=model)
                # Return clone with updated flag
                log_clone = call_log.model_copy()
                log_clone.cached = True
                return cached_obj, log_clone

        start_time = time.monotonic()
        response_data = None
        used_model = model
        
        # Try primary model first, then fallback
        try:
            response_data = await self._execute_with_retries(
                system_prompt, user_prompt, model, temperature, max_tokens
            )
        except Exception as primary_err:
            logger.warning(
                "Primary LLM execution failed, trying fallback",
                module=module_name,
                primary_model=model,
                error=str(primary_err)
            )
            if use_fallback:
                used_model = f"{fallback_config.provider}/{fallback_config.model}"
                try:
                    response_data = await self._execute_with_retries(
                        system_prompt, user_prompt, used_model, temperature, max_tokens
                    )
                except Exception as fallback_err:
                    logger.error("Fallback LLM execution failed", module=module_name, fallback_model=used_model, error=str(fallback_err))
                    raise fallback_err
            else:
                raise primary_err

        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Extract tokens and cost
        usage = getattr(response_data, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        
        # Compute cost
        try:
            cost_usd = litellm.completion_cost(completion_response=response_data)
        except Exception:
            # Fallback cost estimation if litellm cost check fails
            cost_usd = 0.0

        content = response_data.choices[0].message.content
        
        # Validate and parse structured output
        try:
            # Strip markdown block formatting if present
            cleaned_content = content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()

            parsed_object = output_model.model_validate_json(cleaned_content)
        except Exception as parse_err:
            logger.error("LLM Output failed JSON schema validation", content=content, error=str(parse_err))
            raise ValueError(f"LLM response failed schema validation: {parse_err}") from parse_err

        call_log = LLMCallLog(
            module=module_name,
            model=used_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cached=False
        )

        # Cache result
        if self._cache is not None:
            cache_key = self._get_cache_key(system_prompt, user_prompt, model)
            self._cache[cache_key] = (parsed_object, call_log)

        logger.info(
            "LLM call success",
            module=module_name,
            model=used_model,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        return parsed_object, call_log

    async def _execute_with_retries(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int
    ):
        max_retries = self.config.max_api_retries
        timeout = self.config.timeout_seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                # Run the blocking litellm call in an executor since it doesn't offer native asyncio
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: litellm.completion(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        response_format={"type": "json_object"}
                    )
                )
                return response
            except Exception as e:
                logger.warning("LLM API execution attempt failed", attempt=attempt, model=model, error=str(e))
                if attempt == max_retries:
                    raise e
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
