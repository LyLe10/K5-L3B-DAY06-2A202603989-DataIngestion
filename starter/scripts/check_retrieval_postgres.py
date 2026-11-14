"""Bootstrap a NEW tmpfs PostgreSQL test cluster; never reads .env or main DB.

Explicit integration only. Requires local image; no pull, repair, test retry or
production snapshot. A failed test container is retained for manual review.
"""
import argparse
from datetime import datetime, timezone
import json
import importlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default='results/retrieval_postgres_integration.json')
    parser.add_argument('--suite',choices=('retrieval','cancellation'),default='retrieval')
    args=parser.parse_args()
    output=(ROOT/args.report).resolve()
    if output.parent!=ROOT/'results' or output.suffix!='.json' or output.exists():
        raise ValueError('Report must be a NEW JSON file directly under results/')
    os.chdir(ROOT)
    name='day6-store-test-retrieval-'+secrets.token_hex(5)
    password=secrets.token_hex(24)
    report=dict(started_at=datetime.now(timezone.utc).isoformat(),passed=False,
                production_connections=0,synthetic_only=True,errors=[])
    started=time.perf_counter()
    created=False
    def docker(*args,check=True):
        result=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=40)
        if check and result.returncode:
            raise RuntimeError('Docker command failed; no retry or production fallback')
        return result
    class Plugin:
        total=0
        outcomes=[]
        def pytest_collection_finish(self,session): self.total=len(session.items)
        def pytest_runtest_logreport(self,report):
            if report.when=='call' or report.failed:
                self.outcomes.append(dict(nodeid=report.nodeid,phase=report.when,outcome=report.outcome,
                                          seconds=report.duration,error=str(report.longrepr).replace(password,'[REDACTED]') if report.failed else None))
    plugin=Plugin()
    try:
        # Docker verifies target existence/isolation BEFORE any SQL connection.
        # The port bind fails rather than touching an existing container.
        env=dict(os.environ,POSTGRES_PASSWORD=password)
        command=['docker','run','--pull','never','-d','--name',name,'--label','day6.role=store-integration',
                 '--tmpfs','/var/lib/postgresql/data:rw','-p','127.0.0.1:55434:5432',
                 '-e','POSTGRES_DB=day6_lab','-e','POSTGRES_USER=tester','-e','POSTGRES_PASSWORD',
                 'pgvector/pgvector:0.8.7-pg16']
        result=subprocess.run(command,capture_output=True,text=True,env=env,timeout=40)
        if result.returncode: raise RuntimeError('Disposable bootstrap failed; no database connection attempted')
        created=True
        from starter.scripts.store_test_target import validate_container, integration_target, validate_identity
        info,=json.loads(docker('inspect',name).stdout)
        validate_container(info)
        # Readiness polling only, not migration/test retry.
        for attempt in range(40):
            if docker('exec',name,'pg_isready','-U','tester','-d','day6_lab',check=False).returncode==0: break
            time.sleep(0.25)
        else: raise RuntimeError('Disposable PostgreSQL readiness timeout')
        os.environ['DAY6_TEST_CONTAINER']=name
        os.environ['DAY6_TEST_PASSWORD']=password
        verified=integration_target()
        report['isolation']={k:v for k,v in verified.items() if k!='password'}
        report['isolation'].update(endpoint='127.0.0.1:55434',tmpfs_only=True,production_cluster_rejected=True,
                                   image_id=info['Image'])
        import psycopg
        import pytest
        from starter.src.schema import load_migrations
        module='postgres_cancellation_cases' if args.suite=='cancellation' else 'postgres_retrieval_cases'
        cases=importlib.import_module('starter.tests.'+module)
        from starter.tests.postgres_store_cases import DSN
        migration,=load_migrations()
        if migration.checksum!='04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6':
            raise ValueError('Migration checksum mismatch')
        with psycopg.connect(DSN,autocommit=True,connect_timeout=5) as conn:
            identity=conn.execute("SELECT current_database(),current_user,current_setting('server_version_num'),"
                                  '(SELECT system_identifier::text FROM pg_control_system())').fetchone()
            validate_identity(identity,verified['cluster'],extension=False)
            if conn.execute("SELECT to_regnamespace('day6_ingestion')").fetchone()!=(None,):
                raise ValueError('New disposable cluster unexpectedly has existing schema')
            conn.execute('CREATE EXTENSION vector')
            version=conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]
            validate_identity((*identity,version),verified['cluster'])
            with conn.transaction():
                conn.execute("SELECT set_config('day6_ingestion.migration_checksum',%s,true)",(migration.checksum,))
                conn.execute(migration.sql)
            report['database_identity']=identity
            report['pgvector']=version
            report['migration_checksum']=migration.checksum
        case_path='starter/tests/'+module+'.py'
        report['suite']=args.suite
        code=pytest.main(['-q','-x','--tb=short','-p','no:cacheprovider',case_path],plugins=[plugin])
        report['pytest_exit_code']=int(code)
        report['tests']=plugin.outcomes
        ran={r['nodeid'] for r in plugin.outcomes}
        report['summary']=dict(PASS=sum(r['outcome']=='passed' for r in plugin.outcomes),
                               FAIL=len({r['nodeid'] for r in plugin.outcomes if r['outcome']=='failed'}),
                               BLOCKED=plugin.total-len(ran))
        report['evidence']=next((m.EVIDENCE for m in list(sys.modules.values())
                                 if getattr(m,'__file__',None)==str(ROOT/case_path)
                                 and getattr(m,'EVIDENCE',[])),[])
        report['passed']=code==0
    except Exception as exc:
        report['errors'].append(dict(type=type(exc).__name__,message=str(exc).replace(password,'[REDACTED]'),
                                     sqlstate=getattr(exc,'sqlstate',None)))
    finally:
        if created and report['passed']:
            report['container_stopped']=docker('stop',name,check=False).returncode==0
        elif created:
            report['container_retained_for_review']=name
        report['seconds']=time.perf_counter()-started
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('passed','summary','errors','seconds')},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
