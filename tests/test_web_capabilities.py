"""Full supported surface, with tripwires installed before target imports."""
import json
from pathlib import Path
import subprocess
import sys


def test_fresh_supported_surface_and_each_source_owner_invariant(tmp_path):
    from operator_fixtures import make_operator_sources, capture_sources
    sources = make_operator_sources(tmp_path)
    baseline = capture_sources(sources)
    actions = ['factory', 'routes', 'reports', 'ack', 'observer', 'cli']
    for action in actions:
        registry = {**sources.probe_registry(), 'surface': action}
        result = subprocess.run([sys.executable, 'tests/capability_probe.py', '--module',
            'test_web_capabilities', '--action', 'exercise', '--registry', json.dumps(registry)],
            capture_output=True, text=True, timeout=35)
        assert result.returncode == 0, f'{action}: {result.stdout}\n{result.stderr}'
        proof = json.loads(result.stdout)
        assert proof['ok'] and not proof['shared_conftest']
        assert proof['result']['checked'] > 0
        assert capture_sources(sources) == baseline, action
