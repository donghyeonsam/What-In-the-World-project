"""Create deterministic nested 50K/100K/150K/200K JSONL inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


DEFAULT_SIZES = (50_000, 100_000, 150_000, 200_000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sizes = tuple(sorted(set(args.sizes)))
    if not sizes or sizes[0] < 1:
        raise SystemExit("sizes must contain positive integers")
    if not args.source.is_file():
        raise SystemExit(f"source does not exist: {args.source}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        size: args.output_dir / f"silver-{size:06d}.jsonl" for size in sizes
    }
    temporary = {size: path.with_suffix(path.suffix + ".tmp") for size, path in targets.items()}
    handles = {size: path.open("wb") for size, path in temporary.items()}
    digests = {size: hashlib.sha256() for size in sizes}
    counts = {size: 0 for size in sizes}

    source_count = 0
    try:
        with args.source.open("rb") as source:
            for source_count, line in enumerate(source, start=1):
                if source_count > sizes[-1]:
                    break
                for size in sizes:
                    if source_count <= size:
                        handles[size].write(line)
                        digests[size].update(line)
                        counts[size] += 1
    finally:
        for handle in handles.values():
            handle.close()

    if source_count < sizes[-1]:
        for path in temporary.values():
            path.unlink(missing_ok=True)
        raise SystemExit(
            f"source has only {source_count:,} rows; {sizes[-1]:,} are required"
        )

    entries = []
    for size in sizes:
        if counts[size] != size:
            raise RuntimeError(f"unexpected row count for {size}: {counts[size]}")
        os.replace(temporary[size], targets[size])
        entries.append(
            {
                "rows": size,
                "file": targets[size].name,
                "bytes": targets[size].stat().st_size,
                "sha256": digests[size].hexdigest(),
            }
        )

    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"source": args.source.name, "datasets": entries}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    for entry in entries:
        print(f"{entry['rows']:>7,} rows  {entry['sha256']}  {entry['file']}")


if __name__ == "__main__":
    main()
