# Gemini Native Bypass Strategy

This document outlines the architecture, implementation steps, and consequences of bypassing `litellm` in favor of the native `google-generativeai` SDK, specifically for Google Gemini models.

This strategy should only be implemented if the system encounters persistent `404 Not Found` API routing bugs within the `litellm` library when attempting to hit the Gemini `/v1beta/models/...:generateContent` endpoint.

## 1. Architectural Impact
Currently, the `LLMGateway` (`src/foundation/llm_gateway.py`) acts as a provider-agnostic router. All requests are formatted into OpenAI-style chat schemas and sent to `litellm`, which translates them to the respective provider's API.

If this bypass is implemented, we will add an explicit conditional branch within `LLMGateway._execute_with_retries`:
- **If model starts with `gemini/`**: Completely bypass `litellm`. The gateway will initialize the native `google-generativeai` client, construct the prompt, make the API call directly to Google, and mock a `litellm`-style response object so the downstream pipeline components remain unaware of the bypass.
- **Else**: Route to `litellm` as normal (for OpenAI, Anthropic, etc).

## 2. Implementation Steps
If you choose to proceed with this route, the following changes must be made to `src/foundation/llm_gateway.py`:

1. Add `import google.generativeai as genai`
2. Update `_execute_with_retries` to intercept Gemini traffic:
   ```python
   if provider == "gemini":
       genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
       gemini_model = genai.GenerativeModel(model.replace("gemini/", ""))
       
       # Convert system/user prompt into Gemini format
       prompt = f"System: {system_prompt}\nUser: {user_prompt}"
       response = gemini_model.generate_content(prompt)
       
       # Mock a litellm response object to maintain compatibility
       class MockMessage:
           def __init__(self, content):
               self.content = content
       class MockChoice:
           def __init__(self, message):
               self.message = message
       class MockResponse:
           def __init__(self, choices):
               self.choices = choices
               
       return MockResponse([MockChoice(MockMessage(response.text))])
   else:
       # Standard litellm execution block
   ```

## 3. Pros and Cons Analysis

### The Pros (Benefits)
* **Instant Resolution:** Completely circumvents the `404 Not Found` routing bug inside the `litellm` HTTPX client.
* **Native Reliability:** Communicates directly with Google's official SDK, ensuring 100% compatibility with new Google model names (like `gemini-1.5-flash-001`) and standard `AQ.` formatted API keys.
* **Zero Cascading Impact:** Because the mock object is built entirely inside the `LLMGateway`, no other files in the project need to be touched. The Orchestrator, Planner, and QA Critic will never know the difference.

### The Cons (Risks)
* **Architecture Purity:** Introduces a provider-specific hack into an otherwise beautifully unified and agnostic gateway.
* **Loss of Cost Tracking:** `litellm` automatically tracks API token usage and calculates USD cost dynamically. By bypassing it, Gemini runs will log as `$0.00` in our SQLite analytics database.
* **Loss of Advanced litellm Features:** We lose out on litellm's native rate-limit handling and advanced fallback structures specifically for the Gemini branch.
* **New Dependency:** It introduces a hard dependency on the `google-generativeai` package.
