import os
import sys
from pathlib import Path
from src.utils.config_loader import load_config
from src.foundation.asset_manager import AssetManager

def create_mock_assets(base_dir: Path):
    """Pre-create mock files to make sure validation succeeds."""
    mock_files = [
        "fonts/PlusJakartaSans-Bold.woff2",
        "fonts/Inter-Regular.woff2",
        "logos/jobingen_logo_white.svg",
        "logos/jobingen_logo_dark.svg",
        "backgrounds/gradient_blue.png",
        "icons/email.svg",
        "icons/check.svg"
    ]
    for rel_path in mock_files:
        full_path = base_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_path.exists():
            full_path.write_text("MOCK CONTENT", encoding="utf-8")
            print(f"Created mock asset: {rel_path}")

def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    base_dir = Path(config.assets.dir)
    print(f"Creating mock assets in {base_dir}...")
    create_mock_assets(base_dir)
    
    print("Initializing Asset Manager...")
    am = AssetManager(config)
    
    # Test Validation
    print("\n--- Test Case 1: Validate Assets on Disk ---")
    missing = am.validate()
    print(f"Missing count: {len(missing)}")
    assert len(missing) == 0, f"Expected no missing assets, got: {missing}"
    print("Validation passed! All manifest files exist.")
    
    # Test Resolution
    print("\n--- Test Case 2: Resolve Asset Paths ---")
    resolved = am.resolve(["icon_email", "logo_white"])
    print("Resolved:")
    for k, v in resolved.items():
        print(f"  {k} -> {v}")
        assert Path(v).is_absolute()
        assert Path(v).exists()

    # Test Logo Variant
    logo_path = am.get_logo("dark")
    print(f"Dark logo resolved path: {logo_path}")
    assert "jobingen_logo_dark.svg" in logo_path
    
    print("\nSUCCESS: Asset Manager verified successfully!")

if __name__ == "__main__":
    main()
