import asyncio,json,time,uuid
from pathlib import Path
import httpx
BASE=__import__('os').environ.get('TOKENLAB_TEST_URL','http://127.0.0.1:38473').rstrip('/')+'/api'
async def main():
    results={}
    async with httpx.AsyncClient(timeout=180) as c:
        await c.get(BASE+'/session')
        models=(await c.get(BASE+'/endpoints/default/models')).json()['models']
        assert models
        model=models[0]
        probe=await c.post(BASE+'/endpoints/default/probe',json={'model':model});probe.raise_for_status()
        results['model']=model;results['capabilities']=probe.json()
        async def run(prompt='用一句话解释 Token。',logprobs=True,stream=True,cancel=False):
            rid=uuid.uuid4().hex;events=[];first=None;start=time.perf_counter()
            payload={'endpoint_id':'default','model':model,'prompt':prompt,'max_tokens':1024 if cancel else 40,'logprobs':logprobs,'stream':stream,'run_id':rid}
            async with c.stream('POST',BASE+'/generate',json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith('data:'):continue
                    e=json.loads(line[5:]);events.append(e)
                    if e['type']=='delta' and (e.get('text') or e.get('reasoning')) and first is None:
                        first=time.perf_counter()-start
                        if cancel:await c.post(BASE+'/runs/'+rid+'/cancel')
                    if e['type']=='done':break
            assert events[-1]['type']=='done',events[-1]
            report=events[-1]['report']
            if cancel:assert report['status']=='cancelled',report['status']
            else:assert report['status']=='completed',report
            if logprobs and not cancel:assert report['tokens'] and report['tokens'][0]['probability'] is not None
            if not stream:assert report['metrics']['ttft_ms'] is None
            return {'id':rid,'first_text_seconds':first,'total_observed_seconds':time.perf_counter()-start,'metrics':report['metrics'],'status':report['status'],'token_records':len(report['tokens'])}
        results['stream']=await run()
        assert results['stream']['first_text_seconds']<results['stream']['total_observed_seconds']
        results['without_logprobs']=await run(logprobs=False)
        results['non_stream']=await run(stream=False)
        t=time.perf_counter();a,b=await asyncio.gather(run('用两句话解释 SSE。'),run('用两句话解释 SSE。'))
        results['arena']={'A':a,'B':b,'wall_seconds':time.perf_counter()-t}
        results['cancel']=await run('请写一篇很长的计算机发展史，至少3000字。',cancel=True)
        hist=(await c.get(BASE+'/history')).json();results['history_count']=len(hist)
        assert len(hist)>=6
        health=(await c.get(BASE+'/health')).json();assert health['active_runs']==0
        results['health']=health
    Path('var/live-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False,indent=2))
asyncio.run(main())
