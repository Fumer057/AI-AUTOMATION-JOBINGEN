from src.utils.config_loader import load_config
import sys

if __name__ == "__main__":
    try:
        config = load_config("config.yaml")
        print("SUCCESS: Config loaded successfully!")
        print(f"Engine: {config.registry.active.prompts['planner']}")
        print(f"Primary LLM: {config.llm.primary.provider} / {config.llm.primary.model}")
        print(f"WhatsApp Enabled: {config.notifications.whatsapp.enabled}")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}")
        sys.exit(1)
