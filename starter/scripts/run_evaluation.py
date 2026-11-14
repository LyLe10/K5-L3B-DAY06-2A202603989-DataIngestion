"""Offline evaluation plan validation ONLY; runtime execution is not enabled here.

This checkpoint cannot load a model or connect PostgreSQL. Test planning still
requires a separate identity-bound approval artifact; no CLI flag bypasses it.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',required=True,choices=('dev','test'))
    parser.add_argument('--benchmark',type=Path,default=ROOT/'benchmark')
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--test-approval',type=Path)
    args=parser.parse_args()
    from starter.src.evaluation_runner import load_benchmark,evaluator_identity
    config=json.loads(args.config.read_text())
    approval=json.loads(args.test_approval.read_text()) if args.test_approval else None
    bundle=load_benchmark(args.benchmark,args.split,config=config,identity=evaluator_identity(),approval=approval)
    print(json.dumps(dict(status='PLAN_VALIDATED_EXECUTION_DISABLED',split=args.split,
                          question_count=len(bundle['questions']),freeze_sha256=bundle['freeze_sha256'])))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
