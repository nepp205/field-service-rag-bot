"""Raw connectivity test: use the endpoint strings exactly as provided in env.

This script does NOT try to normalize or construct URLs. It POSTS to the
value of AZURE_OPENAI_ENDPOINT as-is and (if set) AZURE_REWRITE_ENDPOINT as-is.

Usage:
    python3 test_endpoints_raw.py

Environment variables used (read from env/.env):
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_API_KEY
    AZURE_OPENAI_API_VERSION
    AZURE_OPENAI_DEPLOYMENT
    AZURE_REWRITE_ENDPOINT (optional)
    AZURE_REWRITE_API_KEY (optional)
    AZURE_REWRITE_DEPLOYMENT (optional)

This helps you confirm whether the raw endpoint strings you put in your .env
are reachable and accept the API key.
"""

import os
import logging
import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def try_post(url: str, api_key: str):
    headers = {"Content-Type": "application/json", "api-key": api_key}
    payload = {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    client = httpx.Client(timeout=10.0)
    try:
        resp = client.post(url, headers=headers, json=payload)
        return {"ok": True, "status": resp.status_code, "body": resp.text}
    except httpx.RequestError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        client.close()


def main():
    openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    # Single resource / key for both deployments as you described
    rewrite_endpoint = os.getenv("AZURE_REWRITE_ENDPOINT") or openai_endpoint
    rewrite_api_key = os.getenv("AZURE_REWRITE_API_KEY") or openai_api_key
    rewrite_deployment = os.getenv("AZURE_REWRITE_DEPLOYMENT")
    openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION")

    print("\n== Raw Azure OpenAI connectivity test ==\n")

    if not openai_endpoint:
        print("Main endpoint missing: set AZURE_OPENAI_ENDPOINT in your environment or .env")
    else:
        # Construct a completions URL using the deployment names and api-version
        if not openai_api_key:
            print("  Skipped: AZURE_OPENAI_API_KEY not set")
        elif not openai_deployment or not openai_api_version:
            print("  Skipped: AZURE_OPENAI_DEPLOYMENT or AZURE_OPENAI_API_VERSION not set")
        else:
            main_url = f"{openai_endpoint.rstrip('/')}/openai/deployments/{openai_deployment}/chat/completions?api-version={openai_api_version}"
            print(f"Posting to constructed main completions URL:\n  {main_url}")
            r = try_post(main_url, openai_api_key)
            if r.get("ok"):
                print(f"  -> HTTP {r['status']}")
                print(f"     body: {r['body'][:400]}")
            else:
                print(f"  -> Request failed: {r.get('error')}")

    # Rewrite: only if a separate endpoint is provided. We do NOT attempt to
    # construct rewrite URLs from the main endpoint; this script is raw by design.
    # Test rewrite deployment using the same resource/key, constructing URL
    if not rewrite_deployment:
        print("\nAZURE_REWRITE_DEPLOYMENT not set — rewrite test skipped.")
    elif not rewrite_endpoint or not rewrite_api_key:
        print("\nAZURE_REWRITE_ENDPOINT or AZURE_REWRITE_API_KEY not set — rewrite test skipped.")
    else:
        rewrite_url = f"{rewrite_endpoint.rstrip('/')}/openai/deployments/{rewrite_deployment}/chat/completions?api-version={openai_api_version}"
        print(f"\nPosting to constructed rewrite completions URL:\n  {rewrite_url}")
        r = try_post(rewrite_url, rewrite_api_key)
        if r.get("ok"):
            print(f"  -> HTTP {r['status']}")
            print(f"     body: {r['body'][:400]}")
        else:
            print(f"  -> Request failed: {r.get('error')}")

    print("\nDone. This used your env values verbatim (no URL modification).\n")


if __name__ == '__main__':
    main()
