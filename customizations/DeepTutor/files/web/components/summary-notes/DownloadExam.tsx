"use client";
import {useEffect,useRef,useState} from "react";
import {LoaderCircle} from "lucide-react";
import {apiFetch,apiUrl} from "@/lib/api";

export default function DownloadExam({sessionId,turnId}:{sessionId:string;turnId:string}){
 const [busy,setBusy]=useState(false),[seconds,setSeconds]=useState(0),[error,setError]=useState('');
 const active=useRef(false),controller=useRef<AbortController|null>(null);
 useEffect(()=>()=>{controller.current?.abort();},[]);
 useEffect(()=>{if(!busy)return;const started=Date.now();const timer=setInterval(()=>setSeconds(Math.floor((Date.now()-started)/1000)),1000);return()=>clearInterval(timer);},[busy]);
 async function download(){
  if(active.current)return;active.current=true;setBusy(true);setSeconds(0);setError('');
  const abort=new AbortController();controller.current=abort;
  const base=`/api/summary-notes/${sessionId}/turns/${turnId}/exams`;
  const notify=()=>window.dispatchEvent(new CustomEvent('summary-exams-updated',{detail:{sessionId,turnId}}));
  async function request(path:string,init?:RequestInit){const r=await apiFetch(apiUrl(path),{...init,signal:abort.signal});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'练习题请求失败，请稍后重试。');return data;}
  try{
   const existing=await request(base);
   let id=existing.exams.find((e:{status:string})=>e.status==='generating')?.id;
   if(!id){const data=await request(base,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:crypto.randomUUID().replaceAll('-','')})});id=data.id;}
   notify();
   const deadline=Date.now()+12*60*1000;
   while(!abort.signal.aborted){
    const data=await request(base);const exam=data.exams.find((e:{id:string})=>e.id===id);
    if(!exam)throw Error('找不到生成任务，请在复习练习卷中检查。');
    if(exam.status==='failed')throw Error(exam.error||'生成未完成，请检查模型设置后重试。');
    if(exam.status==='complete')break;
    if(Date.now()>deadline)throw Error('等待时间较长，请稍后在复习练习卷中查看结果。');
    await new Promise<void>((resolve,reject)=>{const onAbort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};const timer=setTimeout(()=>{abort.signal.removeEventListener('abort',onAbort);resolve();},2000);abort.signal.addEventListener('abort',onAbort,{once:true});});
   }
   const response=await apiFetch(apiUrl(`${base}/${id}/word`),{signal:abort.signal});
   if(!response.ok)throw Error('Word 下载失败，可在复习练习卷中重新下载已有试卷。');
   const blob=await response.blob();const disposition=response.headers.get('Content-Disposition')||'';
   const name=disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
   let filename='复习练习卷.docx';try{if(name)filename=decodeURIComponent(name);}catch{}
   const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);notify();
  }catch(e){if(!abort.signal.aborted)setError((e as Error).message);notify();}
  finally{active.current=false;if(!abort.signal.aborted)setBusy(false);}
 }
 return <div className="min-w-0"><button type="button" disabled={busy} onClick={()=>void download()} className="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-center text-xs font-medium text-[var(--foreground)] hover:bg-[var(--accent)] disabled:cursor-wait disabled:opacity-70" aria-busy={busy}>{busy&&<LoaderCircle size={15} className="shrink-0 animate-spin" aria-hidden="true"/>}<span role="status">{busy?`AI 出题中 · ${seconds}秒`:'下载练习题'}</span></button>{error&&<p role="alert" className="mt-2 break-words text-xs text-red-600">{error}</p>}</div>;
}
