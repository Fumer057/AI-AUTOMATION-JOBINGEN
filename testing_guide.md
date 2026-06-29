# JobInGen Content Engine - Testing & Verification Guide

Follow the steps below to execute the content engine locally. Since no API keys are currently configured in your environment, these runs will generate live authentication/validation errors, proving that the engine is hitting actual external systems without placeholders or mocks.

---

## Step 1: Run the End-to-End Core AI Engine
This runs the full pipeline from Ingestion $\rightarrow$ Planning $\rightarrow$ Template Selection $\rightarrow$ Copy Generation $\rightarrow$ Quality QA.

### How to execute:
In your terminal (PowerShell or Bash), run:
```powershell
python run_engine.py
```

### Expected Result (The Proof):
The orchestrator will initialize the databases, create the plan, select a template, and then call the copywriter generator. Because there is no `GEMINI_API_KEY` or `OPENAI_API_KEY` configured in your environment, the pipeline will crash natively at the LLM Gateway layer, outputting logs similar to this:
```text
2026-06-30 00:44:00 [info     ] Initializing JobInGen Orchestrator...
2026-06-30 00:44:01 [info     ] Triggering Ingestion Plugins...
2026-06-30 00:44:01 [info     ] Starting Main Pipeline Run...
2026-06-30 00:44:01 [info     ] Pipeline started               run_id=a1b2c3d4
...
litellm.exceptions.AuthenticationError: Gemini API Error: API_KEY_INVALID - API key not valid. Please pass a valid API key.
...
2026-06-30 00:44:02 [error    ] Pipeline failed                run_id=a1b2c3d4 error='API key not valid'
```

---

## Step 2: Test the Live Publishing & Notification Plugins
This tests the event-driven handlers (Discord Notifier, LinkedIn and Instagram Publishers) that trigger once content is rendered.

### How to execute:
In your terminal, run:
```powershell
$env:PYTHONIOENCODING="utf-8"; python test_publishing.py
```

### Expected Result (The Proof):
The script will emit a `RenderComplete` event to the Event Bus. The Discord Notifier is active by default. Since no webhook URL is defined in the environment, it will fail fast and raise:
```text
ValueError: DISCORD_WEBHOOK_URL environment variable is missing.
```
> [!TIP]
> If you want to see the other publisher plugins fail as well, open `config.yaml`, change `linkedin_publish -> enabled: true` (or `instagram_publish -> enabled: true`), and run the test command again. They will trigger and throw their respective `ValueError: LINKEDIN_ACCESS_TOKEN... is missing` errors.

---

## Step 3: Run the Unit Test Verification Suite
Run this suite to verify that all databases, planners, metrics collectors, event buses, templates, and caching layers function successfully in isolation.

### How to execute:
In your terminal, run:
```powershell
$env:PYTHONIOENCODING="utf-8"; python test_config.py; python test_llm_gateway.py; python test_planner.py; python test_template_selector.py; python test_copy_generator.py; python test_memory.py; python test_metrics_collector.py; python test_operational_store.py; python test_knowledge_store.py; python test_event_bus.py
```

### Expected Result:
All unit test scripts will execute successfully one after another, ending with green successes:
```text
SUCCESS: Config loaded successfully!
SUCCESS: All LLM Gateway test cases passed!
SUCCESS: Content Planner verified successfully!
SUCCESS: Template Selector verified successfully!
SUCCESS: Copy Generator verified successfully!
SUCCESS: Memory Module verified successfully!
SUCCESS: Metrics Collector behaves correctly!
SUCCESS: Operational Store verified successfully!
SUCCESS: Knowledge Store verified successfully!
SUCCESS: Event Bus behaves correctly!
```

---

## Step 4: Verify LLM Provider Auto-Adaptation (Optional)
The system is equipped with an environment key auto-detection feature. You can verify how it adapts when you define an API key.

### How to execute:
To test the OpenAI auto-adaptation (switching to `gpt-5.5` primary and `gpt-5.4-mini` fallback), run:
```powershell
$env:OPENAI_API_KEY="sk-test-key"; python test_config.py
```

### Expected Result:
The test loader will automatically adapt the configuration on-the-fly and display:
```text
SUCCESS: Config loaded successfully!
Engine: v4
Primary LLM: openai / gpt-5.5
WhatsApp Enabled: True
```
