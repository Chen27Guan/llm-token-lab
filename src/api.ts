export async function api(path:string,body?:unknown,method?:string){
 const r=await fetch('/api'+path,{method:method??(body?'POST':'GET'),headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
 if(!r.ok){let message=r.statusText;try{const v=await r.json();message=typeof v.detail==='string'?v.detail:JSON.stringify(v.detail)}catch{}throw new Error(message)}return r.json();
}
export async function streamRun(body:unknown,emit:(e:any)=>void){
 let buffered:any=null;let timer:ReturnType<typeof setTimeout>|undefined;
 const flush=()=>{if(timer)clearTimeout(timer);timer=undefined;if(buffered){emit(buffered);buffered=null}};
 const onEvent=(e:any)=>{if(e.type!=='delta'){flush();emit(e);return}if(buffered){buffered={...e,text:buffered.text+e.text,reasoning:buffered.reasoning+e.reasoning,tokens:[...buffered.tokens,...e.tokens],has_text_event:buffered.has_text_event||e.has_text_event,chunk_interval_ms:e.chunk_interval_ms??buffered.chunk_interval_ms}}else buffered=e;if(!timer)timer=setTimeout(flush,50)};
 const r=await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok){const j=await r.json();throw new Error(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail))}
 if(!r.body)throw new Error('浏览器不支持 ReadableStream');
 const reader=r.body.getReader(),decoder=new TextDecoder();let pending='',completed=false;
 const consume=(frame:string)=>{const data=frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(data){const event=JSON.parse(data);if(event.type==='done')completed=true;onEvent(event)}};
 try{while(true){const {value,done}=await reader.read();pending+=decoder.decode(value,{stream:!done}).replace(/\r\n/g,'\n');let idx;while((idx=pending.indexOf('\n\n'))>=0){consume(pending.slice(0,idx));pending=pending.slice(idx+2)}if(done)break}if(pending.trim())consume(pending);if(!completed)throw new Error('连接中断，缺少完成事件')}finally{flush();reader.releaseLock()}
}
export function download(value:unknown,name:string){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
