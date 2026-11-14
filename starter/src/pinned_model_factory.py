"""Reviewed pinned constructor bridge; live call disabled, test binding mocks only."""
import json
from pathlib import Path
from threading import Lock
from unittest.mock import Mock

from . import model_load_only as load, dev_authorization as auth, dev_bootstrap as boot
from .evaluation_runner import file_sha
from .schema import canonical_json


def validate_snapshot_inventory(*,root,model,snapshot_path,cache_dir):
    """Shared path/hash/inventory guard. Does not authorize or initialize runtime."""
    root=Path(root).resolve()
    if Path(snapshot_path)!=root/model['snapshot'] or Path(cache_dir)!=root/model['cache']:
        raise auth.AuthorizationError('Unapproved snapshot/cache path')
    boot.stage5_path(root,Path(cache_dir)/'.factory-check',category='embedding_cache')
    auth.verify_model_artifacts(root=root,model=model)
    snapshot=Path(snapshot_path)
    expected_files=set(model['profile']['artifact_sha256'])
    directories={parent.as_posix() for name in expected_files for parent in Path(name).parents if str(parent)!='.'}
    directories.add('2_Normalize')  # The built-in Normalize loader needs no weights/config.
    seen=set()
    for path in snapshot.rglob('*'):
        name=path.relative_to(snapshot).as_posix()
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise auth.AuthorizationError('Unsafe snapshot entry')
        if path.is_file():seen.add(name)
        elif not path.is_dir() or name not in directories:
            raise auth.AuthorizationError('Unapproved snapshot directory')
    if seen!=expected_files:raise auth.AuthorizationError('Unapproved snapshot inventory')
    return snapshot


class PinnedLocalModelFactory:
    """Exact planned MyEmbedder call, without importing or constructing that class.

    The public live call always fails. A test binding is not a security sandbox:
    constructor_double.side_effect is arbitrary trusted synthetic Python.
    """
    def __init__(self,*,root,request_canonical):
        self._root=Path(root).resolve();self._canonical=request_canonical
        request=json.loads(request_canonical)
        # Full regeneration, not merely the partial approval/schema verifier.
        actual=load.model_load_request(root=self._root,run_id=request['run_id'],executor_id=request['executor_id'],live=request.get('scope')==load.LIVE_SCOPE)
        if actual!=request_canonical:raise auth.AuthorizationError('Factory request identity mismatch')
        self._request=json.loads(actual)

    def __call__(self,model_name,*,revision,snapshot_path,cache_dir):
        raise PermissionError('PINNED_MODEL_FACTORY_LIVE_DISABLED')

    def synthetic_binding(self,*,constructor_double):
        if not isinstance(constructor_double,Mock):
            raise auth.AuthorizationError('Synthetic constructor Mock required')
        return Mock(side_effect=self._binding(constructor_double))

    def _live_binding(self):
        # Lazy import is reached only after the outer verified durable claim.
        def initialize(*args,**kwargs):
            from .embeddings import MyEmbedder
            return MyEmbedder(*args,**kwargs)
        return self._binding(initialize)

    def _binding(self,constructor):
        lock=Lock();attempted=False

        def construct(model_name,*,revision,snapshot_path,cache_dir):
            nonlocal attempted
            with lock:
                if attempted:raise auth.AuthorizationError('Factory already attempted; no retry')
                attempted=True
            spec=self._request['model'];root=self._root
            if (model_name!=load.MODEL or revision!=load.REVISION
                    or Path(snapshot_path)!=(root/spec['snapshot'])
                    or Path(cache_dir)!=(root/spec['cache'])
                    or canonical_json(self._request['factory_contract'])!=canonical_json(load.FACTORY_CONTRACT)):
                raise auth.AuthorizationError('Unapproved model/revision/path/cache/factory contract')
            boot.stage5_path(root,Path(cache_dir)/'.factory-check',category='embedding_cache')
            # This assertion only enforces ordering. The outer orchestrator must
            # independently verify manual approval and consume it first.
            auth.ConsumptionLedger(root=root).require_consumed(self._canonical)
            for name,expected in self._request['code_hashes'].items():
                path=root/name
                if not path.resolve().is_relative_to(root) or file_sha(path)!=expected:
                    raise auth.AuthorizationError('Factory code changed after approval')
            if file_sha(root/'results/full_corpus_embedding_preflight.json')!=self._request['source_evidence_sha256']:
                raise auth.AuthorizationError('Approved profile evidence changed')
            snapshot=validate_snapshot_inventory(root=root,model=spec,
                snapshot_path=snapshot_path,cache_dir=cache_dir)
            # Exact existing API: local_files_only/CPU/float32/eval are hard-coded
            # inside the hash-bound MyEmbedder, not unsupported extra kwargs.
            return constructor(model_name,revision=revision,snapshot_path=snapshot,
                                      cache_dir=Path(cache_dir),batch_size=16)

        return construct
