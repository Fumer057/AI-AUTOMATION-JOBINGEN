"""Verify all JobInGen engine dependencies are installed correctly."""

import sys
from importlib.metadata import version as pkg_version

PACKAGES = [
    ("litellm", "litellm"),
    ("openai", "openai"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("jinja2", "jinja2"),
    ("playwright", "playwright"),
    ("yaml", "pyyaml"),
    ("dotenv", "python-dotenv"),
    ("click", "click"),
    ("rich", "rich"),
    ("aiosqlite", "aiosqlite"),
    ("httpx", "httpx"),
    ("structlog", "structlog"),
    ("cachetools", "cachetools"),
    ("dateutil", "python-dateutil"),
    ("PIL", "pillow"),
]

deps = {}
errors = []

for import_name, pkg_name in PACKAGES:
    try:
        __import__(import_name)
        deps[pkg_name] = pkg_version(pkg_name)
    except (ImportError, Exception) as e:
        errors.append(f"{pkg_name}: {e}")

print("=" * 50)
print("  JobInGen Engine - Dependency Check")
print("=" * 50)
print(f"  Python: {sys.version.split()[0]}")
print("-" * 50)

for name, version in deps.items():
    print(f"  OK  {name:20s} {version}")

if errors:
    print("-" * 50)
    for err in errors:
        print(f"  FAIL  {err}")

print("-" * 50)
print(f"  {len(deps)}/{len(deps) + len(errors)} packages OK")

if errors:
    print("  WARNING: Some packages failed to import!")
    sys.exit(1)
else:
    print("  All dependencies ready. Ready to build!")
    sys.exit(0)
