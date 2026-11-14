"""DEV-ONLY offline preparation. Plan-only: no model, DB or evaluation execution."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',choices=('dev',),default='dev')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output',default='data/local/stage5/runs/planned-dev')
    args=parser.parse_args()
    from starter.src.dev_bootstrap import prepare_dev
    config=json.loads(args.config.read_text()) if args.config else None
    prepared=prepare_dev(split=args.split,config=config,output=args.output)
    print(json.dumps(prepared.plan,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
