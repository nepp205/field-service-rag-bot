"""Simple connectivity test for Azure OpenAI endpoints.

Reads relevant env vars (loads .env if present) and performs a minimal
POST to the chat/completions endpoint for the main deployment and, if
configured, the rewrite deployment. Prints concise results so you can see
which endpoint is reachable and whether the credentials are accepted.

Usage:
    python test_endpoints.py

This script intentionally sends a very small request (max_tokens=1).
Don't commit your .env to source control.
"""

import os
import json
import logging
from typing import Optional

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def normalize_base(endpoint: str) -> str:
    """Return a normalized base endpoint without trailing slash.

    If the provided endpoint already contains a path like '/openai' we
    still return it (caller will decide how to append)."""
    if not endpoint:
        return ""
    return endpoint.rstrip("/")


def build_completions_url(endpoint: str, deployment: str, api_version: str) -> Optional[str]:
    if not endpoint or not deployment or not api_version:
        return None
    ep = normalize_base(endpoint)
    # If endpoint already contains 'deployments' or '/openai/', assume it's a full path
    if "/deployments/" in ep or "/openai/" in ep:
        # ensure query param api-version exists
        if "api-version=" in ep:
            return ep
        sep = "?" if "?" not in ep else "&"
        return f"{ep}{sep}api-version={api_version}"

    # Standard Azure style endpoint for completions
    return f"{ep}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"


def try_request(url: str, api_key: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        # Azure typically accepts 'api-key' header for resource keys
        "api-key": api_key,
    }
    payload = {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    client = httpx.Client(timeout=10.0)
    try:
        resp = client.post(url, headers=headers, json=payload)
        return {"ok": True, "status_code": resp.status_code, "text": resp.text}
    except httpx.RequestError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        client.close()


def main():
    # Main model
    openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION")
    openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    # Rewrite (optional)
    rewrite_endpoint = os.getenv("AZURE_REWRITE_ENDPOINT")
    rewrite_api_key = os.getenv("AZURE_REWRITE_API_KEY")
    rewrite_api_version = os.getenv("AZURE_REWRITE_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION")
    rewrite_deployment = os.getenv("AZURE_REWRITE_DEPLOYMENT")

    print("\n== Azure OpenAI connectivity test ==\n")

    # Test main
    main_url = build_completions_url(openai_endpoint, openai_deployment, openai_api_version)
    if not main_url:
        print("Main endpoint: missing one of AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_API_KEY/AZURE_OPENAI_DEPLOYMENT/AZURE_OPENAI_API_VERSION")
    else:
        print(f"Testing main completions URL: {main_url}")
        if not openai_api_key:
            print("  Skipped: AZURE_OPENAI_API_KEY not set in environment")
        else:
            r = try_request(main_url, openai_api_key)
            if r.get("ok"):
                print(f"  -> HTTP {r['status_code']}")
                # print a shortened body
                snippet = (r["text"] or "").strip()
                if snippet:
                    print(f"     body: {snippet[:400]}")
            else:
                print(f"  -> Request failed: {r.get('error')}")

    # Test rewrite (optional)
    if rewrite_endpoint and rewrite_deployment and rewrite_api_key:
        rewrite_url = build_completions_url(rewrite_endpoint, rewrite_deployment, rewrite_api_version or "2024-05-01-preview")
        if not rewrite_url:
            print("Rewrite endpoint: missing info (endpoint/deployment/api_version)")
        else:
            print(f"\nTesting rewrite completions URL: {rewrite_url}")
            r = try_request(rewrite_url, rewrite_api_key)
            if r.get("ok"):
                print(f"  -> HTTP {r['status_code']}")
                snippet = (r["text"] or "").strip()
                if snippet:
                    print(f"     body: {snippet[:400]}")
            else:
                print(f"  -> Request failed: {r.get('error')}")
    else:
        print("\nRewrite test skipped: AZURE_REWRITE_ENDPOINT/AZURE_REWRITE_DEPLOYMENT/AZURE_REWRITE_API_KEY not fully set")

    print("\nDone. If you see 200/201 responses, connectivity and auth look OK.")


if __name__ == "__main__":
    main()
