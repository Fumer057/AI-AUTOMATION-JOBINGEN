import sys
from src.utils.config_loader import load_config
from src.foundation.artifact_registry import ArtifactRegistry

def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    print("Initializing Artifact Registry...")
    registry = ArtifactRegistry(config)
    
    # Test YAML config retrieval
    print("\n--- Test Case 1: Load Prompt Config ---")
    planner_prompt = registry.get("prompts", "planner")
    print(f"Loaded successfully!")
    print(f"Name: {planner_prompt.name}, Version: {planner_prompt.version}")
    print(f"Content System Prompt: {planner_prompt.content['system_prompt']}")
    
    assert planner_prompt.name == "planner"
    assert planner_prompt.version == "v4"
    assert "strategic content director" in planner_prompt.content["system_prompt"]
    
    # Test HTML template retrieval
    print("\n--- Test Case 2: Load HTML Template ---")
    html_content = registry.get_template_html("carousel")
    print(f"Loaded successfully!")
    print(f"Snippet:\n{html_content.strip()}")
    
    assert "Carousel template version 6" in html_content

    # Test Snapshot for observability
    print("\n--- Test Case 3: Verify Version Snapshot ---")
    snap = registry.snapshot()
    print("Registry snapshot:")
    for k, v in snap.items():
        print(f"  {k}: {v}")
        
    assert snap["prompts.planner"] == "v4"
    assert snap["templates.carousel"] == "v6"
    
    print("\nSUCCESS: Artifact Registry loaded and verified successfully!")

if __name__ == "__main__":
    main()
