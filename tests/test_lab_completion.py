from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest

from app import agent as agent_module, logging_config
from app.main import app
from app.pii import scrub_text, scrub_value
from app.dashboard import aggregate
from app.metrics import percentile


@pytest.mark.parametrize('value,kind', [
    ('012345678901', 'CCCD'), ('4111 1111 1111 1111', 'CREDIT_CARD'),
    ('0123-4567-8901-2345', 'CREDIT_CARD'), ('test@example.com', 'EMAIL'),
    ('+84 90 123 4567', 'PHONE_VN'),
])
def test_pii_categories(value, kind):
    assert scrub_text(value) == f'[REDACTED_{kind}]'


def test_recursive_scrub():
    assert scrub_value({'detail': [{'nested': 'test@example.com'}]}) == {
        'detail': [{'nested': '[REDACTED_EMAIL]'}]}


def test_concurrent_request_context_and_failure_headers(monkeypatch, tmp_path):
    log_path = tmp_path / 'requests.jsonl'
    monkeypatch.setattr(logging_config, 'LOG_PATH', log_path)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            async def send(i):
                return await client.post('/chat', headers={'x-request-id': f'req-{i:08x}'},
                    json={'user_id': f'u{i}', 'session_id': f's{i}', 'message': 'monitoring'})
            results = await asyncio.gather(*(send(i) for i in range(6)))
            for i, response in enumerate(results):
                assert response.headers['x-request-id'] == f'req-{i:08x}'
                assert response.json()['correlation_id'] == response.headers['x-request-id']
                assert float(response.headers['x-response-time-ms']) >= 0
            def fail(message):
                raise RuntimeError('Unavailable for test@example.com')
            monkeypatch.setattr(agent_module, 'retrieve', fail)
            response = await send(7)
            assert response.status_code == 500
            assert response.headers['x-request-id'] == 'req-00000007'
    asyncio.run(run())
    raw = log_path.read_text(encoding='utf-8')
    assert 'test@example.com' not in raw
    for row in map(json.loads, raw.splitlines()):
        if row.get('service') == 'api':
            i = int(row['correlation_id'][4:], 16)
            assert row['session_id'] == f's{i}'
            assert row['model'] and row['env'] and row['user_id_hash']


def test_generation_usage_cost_and_safe_preview(monkeypatch):
    client = Mock()
    monkeypatch.setattr(agent_module, 'get_langfuse_client', lambda: client)
    from app.prompt_management import ResolvedPrompt
    agent = agent_module.LabAgent()
    response = agent._generate.__wrapped__(agent, ResolvedPrompt(
        text='test@example.com', name='test', label='baseline', version='local-v1', source='local'))
    first, last = [c.kwargs for c in client.update_current_generation.call_args_list]
    assert 'test@example.com' not in first['input']['prompt_preview']
    assert last['usage_details']['input'] == response.usage.input_tokens
    assert sum(last['cost_details'].values()) == pytest.approx(agent._estimate_cost(response.usage.input_tokens, response.usage.output_tokens))


def test_dashboard_denominators_and_percentiles():
    common = {'ts': '2026-09-30T10:00:00+00:00'}
    rows = [dict(common, event='request_received') for _ in range(2)]
    rows += [dict(common, event='request_failed', error_type='RuntimeError', tool_name='retrieval', tool_success=False)]
    rows += [dict(common, event='response_sent', latency_ms=200, ttft_ms=50,
                  cost_usd=.002, tokens_in=20, tokens_out=80, quality_score=.8,
                  tool_name='retrieval', tool_success=True)]
    result = aggregate(rows)
    assert result['errors'] == {'Error rate': 50, 'Retrieval success': 50}
    assert result['total_cost'] == .002
    assert result['count'] == 2
    assert percentile([100, 200, 300, 400], 50) == 200
    assert aggregate([])['errors']['Retrieval success'] is None
