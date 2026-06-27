import sys
import argparse
import asyncio
from datetime import date
from typing import Optional

import structlog

from src.utils.config_loader import load_config
from src.models.content_state import ContentState, PipelineStatus
from src.foundation.event_bus import EventBus
from src.foundation.artifact_registry import ArtifactRegistry
from src.foundation.asset_manager import AssetManager
from src.foundation.llm_gateway import LLMGateway
from src.foundation.metrics_collector import MetricsCollector

from src.data.knowledge_store import KnowledgeStore
from src.data.operational_store import OperationalStore
from src.data.memory import Memory

from src.intelligence.planner import ContentPlanner
from src.intelligence.template_selector import TemplateSelector
from src.llm.copy_generator import CopyGenerator
from src.llm.qa_pass import QAPass

from src.rendering.render_spec_builder import RenderSpecBuilder
from src.rendering.renderer import DesignRenderer
from src.delivery.output_queue import OutputQueue

logger = structlog.get_logger(__name__)

class Orchestrator:
    """
    The master controller for the JobInGen Content Engine.
    Initializes the dependency graph and executes the pipeline phases.
    """
    def __init__(self, config_path: str = "config.yaml"):
        # Foundation
        self.config = load_config(config_path)
        self.bus = EventBus()
        self.registry = ArtifactRegistry(self.config)
        self.assets = AssetManager(self.config)
        self.gateway = LLMGateway(self.config)
        self.metrics = MetricsCollector()
        
        # Data Layer
        self.knowledge = KnowledgeStore(self.config)
        self.ops = OperationalStore(self.config)
        self.memory = Memory(self.ops)
        
        # Intelligence Layer
        self.planner = ContentPlanner(self.config, self.registry, self.memory, self.knowledge)
        self.template_selector = TemplateSelector(self.config, self.registry, self.knowledge)
        
        # LLM Core
        self.generator = CopyGenerator(self.config, self.registry, self.gateway, self.knowledge)
        self.qa = QAPass(self.config, self.registry, self.gateway)
        
        # Rendering & Delivery
        self.rs_builder = RenderSpecBuilder(self.config, self.registry, self.assets)
        self.renderer = DesignRenderer(self.config)
        self.queue = OutputQueue(self.config, self.ops)

    async def initialize(self):
        """Async initialization for data stores."""
        await self.knowledge.initialize()
        await self.ops.initialize()
        
        missing_assets = self.assets.validate()
        if missing_assets:
            logger.warning("Some configured assets are missing", missing=missing_assets)

    async def run(self, mock_date: Optional[date] = None) -> ContentState:
        """Executes the complete generation pipeline."""
        run_date = mock_date or date.today()
        state = ContentState(date=run_date)
        
        logger.info("Pipeline started", run_id=state.run_id, date=run_date.isoformat())
        await self.bus.emit("PipelineStarted", state)
        
        try:
            # 1. PLAN
            state.plan = await self.planner.create_plan(state)
            state.status = PipelineStatus.PLANNED
            await self.bus.emit("PlanCreated", state)
            
            # 2. SELECT TEMPLATE
            state.template = await self.template_selector.select(state.plan)
            state.status = PipelineStatus.TEMPLATE_SET
            
            # Snapshot artifact versions for reproducibility
            state.artifact_versions = self.registry.snapshot()
            
            # 3. GENERATE & QA (Loop)
            max_retries = self.config.critic.max_retries
            feedback = None
            
            for attempt in range(1, max_retries + 1):
                state.qa_attempts = attempt
                
                copy, gen_log = await self.generator.generate(state.plan, state.template, feedback)
                state.generated_copy = copy
                state.llm_calls.append(gen_log)
                state.status = PipelineStatus.DRAFTED
                
                qa_report, qa_log = await self.qa.evaluate(state.plan, state.template, copy, attempt)
                state.qa = qa_report
                state.llm_calls.append(qa_log)
                
                if qa_report.passed:
                    state.status = PipelineStatus.QA_PASSED
                    await self.bus.emit("QAPassed", state)
                    break
                else:
                    feedback = qa_report.feedback
                    logger.warning("QA Failed, retrying...", attempt=attempt, feedback=feedback)
            
            if not state.qa or not state.qa.passed:
                raise RuntimeError(f"Failed to pass QA after {max_retries} attempts.")
                
            # 4. RENDER SPEC BUILDER
            state.render_spec = self.rs_builder.build(state.plan, state.template, state.generated_copy)
            state.status = PipelineStatus.RENDER_SPEC
            
            # 5. DESIGN RENDERER
            image_paths = await self.renderer.render(state.render_spec, state.run_id)
            state.image_paths = image_paths
            state.status = PipelineStatus.RENDERED
            await self.bus.emit("Rendered", state)
            
            # 6. OUTPUT QUEUE (Delivery & Logging)
            await self.queue.process(state)
            await self.bus.emit("PipelineCompleted", state)
            
            logger.info("Pipeline fully completed! 🚀", run_id=state.run_id, output_dir=state.output_dir)
            return state
            
        except Exception as e:
            state.status = PipelineStatus.FAILED
            state.errors.append(str(e))
            logger.error("Pipeline failed", run_id=state.run_id, error=str(e))
            await self.bus.emit("PipelineFailed", state)
            # Log the failed run to ops DB so we track the failure
            await self.queue.process(state) 
            raise e

def main():
    parser = argparse.ArgumentParser(description="JobInGen Content Engine CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    async def _main():
        orchestrator = Orchestrator(args.config)
        await orchestrator.initialize()
        await orchestrator.run()

    asyncio.run(_main())

if __name__ == "__main__":
    main()
