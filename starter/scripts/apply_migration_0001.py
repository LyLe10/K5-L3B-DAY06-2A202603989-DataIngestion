"""One-shot approved 0001 application, using the integration-tested psql contract.

No retry, repair, fixture insertion, schema replacement or history rewriting.
An existing target schema always stops this script, including after success.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.schema import load_migrations
from starter.scripts.check_schema_isolated import protected

CONTAINER = 'day6_student_starter-postgres-1'
CHECKSUM = '04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6'
CLUSTER = '7707847059457269799'

IDENTITY = """SELECT jsonb_build_object(
 'database',current_database(),'user',current_user,'version',current_setting('server_version'),
 'version_num',current_setting('server_version_num'),'encoding',current_setting('server_encoding'),
 'cluster',(SELECT system_identifier::text FROM pg_control_system()),
 'vector_version',(SELECT extversion FROM pg_extension WHERE extname='vector' AND extnamespace='public'::regnamespace),
 'schema',to_regnamespace('day6_ingestion')::text,
 'migration_tables',(SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')
  AND (table_name ILIKE '%migration%' OR table_name ILIKE '%schema_version%')),
 'can_create',has_database_privilege(current_user,current_database(),'CREATE'))"""

OUTSIDE = """SELECT encode(sha256(convert_to(coalesce(string_agg(item,E'\n' ORDER BY item),''),'UTF8')),'hex') FROM (
 SELECT 'schema:'||nspname||':'||nspowner||':'||coalesce(nspacl::text,'') AS item FROM pg_namespace
  WHERE nspname NOT IN ('pg_catalog','information_schema','day6_ingestion') AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp%'
 UNION ALL SELECT 'extension:'||extname||':'||extversion||':'||extnamespace::regnamespace::text FROM pg_extension
 UNION ALL SELECT 'function:'||pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname NOT IN ('pg_catalog','information_schema','day6_ingestion') AND n.nspname NOT LIKE 'pg_toast%' AND p.prokind='f'
 UNION ALL SELECT 'relation:'||n.nspname||':'||c.relname||':'||c.relkind::text||':'||c.relowner||':'||coalesce(c.relacl::text,'') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname NOT IN ('pg_catalog','information_schema','day6_ingestion') AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%'
) outside_objects"""

CATALOG = """SELECT jsonb_build_object(
 'schema',to_regnamespace('day6_ingestion')::text,
 'tables',(SELECT jsonb_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='day6_ingestion'),
 'views',(SELECT jsonb_agg(viewname ORDER BY viewname) FROM pg_views WHERE schemaname='day6_ingestion'),
 'functions',(SELECT jsonb_agg(p.proname ORDER BY p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='day6_ingestion'),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'table',c.relname,'definition',pg_get_triggerdef(t.oid,true)) ORDER BY t.tgname)
  FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='day6_ingestion' AND NOT t.tgisinternal),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('name',indexname,'table',tablename,'definition',indexdef) ORDER BY indexname) FROM pg_indexes WHERE schemaname='day6_ingestion'),
 'ledger',(SELECT jsonb_agg(to_jsonb(m) ORDER BY version) FROM day6_ingestion.schema_migrations m),
 'row_counts',jsonb_build_object('embedding_profiles',(SELECT count(*) FROM day6_ingestion.embedding_profiles),
  'strategy_snapshots',(SELECT count(*) FROM day6_ingestion.strategy_snapshots),'chunks',(SELECT count(*) FROM day6_ingestion.chunks)),
 'catalog_fingerprint',day6_ingestion.catalog_fingerprint())"""

VALIDATE = """DO $precommit$
DECLARE seen jsonb;
BEGIN
 %s INTO seen;
 IF seen->>'schema' <> 'day6_ingestion'
  OR seen->'tables' <> '["chunks","embedding_profiles","schema_migrations","strategy_snapshots"]'::jsonb
  OR seen->'views' <> '["compatible_snapshots"]'::jsonb
  OR seen->'functions' <> '["assert_snapshot_complete","catalog_fingerprint","guard_namespace","namespace_lock_key","reject_mutation"]'::jsonb
  OR jsonb_array_length(seen->'triggers') <> 10 OR jsonb_array_length(seen->'indexes') <> 8
  OR seen->'row_counts' <> '{"embedding_profiles":0,"strategy_snapshots":0,"chunks":0}'::jsonb
  OR jsonb_array_length(seen->'ledger') <> 1
  OR seen->'ledger'->0->'version' <> '1'::jsonb
  OR seen->'ledger'->0->>'name' <> '0001_day6_ingestion.sql'
  OR seen->'ledger'->0->>'checksum' <> '%s'
  OR seen->'ledger'->0->>'catalog_sha256' IS DISTINCT FROM seen->>'catalog_fingerprint'
 THEN RAISE EXCEPTION '0001 catalog/count/ledger validation failed'; END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint WHERE connamespace='day6_ingestion'::regnamespace AND NOT convalidated)
  OR EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relnamespace='day6_ingestion'::regnamespace AND (NOT i.indisvalid OR NOT i.indisready))
  OR NOT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid='day6_ingestion.chunks'::regclass AND attname='embedding' AND atttypid='public.vector'::regtype AND atttypmod=384 AND attnotnull)
 THEN RAISE EXCEPTION '0001 constraint/index/vector validation failed'; END IF;
END;
$precommit$;""" % (CATALOG, CHECKSUM)


def now():
    return datetime.now(timezone.utc).isoformat()


def psql(body):
    # Same executable, flags and stdin SQL mechanism as check_schema_isolated.py.
    # Only the explicitly approved container/user endpoint differs.
    result = subprocess.run(['docker','exec','-i',CONTAINER,'psql','-X','-q','-A','-t',
                             '-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose',
                             '-U','day6','-d','day6_lab'],input=body.encode(),capture_output=True)
    out, err = result.stdout.decode(errors='replace'), result.stderr.decode(errors='replace')
    match = re.search(r'ERROR:\s+([0-9A-Z]{5}):', err)
    return dict(returncode=result.returncode,stdout=out,stderr=err,
                sqlstate=match.group(1) if match else ('00000' if result.returncode==0 else None))


def checked(body):
    result = psql(body)
    if result['returncode']:
        raise RuntimeError('Read-only check failed: ' + result['stderr'])
    return result


def main():
    evidence = dict(started_at=now(),status='FAILED',target=dict(host='127.0.0.1',port=55433,database='day6_lab',container=CONTAINER),
                    commit_attempted=False,commit_confirmed=False)
    before = protected()
    try:
        migration, = load_migrations()
        integration = json.loads((ROOT/'results/schema_integration.json').read_bytes())
        if migration.version!=1 or migration.checksum!=CHECKSUM or integration['migration_sha256']!=CHECKSUM or integration['summary']!={'PASS':55,'FAIL':0,'BLOCKED':0}:
            raise RuntimeError('Approved SQL/registry/integration evidence mismatch')
        evidence['migration_sha256']=hashlib.sha256((ROOT/'starter/migrations'/migration.name).read_bytes()).hexdigest()
        pre = checked('BEGIN READ ONLY;'+IDENTITY+';'+OUTSIDE+';ROLLBACK;')
        evidence['precheck']=pre
        lines=pre['stdout'].strip().splitlines()
        identity=json.loads(lines[0]); outside=lines[1]
        if not (identity['database']=='day6_lab' and identity['user']=='day6' and identity['version_num']=='160016' and identity['encoding']=='UTF8'
                and identity['cluster']==CLUSTER and identity['vector_version']=='0.8.7' and identity['schema'] is None
                and identity['migration_tables']==0 and identity['can_create']):
            raise RuntimeError('Database preconditions changed; no write attempted')
        evidence['outside_catalog_before']=outside
        # Repeat identity/schema checks inside the ONE write transaction.
        guard="""DO $identity$ BEGIN
 IF current_database()<>'day6_lab' OR current_user<>'day6' OR current_setting('server_version_num')<>'160016'
 OR (SELECT system_identifier::text FROM pg_control_system())<>'%s'
 OR to_regnamespace('day6_ingestion') IS NOT NULL THEN RAISE EXCEPTION 'Write-transaction identity/schema check failed'; END IF;
END; $identity$;""" % CLUSTER
        outside_guard="""DO $outside$ DECLARE observed text; BEGIN %s INTO observed;
 IF observed<>'%s' THEN RAISE EXCEPTION 'Outside catalog changed; refusing commit'; END IF; END; $outside$;""" % (OUTSIDE,outside)
        body=("BEGIN;\n" + guard + "\nSELECT set_config('day6_ingestion.migration_checksum','"+CHECKSUM+"',true);\n"
              + migration.sql + '\n' + VALIDATE + '\n' + outside_guard
              + "\nSELECT 'PRECOMMIT:' || ("+CATALOG+")::text;\nSELECT 'TXID:' || pg_current_xact_id()::text;\nCOMMIT;\n")
        evidence['write_transaction_started_at']=now()
        evidence['commit_attempted']=True
        result=psql(body)
        evidence['transaction']=result
        if result['returncode']:
            evidence['transaction_result']='FAILED; psql ON_ERROR_STOP closed connection; no retry or repair'
            raise RuntimeError('Migration transaction failed; see SQLSTATE and stderr')
        evidence['commit_confirmed']=True
        evidence['committed_at_client_utc']=now()
        evidence['transaction_result']='COMMIT successful; SQLSTATE 00000'
        precommit_line=next(line for line in result['stdout'].splitlines() if line.startswith('PRECOMMIT:'))
        evidence['precommit_catalog']=json.loads(precommit_line[len('PRECOMMIT:'):])
        # New docker exec/psql process means a NEW database connection, read-only.
        post=psql('BEGIN READ ONLY;'+VALIDATE+'\n'+IDENTITY+';'+CATALOG+';'+OUTSIDE+';ROLLBACK;')
        evidence['postcommit']=post
        if post['returncode']:
            raise RuntimeError('Post-commit verification failed; migration will NOT be rerun or dropped')
        post_lines=post['stdout'].strip().splitlines()
        evidence['postcommit_identity']=json.loads(post_lines[0])
        evidence['postcommit_catalog']=json.loads(post_lines[1])
        evidence['outside_catalog_after']=post_lines[2]
        if evidence['postcommit_catalog']!=evidence['precommit_catalog'] or post_lines[2]!=outside or evidence['postcommit_identity']['cluster']!=CLUSTER:
            raise RuntimeError('Post-commit persistence/outside-catalog check failed; no repair attempted')
        evidence['status']='SUCCESS'
    except Exception as exc:
        evidence['error']=str(exc)
        print('FAILED:',str(exc),flush=True)
    evidence['protected_after']=protected()
    evidence['protected_before']=before
    evidence['protected_files_unchanged']=before==evidence['protected_after']
    if not evidence['protected_files_unchanged']:
        evidence['status']='FAILED'
        evidence['integrity_error']='Protected file inventory changed; no database repair attempted'
    evidence['finished_at']=now()
    (ROOT/'results/schema_apply.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:evidence.get(k) for k in ['status','commit_confirmed','transaction_result','protected_files_unchanged','error']},ensure_ascii=False),flush=True)
    return 0 if evidence['status']=='SUCCESS' else 1


if __name__=='__main__':
    raise SystemExit(main())
