from __future__ import annotations
import asyncio, json, math, secrets, time, uuid, os, socket, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'var').mkdir(exist_ok=True)
from sqlalchemy.pool import StaticPool
if os.environ.get('TOKENLAB_TEST')=='1':
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
else:
    # NAS does not support SQLite byte-range locks. Hold a kernel-level abstract
    # socket for exclusive process ownership and share one synchronous connection.
    db_guard=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    db_guard.bind('\0token-lab-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:24])
    engine=create_engine('sqlite:///file:'+str(ROOT/'var/history.sqlite')+'?mode=rwc&nolock=1&uri=true',connect_args={'check_same_thread':False},poolclass=StaticPool)
Base=declarative_base()
class RunRow(Base):
    __tablename__='runs'
    id=Column(String,primary_key=True)
    owner=Column(String,index=True)
    created=Column(String)
    payload=Column(Text)
Base.metadata.create_all(engine)
DB=sessionmaker(engine)
app=FastAPI(title='LLM Token Lab',version='1.0.0')
sessions={}
active={}
DEFAULT_URL=os.environ.get('TOKENLAB_DEFAULT_URL','http://127.0.0.1:8000/v1')
def safe_url(v):
    v=v.strip().rstrip('/');u=urlsplit(v)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise HTTPException(422,'请填写不含凭据或查询参数的 HTTP(S) URL')
    return v
def owner(req):
    key=req.cookies.get('lab_session','')
    if key not in sessions:raise HTTPException(401,'会话已过期，请刷新页面')
    return key
def endpoint(req,eid):
    sid=owner(req)
    if eid not in sessions[sid]['endpoints']:raise HTTPException(404,'当前会话没有该端点')
    return sid,sessions[sid]['endpoints'][eid]
def headers(ep):return {'Authorization':'Bearer '+ep['key']} if ep['key'] else {}
@app.middleware('http')
async def guard(req,call_next):
    origin=req.headers.get('origin')
    if req.method in ('POST','DELETE','PUT') and origin and urlsplit(origin).netloc!=req.headers.get('host'):
        return JSONResponse({'detail':'拒绝跨站写请求'},403)
    resp=await call_next(req);resp.headers['X-Content-Type-Options']='nosniff';return resp
@app.get('/api/session')
async def session(req:Request):
    key=req.cookies.get('lab_session','')
    if key not in sessions:
        if not __import__('re').fullmatch(r'[A-Za-z0-9_-]{43}',key):key=secrets.token_urlsafe(32)
        sessions[key]={'endpoints':{'default':{'id':'default','name':'Qwen · LAN','url':DEFAULT_URL,'key':'','kind':'vllm','models':[],'caps':{}}}}
    resp=JSONResponse({'endpoints':[{k:v for k,v in ep.items() if k!='key'} for ep in sessions[key]['endpoints'].values()]})
    resp.set_cookie('lab_session',key,httponly=True,samesite='strict',secure=req.url.scheme=='https')
    return resp
class EndpointIn(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    url:str
    api_key:str=''
    kind:str='compatible'
@app.post('/api/endpoints')
async def add_endpoint(data:EndpointIn,req:Request):
    sid=owner(req);eid=uuid.uuid4().hex
    ep={'id':eid,'name':data.name,'url':safe_url(data.url),'key':data.api_key,'kind':data.kind,'models':[],'caps':{}}
    sessions[sid]['endpoints'][eid]=ep
    return {k:v for k,v in ep.items() if k!='key'}
@app.delete('/api/endpoints/{eid}')
async def delete_endpoint(eid:str,req:Request):
    sid,_=endpoint(req,eid);del sessions[sid]['endpoints'][eid];return {'ok':True}
@app.get('/api/endpoints/{eid}/models')
async def models(eid:str,req:Request):
    _,ep=endpoint(req,eid)
    try:
        async with httpx.AsyncClient(timeout=20,trust_env=False) as c:
            r=await c.get(ep['url']+'/models',headers=headers(ep));r.raise_for_status();data=r.json().get('data',[])
        ep['models']=[x['id'] for x in data]
        if any(x.get('owned_by')=='vllm' for x in data):ep['kind']='vllm'
        return {'models':ep['models'],'kind':ep['kind'],'caps':ep['caps']}
    except Exception as e:raise HTTPException(502,'模型列表获取失败：'+type(e).__name__)
@app.post('/api/endpoints/{eid}/probe')
async def probe(eid:str,req:Request):
    _,ep=endpoint(req,eid);model=(await req.json()).get('model')
    if not model:raise HTTPException(422,'请先选择模型')
    base={'model':model,'messages':[{'role':'user','content':'Hi'}],'max_tokens':1,'temperature':0}
    if ep['kind']=='vllm':base['chat_template_kwargs']={'enable_thinking':False}
    checks={'logprobs':{'logprobs':True,'top_logprobs':3},'top_k':{'top_k':3},'seed':{'seed':42},'stream_usage':{'stream':True,'stream_options':{'include_usage':True}}}
    async def check(name,extra):
        try:
            async with httpx.AsyncClient(timeout=45,trust_env=False) as c:
                r=await c.post(ep['url']+'/chat/completions',json={**base,**extra},headers=headers(ep))
                if r.status_code!=200:return name,False
                if name=='logprobs':return name,bool(((r.json().get('choices') or [{}])[0].get('logprobs') or {}).get('content'))
                if name=='stream_usage':return name,'"completion_tokens"' in r.text
                return name,ep['kind']=='vllm'
        except Exception:return name,False
    caps=dict(await asyncio.gather(*(check(k,v) for k,v in checks.items())))
    ep['caps'][model]=caps;return {'caps':caps,'model':model}
class GenerateIn(BaseModel):
    endpoint_id:str
    model:str=Field(min_length=1)
    prompt:str=Field(min_length=1,max_length=200000)
    system:str=''
    temperature:float=Field(default=0.7,ge=0,le=2)
    top_p:float=Field(default=0.95,gt=0,le=1)
    top_k:int|None=Field(default=None,ge=1,le=1000)
    max_tokens:int=Field(default=512,ge=1,le=32768)
    presence_penalty:float=Field(default=0,ge=-2,le=2)
    frequency_penalty:float=Field(default=0,ge=-2,le=2)
    logprobs:bool=True
    top_logprobs:int=Field(default=5,ge=1,le=20)
    seed:int|None=None
    stream:bool=True
    run_id:str=Field(default_factory=lambda:uuid.uuid4().hex,pattern=r'^[a-zA-Z0-9-]{1,80}$')
async def sse_objects(lines):
    data=[]
    async for line in lines:
        if line=='':
            if data:
                raw='\n'.join(data);data=[]
                if raw=='[DONE]':yield None;return
                yield json.loads(raw)
        elif line.startswith('data:'):data.append(line[5:].lstrip())
    if data and '\n'.join(data)!='[DONE]':yield json.loads('\n'.join(data))

class Tracker:
    def __init__(self):
        self.started=time.perf_counter();self.ttft=None;self.last=None;self.chunks=0;self.tokens=[];self.text='';self.reasoning='';self.usage=None;self.estimate=None;self.finish=None;self.ended_ms=None;self.points=[]
    def elapsed(self):return self.ended_ms if self.ended_ms is not None else (time.perf_counter()-self.started)*1000
    def consume(self,obj,stream=True):
        ms=self.elapsed()
        if obj.get('usage'):self.usage=obj['usage']
        choices=obj.get('choices') or [];choice=choices[0] if choices else {}
        delta=(choice.get('delta') if stream else choice.get('message')) or {}
        text=delta.get('content') or '';reason=delta.get('reasoning_content') or delta.get('reasoning') or '';interval=None
        if text or reason:
            if stream and self.ttft is None:self.ttft=ms
            if self.last is not None:interval=ms-self.last
            self.last=ms;self.chunks+=1
        self.text+=text;self.reasoning+=reason
        lp=(choice.get('logprobs') or {}).get('content') or [];ids=choice.get('token_ids') or [];batch=[]
        for i,t in enumerate(lp):
            v=t.get('logprob');v=v if isinstance(v,(int,float)) and math.isfinite(v) and v<=0 else None
            candidates=[]
            for top in t.get('top_logprobs') or []:
                logp=top.get('logprob')
                if isinstance(logp,(int,float)) and math.isfinite(logp) and logp<=0:
                    candidates.append({'token':top.get('token',''),'logprob':logp,'probability':math.exp(logp),'bytes':top.get('bytes')})
            tok={'index':len(self.tokens),'text':t.get('token',''),'token_id':t.get('token_id',ids[i] if i<len(ids) else None),'bytes':t.get('bytes'),'logprob':v,'probability':math.exp(v) if v is not None else None,'candidates':candidates,'arrival_ms':ms if stream else None,'observed_at_ms':ms,'timing':'shared_chunk_observation' if stream else 'non_stream_unavailable','chunk':self.chunks}
            self.tokens.append(tok);batch.append(tok)
        if choice.get('finish_reason'):self.finish=choice['finish_reason']
        if text or reason:
            m=self.metrics();self.points.append({'ms':ms,'count':m['completion_tokens'],'tps':m['output_tps'],'interval':interval,'latency':ms})
        return {'text':text,'reasoning':reason,'tokens':batch,'chunk_interval_ms':interval,'metrics':self.metrics(),'has_text_event':bool(text or reason)}
    def metrics(self):
        ms=self.elapsed();n=(self.usage or {}).get('completion_tokens')
        source='server_usage' if n is not None else 'logprobs_observed' if self.tokens else 'tokenizer_estimate' if self.estimate is not None else 'unavailable'
        if n is None:n=len(self.tokens) if self.tokens else self.estimate
        lps=[x['logprob'] for x in self.tokens if x['logprob'] is not None]
        return {'ttft_ms':self.ttft,'ttft_source':'backend_observed' if self.ttft is not None else 'unavailable','total_ms':ms,'completion_tokens':n,'count_source':source,'output_tps':n/(ms/1000) if n is not None and ms>0 else None,'throughput_definition':'completion_tokens / total_request_seconds','chunks':self.chunks,'usage':self.usage,'average_logprob':sum(lps)/len(lps) if lps else None,'average_nll':-sum(lps)/len(lps) if lps else None,'low_probability_ratio':sum(math.exp(x)<0.1 for x in lps)/len(lps) if lps else None,'logprob_coverage':len(lps),'true_itl_ms':None}

@app.post('/api/generate')
async def generate(data:GenerateIn,req:Request):
    sid,ep=endpoint(req,data.endpoint_id)
    if data.run_id in active:raise HTTPException(409,'run_id 已在运行')
    caps=ep['caps'].get(data.model,{})
    if data.top_k is not None and not caps.get('top_k'):raise HTTPException(422,'此模型尚未验证 top-k 支持')
    if data.seed is not None and not caps.get('seed'):raise HTTPException(422,'此模型尚未验证 seed 支持')
    if data.logprobs and not caps.get('logprobs'):raise HTTPException(422,'请先探测 logprobs 能力，或关闭 logprobs')
    with DB() as db:
        if db.get(RunRow,data.run_id):raise HTTPException(409,'run_id 已存在，请生成新 ID')
    q=asyncio.Queue();track=Tracker();status='running';estimator=None
    async def emit(kind,payload):await q.put({'type':kind,**payload})
    async def produce():
        nonlocal status,estimator
        try:
            await emit('start',{'run_id':data.run_id,'model':data.model,'stream':data.stream})
            messages=([{'role':'system','content':data.system}] if data.system else [])+[{'role':'user','content':data.prompt}]
            payload={'model':data.model,'messages':messages,'temperature':data.temperature,'top_p':data.top_p,'max_tokens':data.max_tokens,'presence_penalty':data.presence_penalty,'frequency_penalty':data.frequency_penalty,'stream':data.stream}
            if data.stream and caps.get('stream_usage'):payload['stream_options']={'include_usage':True}
            if data.logprobs:payload.update(logprobs=True,top_logprobs=data.top_logprobs)
            if data.top_k is not None:payload['top_k']=data.top_k
            if data.seed is not None:payload['seed']=data.seed
            if ep['kind']=='vllm':payload['chat_template_kwargs']={'enable_thinking':False}

            async with httpx.AsyncClient(timeout=httpx.Timeout(180,connect=15),trust_env=False) as c:
                if not data.logprobs and data.stream and ep['kind']=='vllm':
                    async def estimate_live():
                        u=urlsplit(ep['url']);base=f'{u.scheme}://{u.netloc}';last=''
                        while True:
                            await asyncio.sleep(0.75)
                            text=track.text
                            if text and text!=last and not track.usage:
                                try:
                                    resp=await c.post(base+'/tokenize',headers=headers(ep),json={'model':data.model,'prompt':text,'add_special_tokens':False})
                                    if resp.status_code!=200:return
                                    track.estimate=resp.json().get('count');last=text
                                    await emit('metrics',{'metrics':track.metrics()})
                                except Exception:return
                    estimator=asyncio.create_task(estimate_live())
                if data.stream:
                    async with c.stream('POST',ep['url']+'/chat/completions',json=payload,headers=headers(ep)) as r:
                        if r.status_code!=200:
                            await r.aread();raise RuntimeError(f'上游 HTTP {r.status_code}；请核对服务参数和额度')
                        done=False
                        async for obj in sse_objects(r.aiter_lines()):
                            if obj is None:done=True;break
                            if obj.get('error'):raise RuntimeError('上游返回生成错误')
                            await emit('delta',track.consume(obj))
                        if not done and not track.finish:raise RuntimeError('上游流意外结束，结果可能不完整')
                else:
                    r=await c.post(ep['url']+'/chat/completions',json=payload,headers=headers(ep))
                    if r.status_code!=200:raise RuntimeError(f'上游 HTTP {r.status_code}')
                    delta=track.consume(r.json(),False);track.ttft=None
                    await emit('delta',delta)
                track.ended_ms=track.elapsed()
                if estimator:
                    estimator.cancel()
                    try:await estimator
                    except asyncio.CancelledError:pass
                if not track.tokens and not track.usage and track.text and ep['kind']=='vllm':
                    try:
                        u=urlsplit(ep['url']);base=f'{u.scheme}://{u.netloc}'
                        r=await c.post(base+'/tokenize',headers=headers(ep),json={'model':data.model,'prompt':track.text,'add_special_tokens':False})
                        if r.status_code==200:track.estimate=r.json().get('count')
                    except Exception:pass
            status='completed'
        except asyncio.CancelledError:status='cancelled'
        except Exception as exc:
            status='error';await emit('error',{'message':str(exc) if isinstance(exc,RuntimeError) else '上游连接或解析失败：'+type(exc).__name__})
        finally:
            if estimator and not estimator.done():estimator.cancel()
            if track.ended_ms is None:track.ended_ms=track.elapsed()
            report={'id':data.run_id,'created':datetime.now(timezone.utc).isoformat(),'endpoint':{'name':ep['name'],'url':ep['url']},'model':data.model,'prompt':data.prompt,'system':data.system,'settings':data.model_dump(exclude={'prompt','system'}),'text':track.text,'reasoning':track.reasoning,'tokens':track.tokens,'points':track.points,'metrics':track.metrics(),'status':status,'finish_reason':track.finish}
            with DB() as db:
                db.merge(RunRow(id=data.run_id,owner=sid,created=report['created'],payload=json.dumps(report,ensure_ascii=False,allow_nan=False)));db.commit()
            await emit('done',{'report':report});active.pop(data.run_id,None)
    task=asyncio.create_task(produce());active[data.run_id]=(sid,task)
    async def events():
        try:
            while True:
                try:event=await asyncio.wait_for(q.get(),timeout=10)
                except asyncio.TimeoutError:
                    if await req.is_disconnected():break
                    yield ': heartbeat\n\n';continue
                yield 'data: '+json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n\n'
                if event['type']=='done':break
        finally:
            if not task.done():task.cancel()
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
@app.post('/api/runs/{rid}/cancel')
async def cancel(rid:str,req:Request):
    sid=owner(req)
    if rid in active and active[rid][0]==sid:active[rid][1].cancel()
    return {'ok':True}
@app.get('/api/history')
async def history(req:Request):
    sid=owner(req)
    with DB() as db:
        rows=db.query(RunRow).filter_by(owner=sid).order_by(RunRow.created.desc()).limit(100).all()
        return [json.loads(x.payload) for x in rows]
@app.get('/api/health')
async def health():return {'ok':True,'active_runs':len(active),'python':__import__('sys').version.split()[0]}
if (ROOT/'dist/assets').exists():app.mount('/assets',StaticFiles(directory=ROOT/'dist/assets'),name='assets')
@app.get('/')
async def index():
    if not (ROOT/'dist/index.html').exists():raise HTTPException(503,'请先构建前端')
    return FileResponse(ROOT/'dist/index.html',headers={'Cache-Control':'no-cache'})
