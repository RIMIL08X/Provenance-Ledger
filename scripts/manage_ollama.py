"""Utility script to check, list, and pull models in Ollama."""

import argparse
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.interceptor.ollama_client import OllamaClient


def main():
    parser = argparse.ArgumentParser(description="Manage Ollama models for Provenance Ledger")
    parser.add_argument("--list", action="store_true", help="List downloaded models")
    parser.add_argument("--pull", type=str, help="Pull a specific model (e.g. llama3.2:1b, qwen2.5-coder:1.5b)")
    parser.add_argument("--pull-defaults", action="store_true", help="Pull recommended data science models")
    args = parser.parse_args()

    client = OllamaClient()
    if not client.is_available():
        print(f"Error: Ollama service is not reachable at {client.base_url}")
        print("Tip: Make sure the container is up with `docker compose -f docker/docker-compose.yml up -d`")
        sys.exit(1)

    if args.pull:
        print(f"Pulling model '{args.pull}' (this may take a minute depending on download speed)...")
        success = client.pull_model(args.pull)
        if success:
            print(f"Successfully downloaded '{args.pull}'!")
        else:
            print(f"Failed to pull '{args.pull}'.")

    elif args.pull_defaults:
        for model in client.RECOMMENDED_MODELS[:2]:  # Pull top 2 lightweight models
            print(f"\nPulling default model: {model}...")
            client.pull_model(model)
        print("\nDefault models configured.")

    # Always display current models
    models = client.list_models()
    print(f"\nAvailable Ollama Models ({len(models)} installed):")
    if models:
        for m in models:
            print(f" - {m}")
    else:
        print(" (No models downloaded yet. Run with `--pull llama3.2:1b` to download)")


if __name__ == "__main__":
    main()
