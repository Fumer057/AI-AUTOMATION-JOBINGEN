import asyncio
import sys
from unittest.mock import MagicMock, patch
from pydantic import BaseModel
from src.utils.config_loader import load_config
from src.foundation.llm_gateway import LLMGateway

# Define a simple response model for testing
class TestOutputSchema(BaseModel):
    headline: str
    points: list[str]

# Create a mock litellm response object
class MockUsage:
    def __init__(self):
        self.prompt_tokens = 100
        self.completion_tokens = 50

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockCompletionResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage()

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Enable caching in test config overrides
    config.llm.cache.enabled = True
    
    print("Initializing LLM Gateway...")
    gateway = LLMGateway(config)
    
    system_prompt = "Test System"
    user_prompt = "Test User"
    
    # 1. Test Successful Execution and Parsing
    valid_json = '{"headline": "Test Headline", "points": ["Point A", "Point B"]}'
    mock_response = MockCompletionResponse(valid_json)
    
    print("\n--- Test Case 1: Normal Completion ---")
    with patch("litellm.completion", return_value=mock_response) as mock_complete:
        with patch("litellm.completion_cost", return_value=0.0015):
            res, log = await gateway.complete(
                module_name="test_module",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_model=TestOutputSchema
            )
            
            print(f"Parsed output: {res.headline} - {res.points}")
            print(f"Log tokens: Input {log.input_tokens}, Output {log.output_tokens}")
            print(f"Log cost: ${log.cost_usd:.5f}, Latency: {log.latency_ms}ms, Cached: {log.cached}")
            
            assert res.headline == "Test Headline"
            assert log.cached is False
            mock_complete.assert_called_once()

    # 2. Test Cache Hit (re-run same prompts, expect cached true and no API call)
    print("\n--- Test Case 2: Cache Hit ---")
    with patch("litellm.completion") as mock_complete_cache:
        res2, log2 = await gateway.complete(
            module_name="test_module",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_model=TestOutputSchema
        )
        print(f"Parsed output (cached): {res2.headline}")
        print(f"Log cached: {log2.cached}")
        assert res2.headline == "Test Headline"
        assert log2.cached is True
        mock_complete_cache.assert_not_called()

    # 3. Test Fallback logic
    print("\n--- Test Case 3: Fallback Logic ---")
    # Change prompts to bypass cache
    sys_fallback = "Sys Fallback"
    user_fallback = "User Fallback"
    
    # We want primary call to raise exception, and fallback call to succeed
    # We patch litellm.completion side_effect
    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if kwargs.get("model") == "openai/gpt-4o":
            raise RuntimeError("Primary model error!")
        return MockCompletionResponse('{"headline": "Fallback Headline", "points": ["FB1"]}')

    with patch("litellm.completion", side_effect=side_effect):
        res_fb, log_fb = await gateway.complete(
            module_name="test_module",
            system_prompt=sys_fallback,
            user_prompt=user_fallback,
            output_model=TestOutputSchema
        )
        print(f"Parsed output (fallback): {res_fb.headline}")
        print(f"Log model used: {log_fb.model}")
        assert res_fb.headline == "Fallback Headline"
        assert log_fb.model == "anthropic/claude-3-5-sonnet-20240620"
        assert call_count == 4 # 3 primary calls (retries) + 1 fallback call (success)

    print("\nSUCCESS: All LLM Gateway test cases passed!")

if __name__ == "__main__":
    asyncio.run(main())
