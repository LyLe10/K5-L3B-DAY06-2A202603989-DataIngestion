"""Validate draft/frozen integrity offline; no retrieval or independent gold certification."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.benchmark import validate_benchmark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', type=Path, default=ROOT/'benchmark')
    args = parser.parse_args()
    try:
        result = validate_benchmark(args.benchmark)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps(dict(status='BLOCKED', error=f'{type(exc).__name__}: {exc}')))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['structural_source_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
