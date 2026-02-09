"""Diagnostic script: dump raw API response for a Granola document.

Usage:
    python scripts/dump_api_response.py [document_id]

If no document_id is provided, fetches the first 3 documents from the list
endpoint and dumps them. This reveals ALL fields the API returns, including
any that are being silently discarded by the Pydantic model.
"""

import json
import sys
from pathlib import Path

import httpx

# Add src to path so we can import granola_sync
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from granola_sync.auth.credentials import load_credentials
from granola_sync.config import AppConfig

BASE_URL = "https://api.granola.ai"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Granola/5.354.0",
    "X-Client-Version": "5.354.0",
}


def main():
    # Load config and credentials
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if config_path.exists():
        config = AppConfig.from_yaml(config_path)
    else:
        config = AppConfig()

    tokens = load_credentials(config.credentials_path)
    auth = {"Authorization": f"Bearer {tokens.access_token}"}

    client = httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=30.0)

    doc_id = sys.argv[1] if len(sys.argv) > 1 else None

    if doc_id:
        print(f"\n=== Fetching single document: {doc_id} ===\n")

        # Batch endpoint (full details)
        resp = client.post(
            "/v1/get-documents-batch",
            json={"document_ids": [doc_id], "include_last_viewed_panel": True},
            headers=auth,
        )
        resp.raise_for_status()
        data = resp.json()
        doc_list = data if isinstance(data, list) else data.get("documents", [data])

        for doc in doc_list:
            _dump_document(doc, "batch")
    else:
        print("\n=== Fetching first 3 documents from list endpoint ===\n")

        resp = client.post(
            "/v2/get-documents",
            json={"limit": 3, "offset": 0, "include_last_viewed_panel": True},
            headers=auth,
        )
        resp.raise_for_status()
        data = resp.json()
        doc_list = data if isinstance(data, list) else data.get("documents", data.get("docs", []))

        for i, doc in enumerate(doc_list[:3]):
            _dump_document(doc, f"list[{i}]")

        # Also fetch the same docs via batch to compare
        if doc_list:
            doc_ids = [d["id"] for d in doc_list[:3]]
            print(f"\n=== Re-fetching same docs via batch endpoint ===\n")
            resp2 = client.post(
                "/v1/get-documents-batch",
                json={"document_ids": doc_ids, "include_last_viewed_panel": True},
                headers=auth,
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            batch_list = data2 if isinstance(data2, list) else data2.get("documents", [])
            for i, doc in enumerate(batch_list):
                _dump_document(doc, f"batch[{i}]")

    # Save full dump to file
    output_path = Path(__file__).resolve().parent / "api_dump.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull JSON saved to: {output_path}")

    client.close()


def _dump_document(doc: dict, label: str):
    """Print a summary of a document's fields."""
    print(f"--- {label}: {doc.get('title', '???')} (id={doc.get('id', '?')[:20]}...) ---")
    print(f"  ALL KEYS: {sorted(doc.keys())}")
    print()

    # Show each field with its type and a preview
    for key in sorted(doc.keys()):
        val = doc[key]
        if val is None:
            print(f"  {key}: null")
        elif isinstance(val, str):
            preview = val[:100].replace("\n", "\\n")
            print(f"  {key}: str[{len(val)}] = \"{preview}{'...' if len(val) > 100 else ''}\"")
        elif isinstance(val, dict):
            subkeys = list(val.keys())[:10]
            print(f"  {key}: dict[{len(val)} keys] = {subkeys}")
        elif isinstance(val, list):
            if val:
                first = type(val[0]).__name__
                print(f"  {key}: list[{len(val)}] of {first}")
                if isinstance(val[0], dict):
                    print(f"    [0] keys: {sorted(val[0].keys())}")
            else:
                print(f"  {key}: list[0] (empty)")
        elif isinstance(val, (int, float)):
            print(f"  {key}: {type(val).__name__} = {val}")
        elif isinstance(val, bool):
            print(f"  {key}: bool = {val}")
        else:
            print(f"  {key}: {type(val).__name__} = {val}")

    print()


if __name__ == "__main__":
    main()
