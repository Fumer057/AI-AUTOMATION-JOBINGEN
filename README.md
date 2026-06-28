# JobInGen AI Content Creation Engine — System Architecture v3 (Final)

> **Changelog from v2**: Split stores (Knowledge vs Operational), LLM Gateway, RenderSpec Builder as own module, Event Bus, observability metrics, Artifact Registry (version everything), Planner scoring engine, Template Selector module.

---

## 1. Problem Summary

Build a fully automated AI content engine that produces daily, on-brand social media posts (copy + designed images) for JobInGen. One command → complete content pack. Zero manual work. Phase 2 integrations are optional plugins — the core engine works end-to-end with all externals off.

---

## 2. Architectural Principles

| # | Principle | How |
|---|-----------|-----|
| 1 | **Typed contracts** | Every module communicates via Pydantic models. No free-form text between modules. |
| 2 | **Single state object** | `ContentState` flows through the pipeline. Every module reads and writes to it. |
| 3 | **Centralized orchestration** | Orchestrator is the only entity that invokes modules. Modules never call each other. |
| 4 | **Deterministic rendering** | Renderer receives a typed `RenderSpec` — never raw LLM output. |
| 5 | **Version everything** | Artifact Registry versions prompts, rubrics, schemas, and HTML templates as code. |
| 6 | **Separated concerns** | Knowledge data (topics, jobs) and operational data (runs, logs, metrics) live in separate stores. |
| 7 | **Provider-agnostic LLM** | A dedicated LLM Gateway handles retries, caching, fallback, cost tracking, rate limiting. Consumers never know about providers. |
| 8 | **Event-driven extensibility** | An internal Event Bus lets plugins subscribe to pipeline events without modifying the Orchestrator. |
| 9 | **Observable by default** | Every run emits structured metrics (latency, cost, scores, retries) ready for dashboards. |

---

## 3. High-Level Architecture

```mermaid
graph TD
    subgraph "⏱ Trigger"
        CRON["Cron / n8n / GitHub Actions"]
    end

    subgraph "🧠 Core Engine"
        ORCH["Orchestrator"]
        BUS["Event Bus"]

        subgraph "Foundation Services"
            REGISTRY["Artifact Registry"]
            ASSETS["Asset Manager"]
            GATEWAY["LLM Gateway"]
            OBSERVE["Metrics Collector"]
        end

        subgraph "Data Layer"
            KNOWLEDGE["Knowledge Store\n(topics, jobs, testimonials)"]
            OPS["Operational Store\n(runs, logs, metrics, history)"]
            MEMORY["Memory Module"]
        end

        subgraph "Pipeline Stages"
            PLANNER["Planner\n(scoring engine)"]
            TSELECT["Template Selector"]
            GENERATOR["Copy Generator"]
            CRITIC["Critic / QA"]
            RSBUILD["RenderSpec Builder"]
            RENDERER["Design Renderer"]
            QUEUE["Output Queue"]
        end
    end

    subgraph "🔌 Plugins (Phase 2)"
        LINKEDIN["P2.1 LinkedIn"]
        JOBDATA["P2.2 Job Ingestion"]
        INSTAGRAM["P2.3 Instagram"]
        TRENDS["P2.4 Trends"]
        LEARNING["P2.5 Learning Module"]
    end

    CRON --> ORCH
    ORCH --> PLANNER
    ORCH --> TSELECT
    ORCH --> GENERATOR
    ORCH --> CRITIC
    ORCH --> RSBUILD
    ORCH --> RENDERER
    ORCH --> QUEUE

    ORCH --> BUS
    BUS -.->|subscribe| LINKEDIN
    BUS -.->|subscribe| INSTAGRAM
    BUS -.->|subscribe| LEARNING

    REGISTRY -.-> ORCH
    ASSETS -.-> RSBUILD
    ASSETS -.-> RENDERER
    GATEWAY -.-> GENERATOR
    GATEWAY -.-> CRITIC
    OBSERVE -.-> ORCH

    KNOWLEDGE -.-> PLANNER
    KNOWLEDGE -.-> GENERATOR
    MEMORY -.-> PLANNER
    OPS -.-> MEMORY
    OPS -.-> OBSERVE

    JOBDATA -.-> KNOWLEDGE
    TRENDS -.-> KNOWLEDGE
    LEARNING -.-> OPS
```

### Orchestrator as Central Controller

```
                        Orchestrator
                             │
              ┌──────────────┼──────────────────┐
              │              │                  │
     Artifact Registry   LLM Gateway     Event Bus
              │              │                  │
    ┌─────────┼─────────┐    │                  │
    │         │         │    │                  │
Knowledge  Operational Memory               Metrics
  Store      Store                          Collector
                             │
              ┌──────────────┼──────────────┐
              │              │              │
          Planner     Asset Manager     (ready)
              │
              ▼
      Template Selector
              │
              ▼
        Copy Generator ←──── LLM Gateway
              │
              ▼
         Critic / QA   ←──── LLM Gateway
           ↙       ↘
     Retry (<3)    Pass
                     │
                     ▼
            RenderSpec Builder
                     │
                     ▼
             Design Renderer
                     │
                     ▼
              Output Queue
                     │
                Event Bus → (PlanCreated, CopyGenerated, QAPassed, Rendered, Delivered)
```

