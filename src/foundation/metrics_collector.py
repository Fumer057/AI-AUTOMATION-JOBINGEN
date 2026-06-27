from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class Metric(BaseModel):
    """Structured representation of a single pipeline metric event."""
    name: str
    value: float
    labels: Dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=datetime.utcnow)

class MetricsCollector:
    """
    Collector for tracking pipeline execution metrics (e.g., latency, 
    token consumption, cost, and quality scores). Logs structured metrics
    and caches them for flushing to the database.
    """
    def __init__(self):
        self.current_metrics: List[Metric] = []

    def record(self, name: str, value: float, labels: Optional[Dict[str, Any]] = None):
        """
        Record a metric measurement with optional contextual labels.
        
        Args:
            name: Identifier for the metric (e.g. 'pipeline.duration_ms')
            value: Float metric value
            labels: Dictionary of metadata (e.g. {'pillar': 'Educate', 'model': 'gpt-4o'})
        """
        metric = Metric(name=name, value=value, labels=labels or {})
        self.current_metrics.append(metric)
        
        # Emit structured log for ingestion by external monitoring tools
        logger.info(
            "Metric recorded",
            metric_name=name,
            metric_value=value,
            **metric.labels
        )

    def get_metrics(self) -> List[Metric]:
        """Return all collected metrics in the current run."""
        return self.current_metrics

    def clear(self):
        """Clear the in-memory metric buffer."""
        self.current_metrics.clear()

    def flush_to_db(self, run_id: str, db_connection: Any = None) -> List[Metric]:
        """
        Flush all buffered metrics. If an active database connection is provided,
        it writes them to the pipeline_metrics table.
        
        Args:
            run_id: Unique pipeline execution run identifier
            db_connection: Optional database connection (integrated in Data Layer)
        """
        flushed = list(self.current_metrics)
        
        # Database integration will happen here in the Data Layer step.
        # For now, we log the flush event.
        logger.info("Flushing metrics buffer", run_id=run_id, metrics_count=len(flushed))
        
        self.clear()
        return flushed
