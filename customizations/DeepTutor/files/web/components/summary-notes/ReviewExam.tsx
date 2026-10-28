"use client";
import {useCallback,useEffect,useState} from "react";
import {apiFetch,apiUrl} from "@/lib/api";

type Question={id:number;type:string;prompt:string;options:{key:string;text:string}[];correctOptions:string[];answer:string;explanation:string;knowledgePoint:string;verdict?:boolean;correction?:string};
type Paper={title:string;scope:string;questions:Question[];recap:string[]};
type Exam={id:string;status:string;created_at:number;error:string;paper:Paper|null};
const types:Record<string,string>={recall:'简答题',fill:'填空题',single:'单选题',multiple:'多选题',correction:'判断并改错',explain:'对比与解释',application:'情境应用'};
const button="rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-xs font-medium disabled:opacity-50";
export default function ReviewExam({sessionId,turnId}:{sessionId:string;turnId:string}){
 const [open,setOpen]=useState(false),[exams,setExams]=useState<Exam[]>([]),[selected,setSelected]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const base=`/api/summary-notes/${sessionId}/turns/${turnId}/exams`;
 const request=useCallback(async(path:string,init?:RequestInit)=>{const response=await apiFetch(apiUrl(path),init);const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'试卷请求失败，请稍后重试。');return data;},[]);
 const load=useCallback(async()=>{const data=await request(base);setExams(data.exams);},[request,base]);
 useEffect(()=>{if(open)void load().catch(e=>setError(e.message));},[open,load]);
 useEffect(()=>{const refresh=(event:Event)=>{const d=(event as CustomEvent).detail;if(d?.sessionId===sessionId&&d?.turnId===turnId)void load().catch(e=>setError(e.message));};window.addEventListener('summary-exams-updated',refresh);return()=>window.removeEventListener('summary-exams-updated',refresh);},[load,sessionId,turnId]);
 const pending=exams.some(e=>e.status==='generating');
 useEffect(()=>{if(!pending)return;const timer=setInterval(()=>void load().catch(e=>setError(e.message)),2500);return()=>clearInterval(timer);},[pending,load]);
 const current=exams.find(e=>e.id===selected)||exams[0],paper=current?.paper;
 async function generate(){setBusy(true);setError('');try{const data=await request(base,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:crypto.randomUUID().replaceAll('-','')})});setSelected(data.id);await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <details className="rounded-lg border border-[var(--border)]" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary className="cursor-pointer px-3 py-3 text-sm font-medium">复习练习卷 · 点击{open?'收起':'展开'}</summary>
  {open&&<div className="space-y-4 border-t border-[var(--border)] p-3 text-sm">
   <p className="text-xs leading-6 text-[var(--muted-foreground)]">基于这份 AI 笔记，按内容量和知识点自动出题，最多22题。题目与答案分开呈现。</p>
   <div className="flex flex-wrap items-center gap-2"><span className="text-xs">出题材料：当前 AI 笔记</span><button className={button} disabled={busy||pending} onClick={()=>void generate()}>{busy||pending?'试卷生成中…':exams.length?'重新生成试卷':'生成复习试卷'}</button></div>
   {error&&<p role="alert" className="text-xs text-red-600">{error}</p>}
   {pending&&<p role="status" className="text-xs">正在生成，收起后仍会继续。</p>}
   {exams.length>0&&<label className="block text-xs">试卷版本<select aria-label="试卷版本" className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] p-2" value={current?.id||''} onChange={e=>setSelected(e.target.value)}>{exams.map(e=><option key={e.id} value={e.id}>{new Date(e.created_at*1000).toLocaleString('zh-CN')} · {e.status==='complete'?'已完成':e.status==='generating'?'生成中':'未完成'}</option>)}</select></label>}
   {current?.error&&<p role="status" className="text-xs text-orange-700">{current.error}</p>}
   {paper&&<><div className="flex flex-wrap gap-2"><a className={`${button} inline-block`} href={apiUrl(`${base}/${current.id}/word`)}>下载 Word 文档</a><a className={`${button} inline-block`} href={apiUrl(`${base}/${current.id}/html`)}>下载 HTML 练习卷</a></div>
    <article aria-label="复习练习卷" className="space-y-5 leading-7">
     <header><h3 className="text-base font-bold">{paper.title} 复习练习卷</h3><p className="text-xs text-[var(--muted-foreground)]">题量：{paper.questions.length} · {paper.scope}</p></header>
     <section className="space-y-4"><h4 className="font-bold">第一部分｜题目</h4>{paper.questions.map(q=><div key={q.id} className="space-y-2 border-b border-[var(--border)] pb-4"><p><strong>{q.id}. 【{types[q.type]}】</strong>{q.prompt}</p>{q.options.map(o=><p key={o.key} className="pl-3">{o.key}. {o.text}</p>)}</div>)}</section>
     <details className="rounded-lg border border-[var(--border)] p-3"><summary className="cursor-pointer font-bold">第二部分｜参考答案与解析（点击展开）</summary><div className="mt-4 space-y-5">{paper.questions.map(q=><section key={q.id} className="space-y-1"><h5 className="font-bold">第{q.id}题</h5>{q.correctOptions.length>0&&<p>正确选项：{q.correctOptions.join('、')}</p>}{typeof q.verdict==='boolean'&&<p>判断：{q.verdict?'正确':'错误'}</p>}<p className="whitespace-pre-wrap"><strong>参考答案：</strong>{q.answer}</p>{q.correction&&<p>正确表述：{q.correction}</p>}<p><strong>解析：</strong>{q.explanation}</p><p><strong>知识点：</strong>{q.knowledgePoint}</p></section>)}</div></details>
     <section><h4 className="font-bold">第三部分｜复习速记</h4><ul className="list-disc space-y-2 pl-5">{paper.recap.map((line,i)=><li key={i}>{line}</li>)}</ul></section>
    </article>
   </>}
  </div>}
 </details>;
}
