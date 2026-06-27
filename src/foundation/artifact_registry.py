import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel
from src.utils.config_loader import AppConfig
import structlog

logger = structlog.get_logger(__name__)

class ArtifactConfig(BaseModel):
    """Container for parsed prompt, rubric, or schema yaml configs."""
    name: str
    version: str
    content: Dict[str, Any]

class ArtifactRegistry:
    """
    Registry for loading and tracking active versions of prompts, rubrics,
    schemas, and HTML templates dynamically defined in config.yaml.
    """
    def __init__(self, config: AppConfig):
        self.config = config.registry
        self.base_dir = Path(self.config.dir)
        self.active_versions = self.config.active
        logger.info("Artifact Registry initialized", base_dir=str(self.base_dir))

    def get(self, category: str, name: str) -> ArtifactConfig:
        """
        Load the active YAML configuration for a prompt, rubric, or schema.
        
        Args:
            category: Folder name (e.g., 'prompts', 'rubrics', 'schemas')
            name: Base name of the file (e.g., 'planner', 'critic')
        """
        # Resolve active version
        active_map = getattr(self.active_versions, category, None)
        if not active_map:
            raise ValueError(f"Category '{category}' is invalid in registry active configs.")
            
        version = active_map.get(name)
        if not version:
            raise ValueError(f"No active version defined for artifact: {category}/{name}")

        filename = f"{name}_{version}.yaml"
        file_path = self.base_dir / category / filename

        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found in registry: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            # The YAML must contain metadata: name, version
            name_val = data.get("name", name)
            version_val = data.get("version", version)
            
            logger.info("Loaded registry artifact", category=category, name=name, version=version)
            return ArtifactConfig(name=name_val, version=version_val, content=data)
        except Exception as e:
            logger.error("Failed to parse registry artifact", path=str(file_path), error=str(e))
            raise e

    def get_template_html(self, template_type: str) -> str:
        """
        Load the active HTML template from registry/templates.
        
        Args:
            template_type: Type of template (e.g., 'carousel', 'job_drop')
        """
        version = self.active_versions.templates.get(template_type)
        if not version:
            raise ValueError(f"No active version defined for template: {template_type}")

        filename = f"{template_type}_{version}.html"
        file_path = self.base_dir / "templates" / filename

        if not file_path.exists():
            raise FileNotFoundError(f"HTML Template not found in registry: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
            logger.info("Loaded HTML template", template=template_type, version=version)
            return content
        except Exception as e:
            logger.error("Failed to read HTML template", path=str(file_path), error=str(e))
            raise e

    def snapshot(self) -> Dict[str, str]:
        """
        Take a snapshot of all active artifact versions currently loaded
        to log in the operational run history for complete reproducibility.
        """
        flat_snapshot = {}
        for cat_name in ["prompts", "rubrics", "schemas", "templates"]:
            cat_obj = getattr(self.active_versions, cat_name, {})
            if isinstance(cat_obj, dict):
                mapping = cat_obj
            else:
                mapping = cat_obj.model_dump() if hasattr(cat_obj, "model_dump") else {}
                
            for k, v in mapping.items():
                flat_snapshot[f"{cat_name}.{k}"] = v
        return flat_snapshot
