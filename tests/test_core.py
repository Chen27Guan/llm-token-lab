import asyncio,math
import pytest
from fastapi.testclient import TestClient
from backend.app import app,Tracker,sse_objects,safe_url

def event(content='',tokens=None,usage=None):
    return {'choices':[{'delta':{'content':content},'logprobs':{'content':tokens or []}}], 'usage':usage}
def test_chunk_is_not_token():
    t=Tracker();t.consume(event('一次返回很多文字'));t.consume(event('更多'))
    assert t.chunks==2 and t.metrics()['completion_tokens'] is None
    assert not t.tokens

def test_multiple_tokens_share_observation_time():
    t=Tracker();t.consume(event('你好',[{'token':'你','logprob':-1,'top_logprobs':[]},{'token':'好','logprob':-2,'top_logprobs':[]}]))
    assert len(t.tokens)==2 and t.chunks==1
    assert t.tokens[0]['arrival_ms']==t.tokens[1]['arrival_ms']
    assert t.tokens[0]['token_id'] is None
    assert t.metrics()['true_itl_ms'] is None
    assert t.tokens[0]['probability']==pytest.approx(math.exp(-1))

def test_usage_overrides_observed_count():
    t=Tracker();t.consume(event('x',[{'token':'x','logprob':-.5}]))
    t.consume({'choices':[],'usage':{'completion_tokens':7,'prompt_tokens':9,'total_tokens':16}})
    assert t.metrics()['completion_tokens']==7
    assert t.metrics()['count_source']=='server_usage'

def test_non_stream_has_no_token_timing_or_ttft():
    t=Tracker();t.consume({'choices':[{'message':{'content':'你好'},'logprobs':{'content':[{'token':'你好','logprob':-.1}]}}]},False)
    assert t.ttft is None and t.tokens[0]['arrival_ms'] is None

def test_nonfinite_logprobs_are_unavailable():
    t=Tracker();t.consume(event('x',[{'token':'x','logprob':float('-inf')},{'token':'z','logprob':2}]))
    assert all(x['probability'] is None for x in t.tokens)

@pytest.mark.asyncio
async def test_sse_multiline_heartbeat_done():
    async def lines():
        for x in [': heartbeat','','data: {"choices":','data: []}','','data: [DONE]','']:
            yield x
    out=[x async for x in sse_objects(lines())]
    assert out==[{'choices':[]},None]

def test_endpoint_auth_and_key_redaction():
    with TestClient(app) as c:
        assert c.get('/api/history').status_code==401
        c.get('/api/session')
        r=c.post('/api/endpoints',json={'name':'secret test','url':'http://127.0.0.1:9999/v1','api_key':'DO-NOT-PERSIST'})
        assert r.status_code==200 and 'DO-NOT-PERSIST' not in r.text
        assert 'DO-NOT-PERSIST' not in c.get('/api/session').text
        assert c.post('/api/endpoints',headers={'Origin':'http://attacker.invalid'},json={'name':'x','url':'http://host/v1'}).status_code==403

def test_unsupported_parameter_rejected():
    with TestClient(app) as c:
        c.get('/api/session')
        r=c.post('/api/generate',json={'endpoint_id':'default','model':'x','prompt':'hi','logprobs':False,'top_k':3})
        assert r.status_code==422

def test_bad_url():
    for url in ['file:///etc/passwd','http://key:secret@host/v1','http://host/v1?key=x']:
        with pytest.raises(Exception):safe_url(url)
