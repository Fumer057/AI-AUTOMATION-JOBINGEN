import json
from pathlib import Path
from typing import Dict, List
from src.utils.config_loader import AppConfig
import structlog

logger = structlog.get_logger(__name__)

class AssetManager:
    """
    Manages brand asset resolution and validation, ensuring paths to 
    logos, fonts, icons, and backgrounds are resolved dynamically 
    before rendering starts.
    """
    def __init__(self, config: AppConfig):
        self.config = config.assets
        self.base_dir = Path(self.config.dir)
        self.manifest_path = Path(self.config.manifest)
        self.manifest: Dict[str, str] = {}
        self._load_manifest()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Asset manifest file not found: {self.manifest_path}")
        
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)
            logger.info("Asset manifest loaded", keys_count=len(self.manifest))
        except Exception as e:
            logger.error("Failed to load asset manifest", path=str(self.manifest_path), error=str(e))
            raise e

    def resolve(self, asset_ids: List[str]) -> Dict[str, str]:
        """
        Resolve a list of asset IDs to absolute local file paths.
        
        Args:
            asset_ids: List of asset keys from the content plan (e.g. ['icon_email', 'logo_white'])
        """
        resolved = {}
        for asset_id in asset_ids:
            if asset_id not in self.manifest:
                logger.warning("Asset ID not found in manifest", asset_id=asset_id)
                continue
            
            rel_path = self.manifest[asset_id]
            abs_path = self.base_dir / rel_path
            resolved[asset_id] = str(abs_path.resolve())
            
        return resolved

    def get_brand_fonts(self) -> Dict[str, str]:
        """Return the resolved paths to the primary heading and body fonts."""
        return self.resolve(["font_heading", "font_body"])

    def get_logo(self, variant: str = "white") -> str:
        """
        Get the resolved path to the brand logo.
        
        Args:
            variant: Either 'white' or 'dark'
        """
        logo_key = f"logo_{variant}"
        resolved = self.resolve([logo_key])
        if logo_key not in resolved:
            raise ValueError(f"Logo variant '{variant}' not configured in manifest.")
        return resolved[logo_key]

    def validate(self) -> List[str]:
        """
        Validate that all files mapped in the manifest actually exist on disk.
        Returns a list of missing asset paths (empty list if everything is OK).
        """
        missing_assets = []
        for asset_id, rel_path in self.manifest.items():
            abs_path = self.base_dir / rel_path
            if not abs_path.exists():
                missing_assets.append(f"{asset_id} -> {abs_path}")
                logger.error("Missing asset on disk", asset_id=asset_id, path=str(abs_path))
                
        return missing_assets
