"""Check required environment variables for the project.

This script attempts to load `.env` (preferred) and falls back to
`.env.example` if `.env` is not present. It reports which required
variables are set and flags placeholder values starting with "YOUR_".

Usage:
    python scripts/check_env.py
"""
import os
import sys

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

ROOT = os.path.dirname(os.path.dirname(__file__))
env_path = os.path.join(ROOT, ".env")
example_path = os.path.join(ROOT, ".env.example")

loaded_from = None
if load_dotenv:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        loaded_from = ".env"
    elif os.path.exists(example_path):
        load_dotenv(example_path)
        loaded_from = ".env.example"

REQUIRED = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
]

def is_filled(value: str | None) -> bool:
    if not value:
        return False
    if value.strip() == "":
        return False
    # treat obvious placeholders as not filled
    if value.upper().startswith("YOUR_"):
        return False
    return True

def main() -> int:
    if not load_dotenv:
        print("python-dotenv not installed; this script only checks environment variables from the current process.")
        print("Install it with: pip install python-dotenv")
        print()
    else:
        print(f"Loaded environment from: {loaded_from or 'process environment only'}")

    missing = []
    placeholders = []
    for name in REQUIRED:
        val = os.environ.get(name)
        if not is_filled(val):
            # difference between empty/missing vs placeholder
            if val is None or val == "":
                missing.append(name)
            else:
                placeholders.append(name)

    if not missing and not placeholders:
        print("All required environment variables are present and look filled.")
        return 0

    if missing:
        print("Missing values for:")
        for n in missing:
            print(f"  - {n}")
    if placeholders:
        print("Variables present but appear to be placeholders (e.g. start with YOUR_):")
        for n in placeholders:
            print(f"  - {n} (placeholder)")

    print()
    print("Next steps:")
    print("  1) Copy .env.example to .env and fill the real values, or export the variables in your shell before running uvicorn.")
    print("  2) Start the server in the same terminal: uvicorn requesthandler:app --reload")
    return 2

if __name__ == '__main__':
    sys.exit(main())
