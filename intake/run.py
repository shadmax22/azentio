"""CLI runner to execute intake agent on a single loan application packet."""

import argparse
import json
import sys
from pathlib import Path
from intake.agent import run_agent


def main():
    parser = argparse.ArgumentParser(description="Run loan application intake agent on a packet JSON file.")
    parser.add_argument("packet_path", type=str, help="Path to packet JSON file, e.g. data/packets/pkt_001.json")
    parser.add_argument("--threshold", type=float, default=0.8, help="Confidence threshold (default: 0.8)")

    args = parser.parse_args()
    file_path = Path(args.packet_path)

    if not file_path.exists():
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            packet_data = json.load(f)
    except Exception as e:
        print(f"Error reading packet JSON: {e}", file=sys.stderr)
        sys.exit(1)

    result = run_agent(packet_data, confidence_threshold=args.threshold)
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()

