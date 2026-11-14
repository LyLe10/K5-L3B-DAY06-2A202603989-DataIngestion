"""Fail-closed discovery of a disposable Docker test target; never uses DATABASE_URL."""
from functools import lru_cache
import json
import os
import re
import subprocess

PRODUCTION_CLUSTER = '7707847059457269799'
# Migration 0001 pins this name. Isolation is established by container/endpoint/
# independently discovered cluster identity, never by the database name alone.
TEST_DATABASE = 'day6_lab'


def validate_container(info):
    config, host = info['Config'], info['HostConfig']
    if (not info['State']['Running'] or config.get('Labels', {}).get('day6.role') != 'store-integration'
            or host.get('Privileged') or host.get('Binds')
            or host.get('NetworkMode') in ('host', 'none')
            or host.get('NetworkMode', '').startswith('container:')
            or any(m.get('Type') != 'tmpfs' for m in info.get('Mounts', []))
            or host.get('Tmpfs') != {'/var/lib/postgresql/data': 'rw'}):
        raise ValueError('Target must be a labeled, running, unprivileged tmpfs-only disposable container')
    ports = info['NetworkSettings']['Ports']
    if ports != {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '55434'}]}:
        raise ValueError('Test port must be exclusively 127.0.0.1:55434')
    env = dict(item.split('=', 1) for item in config['Env'] if '=' in item)
    if env.get('POSTGRES_DB') != TEST_DATABASE or env.get('POSTGRES_USER') != 'tester':
        raise ValueError('Only the migration-required database name and disposable tester role are allowed')


def validate_identity(row, cluster, *, extension=True):
    wanted = (TEST_DATABASE, 'tester', '160016', cluster)
    if (not re.fullmatch(r'[0-9]+', cluster) or cluster == PRODUCTION_CLUSTER
            or tuple(row[:4]) != wanted or (extension and row[4:] != ('0.8.7',))):
        raise ValueError('Test SQL identity/version does not match the verified disposable container')


@lru_cache(maxsize=1)
def integration_target():
    name = os.environ.get('DAY6_TEST_CONTAINER', '')
    password = os.environ.get('DAY6_TEST_PASSWORD', '')
    if not re.fullmatch(r'day6-store-test-[a-z0-9-]+', name) or not password:
        raise ValueError('Set DAY6_TEST_CONTAINER and a disposable DAY6_TEST_PASSWORD explicitly')
    def docker(*args):
        result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ValueError('Docker target verification failed; no database write permitted')
        return result.stdout
    info, = json.loads(docker('inspect', name))
    validate_container(info)
    cluster = docker('exec', name, 'psql', '-XAt', '-U', 'tester', '-d', TEST_DATABASE,
                     '-c', 'SELECT system_identifier::text FROM pg_control_system()').strip()
    if not re.fullmatch(r'[0-9]+', cluster) or cluster == PRODUCTION_CLUSTER:
        raise ValueError('Production or invalid cluster rejected')
    return dict(container=name, container_id=info['Id'], cluster=cluster, password=password)
