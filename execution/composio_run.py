#!/usr/bin/env python3
"""Wrapper que llama al Composio CLI con JSON bien formado."""
import subprocess
import json
import sys
import os

COMPOSIO = os.path.expanduser("~/.composio/composio")
SPREADSHEET_ID = "1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE"

def run(tool, data: dict):
    result = subprocess.run(
        [COMPOSIO, "execute", tool, "-d", json.dumps(data)],
        capture_output=True, text=True
    )
    stdout = "\n".join(
        l for l in result.stdout.splitlines()
        if "Update available" not in l and "composio upgrade" not in l
    ).strip()
    if result.returncode != 0:
        print("ERROR:", result.stderr, file=sys.stderr)
        sys.exit(1)
    print(stdout)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: composio_run.py <TOOL> '<json>'")
        sys.exit(1)
    tool = sys.argv[1]
    data = json.loads(sys.argv[2])
    run(tool, data)
