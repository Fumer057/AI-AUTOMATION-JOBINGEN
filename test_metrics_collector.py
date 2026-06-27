import sys
from src.foundation.metrics_collector import MetricsCollector

# Configure structlog to output json for verification
import structlog
structlog.configure(
    processors=[structlog.processors.JSONRenderer()]
)

def main():
    print("Initializing Metrics Collector...")
    mc = MetricsCollector()
    
    # 1. Test Recording latency and token counts
    print("\n--- Test Case 1: Record Core Pipeline Metrics ---")
    mc.record("pipeline.duration_ms", 45200.0, {"status": "delivered"})
    mc.record("llm.cost_usd", 0.0234, {"model": "gpt-4o", "module": "generator"})
    mc.record("llm.tokens_total", 4520.0, {"model": "gpt-4o"})
    mc.record("qa.score", 8.5, {"pillar": "Educate", "attempt": 1})
    
    metrics = mc.get_metrics()
    print(f"Recorded metric count: {len(metrics)}")
    assert len(metrics) == 4
    
    # Check values
    assert metrics[0].name == "pipeline.duration_ms"
    assert metrics[0].value == 45200.0
    assert metrics[0].labels["status"] == "delivered"
    
    assert metrics[1].name == "llm.cost_usd"
    assert metrics[1].value == 0.0234
    
    # 2. Test Flushing
    print("\n--- Test Case 2: Flush Buffer ---")
    flushed = mc.flush_to_db(run_id="test_run_123")
    assert len(flushed) == 4
    assert len(mc.get_metrics()) == 0
    
    print("\nSUCCESS: Metrics Collector behaves correctly!")

if __name__ == "__main__":
    main()
