#!/usr/bin/env python3
"""
CLI for the KerfSuite Env/Secrets Service. No dependency on the rest of
this repo besides httpx - copy this single file into any project.

Config comes from env vars (so the API key never ends up in shell
history) or flags, flags win if both are given:
    ENV_SERVICE_URL       e.g. https://obs-env.kerfsuite.local
    ENV_SERVICE_API_KEY   a project API key (or the admin key)

Usage:
    python env_cli.py pull     --project kerfportal --environment production --output .env
    python env_cli.py push     --project kerfportal --environment production --file .env
    python env_cli.py validate --project kerfportal --environment production
    python env_cli.py list     --project kerfportal --environment production
"""
import argparse
import os
import stat
import sys

import httpx


def _config(args) -> tuple[str, str]:
    base_url = args.url or os.environ.get("ENV_SERVICE_URL")
    api_key = args.api_key or os.environ.get("ENV_SERVICE_API_KEY")
    if not base_url or not api_key:
        sys.exit("Set ENV_SERVICE_URL and ENV_SERVICE_API_KEY (or pass --url/--api-key).")
    return base_url.rstrip("/"), api_key


def _parse_dotenv(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].replace('\\"', '"').replace("\\n", "\n")
        entries[key] = value
    return entries


def cmd_pull(args):
    base_url, api_key = _config(args)
    resp = httpx.get(
        f"{base_url}/projects/{args.project}/secrets/{args.environment}/_/export",
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()

    output_path = args.output
    with open(output_path, "w") as f:
        f.write(resp.text)
    # Owner read/write only - this file has plaintext secrets in it now.
    os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)
    print(f"Wrote {output_path} (mode 600).")


def cmd_push(args):
    base_url, api_key = _config(args)
    with open(args.file) as f:
        entries = _parse_dotenv(f.read())

    if not entries:
        sys.exit(f"No KEY=VALUE entries found in {args.file}.")

    resp = httpx.put(
        f"{base_url}/projects/{args.project}/secrets/{args.environment}",
        json={"entries": entries},
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    print(f"Pushed {len(entries)} entries from {args.file}.")


def cmd_validate(args):
    base_url, api_key = _config(args)
    resp = httpx.get(
        f"{base_url}/projects/{args.project}/secrets/{args.environment}/_/validate",
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()

    if result["missing_required"]:
        print("MISSING required vars:")
        for key in result["missing_required"]:
            print(f"  - {key}")
    else:
        print("All required vars present.")

    if result["unrecognized"]:
        print("\nUnrecognized vars present (typo, or a template not assigned to this project?):")
        for key in result["unrecognized"]:
            print(f"  - {key}")

    if result["missing_required"]:
        sys.exit(1)


def cmd_list(args):
    base_url, api_key = _config(args)
    resp = httpx.get(
        f"{base_url}/projects/{args.project}/secrets/{args.environment}",
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    for row in resp.json():
        flag = " (sensitive)" if row["is_sensitive"] else ""
        print(f"{row['key']}{flag}  -  updated {row['updated_at']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Overrides ENV_SERVICE_URL")
    parser.add_argument("--api-key", help="Overrides ENV_SERVICE_API_KEY")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pull = sub.add_parser("pull", help="Write a project's secrets to a local .env file")
    p_pull.add_argument("--project", required=True)
    p_pull.add_argument("--environment", required=True)
    p_pull.add_argument("--output", default=".env")
    p_pull.set_defaults(func=cmd_pull)

    p_push = sub.add_parser("push", help="Upload a local .env file's entries")
    p_push.add_argument("--project", required=True)
    p_push.add_argument("--environment", required=True)
    p_push.add_argument("--file", default=".env")
    p_push.set_defaults(func=cmd_push)

    p_validate = sub.add_parser("validate", help="Check stored keys against assigned templates")
    p_validate.add_argument("--project", required=True)
    p_validate.add_argument("--environment", required=True)
    p_validate.set_defaults(func=cmd_validate)

    p_list = sub.add_parser("list", help="List stored keys (not values) for a project/environment")
    p_list.add_argument("--project", required=True)
    p_list.add_argument("--environment", required=True)
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.HTTPStatusError as exc:
        sys.exit(f"Request failed ({exc.response.status_code}): {exc.response.text}")


if __name__ == "__main__":
    main()
