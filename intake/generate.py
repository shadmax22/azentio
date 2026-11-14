"""Main CLI generator for synthetic loan packets and ground-truth labels."""

import argparse
import json
import os
import random
from pathlib import Path
from intake.generator.scenarios import build_scenario_bucket
from intake.generator.generate_labels import create_label
from intake.generator.generate_packets import render_packet


def generate_dataset(total_packets: int = 40, seed: int = 7, out_dir: str = "data", as_of: str = "2026-03-15"):
    """Generate synthetic packets and ground-truth labels deterministically."""
    rng = random.Random(seed)
    out_path = Path(out_dir)
    packets_dir = out_path / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)

    labels_file = out_path / "labels.jsonl"
    scenarios = build_scenario_bucket(total_packets=total_packets, rng=rng)

    with open(labels_file, "w", encoding="utf-8") as f_labels:
        for idx, scenario in enumerate(scenarios, start=1):
            packet_id = f"pkt_{idx:03d}"

            # 1. Generate Ground Truth Label
            label = create_label(
                packet_id=packet_id,
                as_of=as_of,
                scenario=scenario,
                rng=rng
            )

            # Write label record to labels.jsonl (one JSON line per record)
            f_labels.write(label.model_dump_json() + "\n")

            # 2. Render Raw Packet (Zero Label Leakage)
            packet = render_packet(
                label=label,
                as_of=as_of,
                is_ambiguous_form=(scenario["flaw"] == "AMBIGUOUS_FORM"),
                rng=rng
            )

            packet_file = packets_dir / f"{packet_id}.json"
            with open(packet_file, "w", encoding="utf-8") as f_packet:
                json.dump(packet.model_dump(), f_packet, indent=2)

    print(f"Successfully generated {total_packets} packets in '{packets_dir}' and labels in '{labels_file}' (seed={seed})")


def main():
    parser = argparse.ArgumentParser(description="Synthetic loan application packet & ground-truth generator.")
    parser.add_argument("--packets", type=int, default=40, help="Number of packets to generate (default: 40)")
    parser.add_argument("--seed", type=int, default=7, help="Random number generator seed (default: 7)")
    parser.add_argument("--out", type=str, default="data", help="Output directory path (default: 'data')")
    parser.add_argument("--as-of", type=str, default="2026-03-15", help="Baseline evaluation date (default: '2026-03-15')")

    args = parser.parse_args()
    generate_dataset(
        total_packets=args.packets,
        seed=args.seed,
        out_dir=args.out,
        as_of=args.as_of
    )


if __name__ == "__main__":
    main()

