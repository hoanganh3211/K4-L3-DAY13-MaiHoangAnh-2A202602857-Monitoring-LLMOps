"""Collect reproducible local practice evidence; never substitutes official challenge."""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from datetime import datetime, timezone
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.dashboard import aggregate


def main():
    evidence = ROOT / 'submission/evidence'
    evidence.mkdir(exist_ok=True)
    queries = [json.loads(s) for s in (ROOT / 'data/sample_queries.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    runs = []
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30) as client:
        health = client.get('/health').json()
        if any(health['incidents'].values()):
            raise RuntimeError('Disable existing incidents before collecting practice evidence')
        for scenario in (None, 'rag_slow', 'tool_fail', 'cost_spike', None):
            phase = scenario or ('baseline' if not runs else 'recovery')
            start = datetime.now(timezone.utc).isoformat()
            if scenario:
                client.post(f'/incidents/{scenario}/enable').raise_for_status()
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                    responses = list(pool.map(lambda q: client.post('/chat', json=q), queries))
            finally:
                if scenario:
                    client.post(f'/incidents/{scenario}/disable').raise_for_status()
            ids = {r.headers['x-request-id'] for r in responses}
            rows = [json.loads(s) for s in (ROOT / 'data/logs.jsonl').read_text(encoding='utf-8').splitlines()]
            rows = [r for r in rows if r.get('correlation_id') in ids]
            summary = aggregate(rows)
            runs.append({'phase': phase, 'start': start, 'end': datetime.now(timezone.utc).isoformat(),
                         'status_codes': [r.status_code for r in responses], 'correlation_ids': sorted(ids),
                         'metrics': summary})
            (evidence / f'practice-{phase}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
        (evidence / '11-dashboard-overview.html').write_text(client.get('/dashboard').text, encoding='utf-8')
        (evidence / 'local-runtime.json').write_text(json.dumps({'health': health, 'runs': runs}, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(runs, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
