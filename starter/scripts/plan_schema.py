"""Print verified migration inventory; intentionally has no database/apply option."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.schema import load_migrations


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    migrations = load_migrations()
    print(json.dumps({'mode': 'offline-review-only', 'schema': 'day6_ingestion',
                      'database_connected': False, 'ddl_executed': False,
                      'migrations': [dict(version=m.version, name=m.name, sha256=m.checksum)
                                     for m in migrations]}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
