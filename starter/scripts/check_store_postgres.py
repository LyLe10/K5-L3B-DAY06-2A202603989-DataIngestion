"""Run explicit integration cases ONLY against a verified disposable Docker cluster."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', default='results/store_postgres_integration_run.json')
    args=parser.parse_args()
    output=(ROOT/args.report).resolve()
    if output.parent != ROOT/'results' or output.suffix != '.json' or output.exists():
        raise ValueError('Report must be a NEW JSON file directly under results/')
    import psycopg
    import pytest
    from dotenv import dotenv_values
    from starter.src.schema import load_migrations
    from starter.tests import postgres_store_cases as cases
    from starter.scripts.store_test_target import integration_target, validate_identity

    report=dict(started_at=datetime.now(timezone.utc).isoformat(),passed=False,errors=[])
    started=perf_counter()
    # Production is used only by this read-only snapshot function, never by a store.
    def main_snapshot():
        url=dotenv_values(ROOT/'starter/.env')['DATABASE_URL']
        with psycopg.connect(url,connect_timeout=5,options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
            row=conn.execute("SELECT current_database(),current_setting('transaction_read_only'),"
                '(SELECT system_identifier::text FROM pg_control_system()),'
                '(SELECT count(*) FROM day6_ingestion.embedding_profiles),'
                '(SELECT count(*) FROM day6_ingestion.strategy_snapshots),(SELECT count(*) FROM day6_ingestion.chunks),'
                'day6_ingestion.catalog_fingerprint(),(SELECT jsonb_agg(to_jsonb(m)) FROM day6_ingestion.schema_migrations m)').fetchone()
            assert row[:3]==('day6_lab','on','7707847059457269799')
            conn.rollback()
            return list(row)

    class EvidencePlugin:
        total=0
        outcomes=[]
        def pytest_collection_finish(self,session): self.total=len(session.items)
        def pytest_runtest_logreport(self,report):
            if report.when=='call' or report.failed:
                self.outcomes.append(dict(nodeid=report.nodeid,phase=report.when,outcome=report.outcome,
                                          seconds=report.duration,error=str(report.longrepr) if report.failed else None))

    plugin=EvidencePlugin()
    try:
        verified=integration_target()
        report['disposable_target']={k:v for k,v in verified.items() if k!='password'}
        report['production_before']=main_snapshot()
        migration,=load_migrations()
        assert migration.checksum=='04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6'
        # Fixed endpoint + cluster fingerprint: never accept DATABASE_URL or fallback.
        with psycopg.connect(cases.DSN,autocommit=True,connect_timeout=5) as conn:
            identity=conn.execute("SELECT current_database(),current_user,current_setting('server_version_num'),(SELECT system_identifier::text FROM pg_control_system()),to_regnamespace('day6_ingestion')::text").fetchone()
            validate_identity(identity[:4], cases.TEST_CLUSTER, extension=False)
            if identity[4] is not None:
                raise ValueError('Test schema already exists; use a new disposable container')
            conn.execute('CREATE EXTENSION vector')
            assert conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()==('0.8.7',)
            with conn.transaction():
                conn.execute("SELECT set_config('day6_ingestion.migration_checksum',%s,true)",(migration.checksum,))
                conn.execute(migration.sql)
            report['test_identity']=identity
            report['migration_sha256']=migration.checksum
            report['migration_sqlstate']='00000'
        code=pytest.main(['-q','-x','--tb=short','-p','no:cacheprovider','starter/tests/postgres_store_cases.py'],plugins=[plugin])
        report['pytest_exit_code']=int(code)
        report['tests']=plugin.outcomes
        ran={r['nodeid'] for r in plugin.outcomes}
        report['summary']=dict(PASS=sum(r['outcome']=='passed' for r in plugin.outcomes),
                               FAIL=len({r['nodeid'] for r in plugin.outcomes if r['outcome']=='failed'}),
                               BLOCKED=plugin.total-len(ran))
        # pytest can import the case file under a different module name; retain its evidence.
        report['evidence']=next((m.EVIDENCE for m in list(sys.modules.values())
                                 if getattr(m,'__file__',None)==str(ROOT/'starter/tests/postgres_store_cases.py') and getattr(m,'EVIDENCE',[])),[])
        report['passed']=code==0
    except Exception as exc:
        report['errors'].append(dict(type=type(exc).__name__,message=str(exc),sqlstate=getattr(exc,'sqlstate',None)))
    finally:
        report['production_after']=main_snapshot()
        report['production_unchanged']=report.get('production_before')==report['production_after']
        if not report['production_unchanged']: report['passed']=False
        report['total_seconds']=perf_counter()-started
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ['passed','summary','errors','production_unchanged','total_seconds']},indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
