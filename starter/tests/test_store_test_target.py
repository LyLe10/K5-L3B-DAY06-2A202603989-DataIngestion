"""Offline tests for the disposable target guard; no Docker/SQL connection."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from starter.scripts.store_test_target import (
    validate_container, validate_identity, integration_target, PRODUCTION_CLUSTER,
)


@pytest.fixture
def info():
    return dict(Id='isolated-id', State={'Running': True},
        Config={'Labels': {'day6.role': 'store-integration'},
                'Env': ['POSTGRES_DB=day6_lab', 'POSTGRES_USER=tester']},
        HostConfig={'Privileged': False, 'Binds': None, 'NetworkMode': 'bridge',
                    'Tmpfs': {'/var/lib/postgresql/data': 'rw'}},
        Mounts=[], NetworkSettings={'Ports': {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '55434'}]}})


def test_valid_container(info):
    validate_container(info)


@pytest.mark.parametrize('part,key,value', [
    ('State','Running',False), ('Config','Labels',{}),
    ('Config','Env',['POSTGRES_DB=wrong_database','POSTGRES_USER=tester']),
    ('Config','Env',['POSTGRES_DB=day6_lab','POSTGRES_USER=day6']),
    ('HostConfig','Privileged',True), ('HostConfig','Binds',['main:/var/lib/postgresql/data']),
    ('HostConfig','Tmpfs',{}), ('HostConfig','NetworkMode','host'),
    ('HostConfig','NetworkMode','container:production'),
    ('NetworkSettings','Ports',{'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'55433'}]}),
    ('NetworkSettings','Ports',{'5432/tcp':[{'HostIp':'0.0.0.0','HostPort':'55434'}]}),
])
def test_container_rejects_unsafe_configuration(info,part,key,value):
    info[part][key]=value
    with pytest.raises(ValueError): validate_container(info)


def test_volume_mount_rejected(info):
    info['Mounts']=[{'Type':'volume'}]
    with pytest.raises(ValueError): validate_container(info)


@pytest.mark.parametrize('row,cluster', [
    (('wrong_database','tester','160016','123','0.8.7'),'123'),
    (('day6_lab','day6','160016','123','0.8.7'),'123'),
    (('day6_lab','tester','160015','123','0.8.7'),'123'),
    (('day6_lab','tester','160016','124','0.8.7'),'123'),
    (('day6_lab','tester','160016','123','0.8.6'),'123'),
    (('day6_lab','tester','160016',PRODUCTION_CLUSTER,'0.8.7'),PRODUCTION_CLUSTER),
])
def test_identity_rejects_wrong_target(row,cluster):
    with pytest.raises(ValueError): validate_identity(row,cluster)


def test_new_cluster_identity_accepted():
    validate_identity(('day6_lab','tester','160016','123','0.8.7'),'123')


def test_missing_configuration_never_uses_database_url(monkeypatch):
    integration_target.cache_clear()
    monkeypatch.delenv('DAY6_TEST_CONTAINER',raising=False)
    monkeypatch.setenv('DATABASE_URL','synthetic://must-not-be-read')
    with pytest.raises(ValueError): integration_target()


def test_discover_cluster_from_verified_container(info,monkeypatch):
    integration_target.cache_clear()
    monkeypatch.setenv('DAY6_TEST_CONTAINER','day6-store-test-unit')
    monkeypatch.setenv('DAY6_TEST_PASSWORD','synthetic-unit-only')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout=json.dumps([info]) if args[1]=='inspect' else '123\n')
    monkeypatch.setattr('starter.scripts.store_test_target.subprocess.run',run)
    result=integration_target()
    assert result['cluster']=='123' and result['container_id']=='isolated-id'
    assert calls[1][-1].startswith('SELECT ') and 'day6_lab' in calls[1]
    integration_target.cache_clear()
