"""Pinned factory bridge tests: source inspection and synthetic constructors only."""
import ast
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from starter.src import pinned_model_factory as factory, model_load_only as load
from starter.src import dev_authorization as auth, dev_bootstrap as boot, database_probe
from starter.tests.test_store import profile as template_profile
from starter.tests.test_model_load_only import setup_model, FakeAdapter


def binding(s,constructor=None):
    bridge=factory.PinnedLocalModelFactory(root=s.root,request_canonical=s.request)
    constructor=constructor if constructor is not None else Mock(return_value=s.adapter)
    return bridge.synthetic_binding(constructor_double=constructor),constructor


def test_constructor_source_has_local_cpu_float32_eval_and_no_encode():
    path=Path(load.__file__).with_name('embeddings.py')
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MyEmbedder')
    init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    calls=[n for n in ast.walk(init) if isinstance(n,ast.Call)]
    call=next(n for n in calls if isinstance(n.func,ast.Name) and n.func.id=='SentenceTransformer')
    kwargs={kw.arg:kw.value for kw in call.keywords}
    assert ast.literal_eval(kwargs['local_files_only']) is True
    assert ast.literal_eval(kwargs['trust_remote_code']) is False
    assert ast.literal_eval(kwargs['device'])=='cpu'
    dtype=next(v for k,v in zip(kwargs['model_kwargs'].keys,kwargs['model_kwargs'].values) if ast.literal_eval(k)=='dtype')
    assert isinstance(dtype,ast.Attribute) and dtype.attr=='float32'
    methods=[n.func.attr for n in calls if isinstance(n.func,ast.Attribute)]
    assert 'eval' in methods
    assert not {'encode','embed_query','embed_documents','_embed','forward','connect','_connect'}&set(methods)
    config=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_configure')
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
        and n.func.attr in ('mkdir','open','write_text','_write_cache','encode') for n in ast.walk(config))


def test_bridge_cannot_initialize_before_claim(setup_model):
    s=setup_model;wrapped,constructor=binding(s)
    with pytest.raises(auth.AuthorizationError,match='consumption'):
        wrapped(load.MODEL,revision=load.REVISION,snapshot_path=s.snapshot,cache_dir=s.adapter._cache_dir)
    constructor.assert_not_called()
    assert not (s.root/'data/local/stage5/authorization').exists()


def test_approved_mock_bridge_calls_exact_constructor_once(setup_model,monkeypatch):
    s=setup_model
    def construct(*args,**kwargs):
        auth.ConsumptionLedger(root=s.root).require_consumed(s.request)
        return s.adapter
    constructor=Mock(side_effect=construct);wrapped,_=binding(s,constructor)
    from starter.src import evaluation_runner,store
    forbidden=Mock(side_effect=AssertionError('Forbidden operation'))
    monkeypatch.setattr(store.PgVectorStore,'_connect',forbidden)
    monkeypatch.setattr(evaluation_runner,'run_evaluation',forbidden)
    monkeypatch.setattr(evaluation_runner.QueryProducer,'prepare',forbidden)
    result=load.simulate_model_load_only(**(s.kw|dict(model_factory=wrapped)))
    assert result['status']=='MODEL_LOAD_VERIFIED' and result['execution_mode']=='OFFLINE_SYNTHETIC'
    constructor.assert_called_once_with(load.MODEL,revision=load.REVISION,snapshot_path=s.snapshot,
                                       cache_dir=s.adapter._cache_dir,batch_size=16)
    forbidden.assert_not_called();s.adapter.embed_query.assert_not_called();s.adapter.embed_documents.assert_not_called()
    assert not (s.root/'data/local/stage5/embedding_cache').exists()


@pytest.mark.parametrize('bad',['model','revision','snapshot','cache'])
def test_wrong_constructor_inputs_rejected_before_initialization(setup_model,bad):
    s=setup_model;wrapped,constructor=binding(s)
    decision=load.verify_model_load_approval(s.request,s.kw['approval'],authority=s.authority)
    auth.ConsumptionLedger(root=s.root).consume(s.request,decision.grant)
    args=dict(revision=load.REVISION,snapshot_path=s.snapshot,cache_dir=s.adapter._cache_dir)
    name=load.MODEL
    if bad=='model':name='wrong/model'
    elif bad=='revision':args['revision']='0'*40
    elif bad=='snapshot':args['snapshot_path']=s.root/'other'
    else:args['cache_dir']=s.root/'data/local/stage4/embedding_cache'
    with pytest.raises(auth.AuthorizationError):wrapped(name,**args)
    constructor.assert_not_called()


@pytest.mark.parametrize('extra',['adapter_config.json','config_sentence_transformers.json','unapproved.py'])
def test_optional_unpinned_config_or_code_blocks_constructor(setup_model,extra):
    s=setup_model;wrapped,constructor=binding(s)
    (s.snapshot/extra).write_text('synthetic unapproved extra')
    with pytest.raises(load.ModelLoadPreparationError):load.simulate_model_load_only(**(s.kw|dict(model_factory=wrapped)))
    constructor.assert_not_called()


def test_profile_mismatch_is_not_repaired_and_approval_stays_consumed(setup_model):
    s=setup_model
    wrong=FakeAdapter(s.profile,s.adapter._cache_dir);wrong.profile_id='0'*64
    wrapped,constructor=binding(s,Mock(return_value=wrong))
    with pytest.raises(load.ModelLoadPreparationError):load.simulate_model_load_only(**(s.kw|dict(model_factory=wrapped)))
    constructor.assert_called_once()
    auth.ConsumptionLedger(root=s.root).require_consumed(s.request)


def test_initialization_error_has_no_retry(setup_model):
    s=setup_model;wrapped,constructor=binding(s,Mock(side_effect=RuntimeError('DO_NOT_EXPORT')))
    with pytest.raises(load.ModelLoadPreparationError):load.simulate_model_load_only(**(s.kw|dict(model_factory=wrapped)))
    with pytest.raises(auth.AuthorizationError):
        wrapped(load.MODEL,revision=load.REVISION,snapshot_path=s.snapshot,cache_dir=s.adapter._cache_dir)
    constructor.assert_called_once()


def test_factory_code_hash_and_contract_bound_to_request(setup_model):
    s=setup_model;request=json.loads(s.request)
    assert 'starter/src/pinned_model_factory.py' in request['code_hashes']
    assert request['factory_contract']==load.FACTORY_CONTRACT
    bridge=factory.PinnedLocalModelFactory(root=s.root,request_canonical=s.request)
    constructor=Mock(return_value=s.adapter);wrapped=bridge.synthetic_binding(constructor_double=constructor)
    code=s.root/'starter/src/pinned_model_factory.py';code.write_bytes(code.read_bytes()+b'\n# changed\n')
    with pytest.raises(auth.AuthorizationError):load.simulate_model_load_only(**(s.kw|dict(model_factory=wrapped)))
    constructor.assert_not_called()


def test_all_live_entries_and_real_constructor_binding_disabled(setup_model):
    s=setup_model;bridge=factory.PinnedLocalModelFactory(root=s.root,request_canonical=s.request)
    with pytest.raises(PermissionError,match='DISABLED'):
        bridge(load.MODEL,revision=load.REVISION,snapshot_path=s.snapshot,cache_dir=s.adapter._cache_dir)
    with pytest.raises(auth.AuthorizationError):bridge.synthetic_binding(constructor_double=lambda:None)
    with pytest.raises(PermissionError):load.execute_model_load_only()
    with pytest.raises(PermissionError):boot.execute_dev()
    with pytest.raises(PermissionError):database_probe.execute_live_probe()
