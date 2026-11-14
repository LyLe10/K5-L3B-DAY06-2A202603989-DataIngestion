"""Disabled live probe and mock-only one-shot identity/permission inspection."""
from threading import Lock
from unittest.mock import Mock

from . import dev_bootstrap as boot
from .retrieval import preflight, RetrievalBaseline
from .store import PgVectorStore

TARGET=dict(host='127.0.0.1',port=55433,dbname='day6_lab')
TABLES=('schema_migrations','embedding_profiles','strategy_snapshots','chunks')

# All identifiers are fixed. Role/namespace identities are bound parameters.
PERMISSIONS_SQL="""SELECT session_user, current_user,
 has_database_privilege(current_user,current_database(),'CONNECT'),
 has_schema_privilege(current_user,'day6_ingestion','USAGE'),
 has_schema_privilege(current_user,'public','USAGE'),
 has_function_privilege(current_user,'pg_catalog.pg_control_system()','EXECUTE'),
 has_function_privilege(current_user,'day6_ingestion.catalog_fingerprint()','EXECUTE'),
 EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND
   (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)),
 EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname<>session_user AND pg_has_role(session_user,r.oid,'MEMBER')),
 EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
   AND has_schema_privilege(current_user,n.oid,'CREATE')),
 has_database_privilege(current_user,current_database(),'CREATE'),
 EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p','v','m','f')
   AND has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')),
 EXISTS (SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE r.rolname=current_user
   UNION ALL SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE r.rolname=current_user
   UNION ALL SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE r.rolname=current_user
   UNION ALL SELECT 1 FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE r.rolname=current_user),
 has_database_privilege(current_user,current_database(),'TEMP'),
 current_setting('transaction_read_only'),current_setting('transaction_isolation'),
 current_setting('statement_timeout')"""


class ProbeBlocked(RuntimeError):
    pass


def execute_live_probe(**kwargs):
    if kwargs.get('authority') is None:
        raise PermissionError('LIVE_DATABASE_PROBE_DISABLED: independent verifier required')
    from .live_probe import execute
    return execute(**kwargs)


class OneShotOfflineProbe:
    """One attempt per instance, including failures. Only mock factories accepted.

    This is not an authorization token or cross-process replay protection. No
    live connector/DSN exists; future real execution needs a separately reviewed gate.
    """
    def __init__(self):
        self._lock=Lock();self._attempted=False

    def inspect(self,prepared,*,selected_role,connection_factory):
        with self._lock:
            if self._attempted:raise ProbeBlocked('BLOCKED: probe already attempted; no retry')
            self._attempted=True
        if not isinstance(connection_factory,Mock):
            raise ProbeBlocked('BLOCKED: offline mock connection factory required')
        if not isinstance(selected_role,str) or not selected_role.strip() or '\x00' in selected_role:
            raise ProbeBlocked('BLOCKED: explicit selected role required')
        return _inspect(prepared,selected_role=selected_role,connection_factory=connection_factory)


def _inspect(prepared,*,selected_role,connection_factory):
        try:
            baseline=prepared.baseline;p=prepared.profile;plan=prepared.plan
            if (type(baseline) is not RetrievalBaseline or baseline.dataset_id!=boot.DATASET
                    or baseline.profile_id!=p.profile_id or p.profile_id!=boot.STAGE4_PROFILE
                    or plan['split']!='dev' or plan['profile_id']!=p.profile_id
                    or tuple(s.snapshot_id for s in baseline.snapshots)!=boot.STAGE4_SNAPSHOTS
                    or tuple(s.expected_count for s in baseline.snapshots)!=(246,264)
                    or any(s.selected_page_count!=40 for s in baseline.snapshots)
                    or tuple(plan['descriptor_hashes'])!=baseline.descriptor_hashes):
                raise ValueError('Unapproved baseline')
            baseline.validate_approved_identity()
            expected=dict(host=TARGET['host'],port=55433,dbname='day6_lab',cluster=boot.CLUSTER,
                postgresql='16.16',pgvector='0.8.7',migration_sha256=boot.MIGRATION_SHA256,
                catalog_sha256=boot.APPROVED_CATALOG,read_only=True)
            if any(type(plan['database'].get(k)) is not type(v) or plan['database'].get(k)!=v for k,v in expected.items()):
                raise ValueError('Unapproved target')
            store=PgVectorStore('OFFLINE_CONNECTION_INJECTED',384,dataset_id=baseline.dataset_id,
                profile_id=p.profile_id,profile=p,context=prepared.context)
            details={}

            def factory(*,target,readonly):
                if target!=TARGET or readonly is not True:raise ValueError('Factory target mismatch')
                return connection_factory(target=dict(TARGET),selected_role=selected_role,readonly=True,
                    connect_timeout=5,autocommit=True,options='-c default_transaction_read_only=on')

            def inspect_inside(connection,*,privileged):
                if privileged:raise PermissionError('Privileged role')
                with connection.cursor() as cursor:
                    cursor.execute(PERMISSIONS_SQL)
                    row=cursor.fetchone()
                    if (not isinstance(row,tuple) or len(row)!=17 or row[:2]!=(selected_role,selected_role)
                            or any(type(v) is not bool for v in row[2:14])
                            or not all(row[2:7]) or any(row[7:13])
                            or row[14:]!=('on','repeatable read','10s')):
                        raise PermissionError('Role/permission/session identity mismatch')
                    details['warnings']=['TEMP_PRIVILEGE_PRESENT_QUERY_LIST_ONLY'] if row[13] else []
                    cursor.execute('SELECT c.relname,has_table_privilege(current_user,c.oid,\'SELECT\') '
                        'FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
                        'WHERE n.nspname=%s AND c.relkind=\'r\' ORDER BY c.relname',('day6_ingestion',))
                    rows=cursor.fetchall()
                    if (rows!=[(t,True) for t in sorted(TABLES)]
                            or any(type(row[1]) is not bool for row in rows)):
                        raise PermissionError('Required table SELECT grants mismatch')
                    cursor.execute('SELECT (SELECT count(*) FROM day6_ingestion.embedding_profiles),'
                        '(SELECT count(*) FROM day6_ingestion.strategy_snapshots),'
                        '(SELECT count(*) FROM day6_ingestion.chunks)')
                    counts=cursor.fetchone()
                    if counts!=(1,2,510) or any(type(v) is not int for v in counts):
                        raise ValueError('Global counts mismatch')
                    cursor.execute("SELECT set_config('lock_timeout','5000ms',true)")
                    cursor.execute("SELECT set_config('idle_in_transaction_session_timeout','15000ms',true)")
                # Shared existing guard verifies complete ledgers, namespace counts,
                # source/corpus/snapshot provenance and approved descriptor hashes.
                snapshots=preflight(store,connection,baseline)
                if tuple(snapshots)!=baseline.snapshots:raise ValueError('Unknown structural result')
                details['structural']='STRUCTURAL_INTEGRITY_VERIFIED'

            identity=boot.probe_database(dict(TARGET),factory,inspection=inspect_inside)
            if details.get('structural')!='STRUCTURAL_INTEGRITY_VERIFIED':raise ValueError('Unknown result')
            return dict(status='PASS',scope='OFFLINE_SYNTHETIC_PROBE',identity=identity,
                profile_id=p.profile_id,snapshot_ids=list(boot.STAGE4_SNAPSHOTS),
                counts=dict(profiles=1,snapshots=2,A=246,B=264,total=510),
                descriptor_hashes=list(baseline.descriptor_hashes),**details,
                vector_integrity='VECTOR_INTEGRITY_NOT_REVERIFIED')
        except Exception as error:
            # Do not print backend text/DSN, authenticate another role or retry.
            category='INSUFFICIENT_PRIVILEGES' if isinstance(error,PermissionError) or getattr(error,'sqlstate',None)=='42501' else 'IDENTITY_CONNECTION_OR_UNKNOWN_RESULT'
            raise ProbeBlocked('BLOCKED: '+category+'; no retry') from None
