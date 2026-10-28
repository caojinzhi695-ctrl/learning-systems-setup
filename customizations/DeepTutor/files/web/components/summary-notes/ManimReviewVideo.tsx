"use client";

import { useEffect, useRef, useState } from "react";
import { X, Film, Download, Sparkles } from "lucide-react";
import { apiFetch, apiUrl } from "@/lib/api";

type Note = { id: string; title?: string; notes: string; status: string };
type Scene = { title: string; layout: string; duration: number; caption: string; source_quote: string; caution: string };
type Plan = { title: string; summary: string; scenes: Scene[] };
type ReviewBrief = { title: string; core_question: string; summary: string; omitted: string; points: { heading: string; takeaway: string; keyphrase: string; screen_text: string; condition: string; source_quote: string }[] };
type Job = { review_brief?: ReviewBrief; id: string; status: string; plan: Plan | null; error: string; model?: string; created_at: number; video: boolean; progress: number };
type Props = { open: boolean; onClose: () => void; notes: Note[]; sessionId?: string; initialNoteId?: string };
const active = (status?: string) => ["queued", "summarizing", "planning", "rendering"].includes(status || "");
const statusName = (status: string) => ({ queued: "排队中", summarizing: "第 1 步：整理重点与复习稿", planning: "第 2 步：根据复习稿设计分镜", rendering: "Manim 渲染中", complete: "已完成", cancelled: "已取消", failed: "未完成", interrupted: "已中断" }[status] || status);
async function request(path: string, init?: RequestInit) {
  const response = await apiFetch(apiUrl(`/api/summary-notes${path}`), init);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "请求失败，请检查本地服务。");
  return result;
}

export default function ManimReviewVideo({ open, onClose, notes, sessionId, initialNoteId }: Props) {
  const available = notes.filter(n => n.status === "complete" && n.notes);
  const [selected, setSelected] = useState("");
  const [instructions, setInstructions] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const panel = useRef<HTMLElement>(null), alive = useRef(true);
  const pollController = useRef<AbortController | null>(null);
  const busy = sending || active(job?.status);
  const base = `/${sessionId}/turns/${selected}/video-plans`;
  const plan = job?.plan;
  const duration = plan?.scenes.reduce((sum, scene) => sum + scene.duration, 0) || 0;
  const button = "rounded-lg border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-40 hover:bg-[var(--muted)]";
  useEffect(() => { alive.current = true; return () => { alive.current = false; pollController.current?.abort(); }; }, []);
  useEffect(() => {
    if (open && !available.some(n => n.id === selected)) { setSelected(available.find(n => n.id === initialNoteId)?.id || available.at(-1)?.id || ""); setJob(null); }
  }, [open, notes, selected]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (open && initialNoteId && available.some(n => n.id === initialNoteId)) {
      pollController.current?.abort();
      setSelected(initialNoteId); setJob(null);
    }
  }, [open, sessionId, initialNoteId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null; panel.current?.focus();
    return () => previous?.focus();
  }, [open]);
  useEffect(() => {
    if (!open || !sessionId || !selected) return;
    pollController.current?.abort();
    const controller = new AbortController(); setLoading(true); setError("");
    request(base, { signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setHistory(data.jobs); setJob(data.jobs[0] || null);
      if (active(data.jobs[0]?.status)) void monitor(data.jobs[0].id);
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  // Reload only when the selected notebook changes or the panel opens.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sessionId, selected]);

  async function monitor(id: string) {
    pollController.current?.abort();
    const controller = new AbortController(); pollController.current = controller;
    try {
      while (!controller.signal.aborted && alive.current) {
        const value: Job = await request(`${base}/${id}`, { signal: controller.signal });
        if (controller.signal.aborted || !alive.current) return;
        setJob(value);
        if (!active(value.status)) {
          setHistory(old => [value, ...old.filter(j => j.id !== value.id)]);
          if (value.error) setError(value.error);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
    } catch (e) { if (!controller.signal.aborted && alive.current) setError(e instanceof Error ? e.message : "状态读取失败。任务仍保留，可重新打开此面板查看。"); }
  }

  async function create() {
    if (!selected || !sessionId || busy) return;
    setSending(true); setError("");
    const id = crypto.randomUUID().replaceAll("-", "");
    try {
      const value = await request(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: id, instructions, confirm_api_cost: true }) });
      if (alive.current) { setJob(value); setSending(false); void monitor(id); }
    } catch (e) {
      if (!alive.current) return;
      // Check an uncertain POST read-only; never resend a paid model request.
      try { const value = await request(`${base}/${id}`); setJob(value); void monitor(id); }
      catch { setError(e instanceof Error ? e.message : "请求未确认，请重新打开历史任务检查。不会自动重复调用模型。"); }
    } finally { if (alive.current) setSending(false); }
  }

  async function rerender() {
    if (!job || busy) return;
    setSending(true); setError("");
    try { const value = await request(`${base}/${job.id}/render`, { method: "POST" }); setJob(value); void monitor(job.id); }
    catch (e) { setError(e instanceof Error ? e.message : "重新渲染失败。"); }
    finally { setSending(false); }
  }

  async function continueFromBrief() {
    if (!job || busy) return;
    setSending(true); setError("");
    try { const value = await request(`${base}/${job.id}/continue`, { method: "POST" }); setJob(value); void monitor(job.id); }
    catch (e) { setError(e instanceof Error ? e.message : "继续制作失败。"); }
    finally { setSending(false); }
  }

  async function cancel() {
    if (!job) return;
    try { const value = await request(`${base}/${job.id}`, { method: "DELETE" }); pollController.current?.abort(); setJob(value); setError(value.error || "已取消生成。"); }
    catch (e) { setError(e instanceof Error ? e.message : "取消未确认，请查看任务状态。"); }
  }
  if (!open) return null;
  return <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    <section ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Manim 复习视频" className="flex h-full w-full max-w-4xl flex-col overflow-auto bg-[var(--background)] shadow-xl" onKeyDown={e => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const controls = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],summary,video[controls]');
        const first = controls?.[0], last = controls?.[controls.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }}>
      <header className="flex items-center gap-2 border-b border-[var(--border)] p-5"><Film size={20} /><h2 className="font-semibold">DeepSeek × Manim 复习视频</h2><button aria-label="关闭复习视频" onClick={onClose} className="ml-auto rounded p-2"><X size={20} /></button></header>
      <div className="space-y-4 p-5">
        <p className="text-sm text-[var(--muted-foreground)]">沿用「新手选品 · 50秒快复习」原片模板：微软雅黑、浅色卡片与原版动画节奏。先由 DeepSeek 分析 AI 笔记、提炼重点形成复习稿，再依据复习稿安排画面、页数与阅读时长，Manim 渲染 1080p，配原片音乐，无旁白。</p>
        <label className="block text-sm">选择已完成的 AI 笔记<select aria-label="选择视频笔记" disabled={busy} value={selected} onChange={e => { setSelected(e.target.value); setJob(null); }} className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] p-2"><option value="">请先生成 AI 笔记</option>{available.map((note, i) => <option key={note.id} value={note.id}>{note.title || `笔记 ${i + 1}`}</option>)}</select></label>
        <p className="rounded-lg border border-[var(--border)] p-3 text-sm">原片风格 · 内容卡片自动排版 · DeepSeek 自动判断时长与页数。</p>
        <label className="block text-sm">制作要求（可选）<textarea aria-label="视频制作要求" maxLength={1200} disabled={busy} value={instructions} onChange={e => setInstructions(e.target.value)} placeholder="例如：重点复习调研、ACOS 与广告四象限；节奏快，多图解，少堆文字。" className="mt-2 h-20 w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--background)] p-3" /></label>
        <button disabled={!selected || busy || loading} onClick={() => void create()} className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm text-white disabled:opacity-40"><Sparkles size={18} />DeepSeek 自动设计并生成 Manim 视频</button>
        <p className="text-xs text-[var(--muted-foreground)]">点击将调用已配置的 DeepSeek，产生 API 用量；先整理复习稿，再制作分镜（通常两次请求）；分镜格式修正最多一次，总计最多三次请求。全部 AI 步骤使用您配置的 DeepSeek；Manim/FFmpeg 在本机后台渲染 MP4。关闭面板仍会继续，复习稿、分镜与成片会保存。</p>
        {loading && <p role="status" className="text-sm">正在读取已保存的视频…</p>}
        {busy && <div className="space-y-2 rounded-xl border border-[var(--border)] p-3"><p role="status" className="text-sm">{sending ? "正在提交任务…" : `${statusName(job?.status || "queued")}${job?.status === "rendering" ? ` · ${job.progress || 0}%` : "…"}`}</p>{job?.status === "rendering" && <progress aria-label="Manim渲染进度" max={100} value={job.progress || 0} className="w-full" />}<button disabled={sending} className={button} onClick={() => void cancel()}>取消生成</button></div>}
        {job?.review_brief && <details className="rounded-lg border border-[var(--border)] p-3 text-sm"><summary className="cursor-pointer">查看第 1 步：整理后的复习稿</summary><div className="mt-3 space-y-3"><p className="font-semibold">{job.review_brief.core_question}</p><p>{job.review_brief.summary}</p><ol className="space-y-3">{job.review_brief.points.map((point, i) => <li key={i}><strong>{i + 1}. {point.heading}</strong><p>{point.takeaway}</p><p className="text-indigo-600">画面短句：{point.keyphrase} · {point.screen_text}</p>{point.condition && <p className="text-amber-700">{point.condition}</p>}<blockquote className="border-l-2 pl-2 text-xs text-[var(--muted-foreground)]">原文依据：{point.source_quote}</blockquote></li>)}</ol>{job.review_brief.omitted && <p className="text-xs text-[var(--muted-foreground)]">本轮省略：{job.review_brief.omitted}</p>}</div></details>}
        {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {job?.review_brief && !plan && !busy && <button className={button} onClick={() => void continueFromBrief()}>继续制作分镜（复用复习稿，调用 AI）</button>}
        {history.length > 0 && <label className="block text-sm">历史视频<select aria-label="历史Manim视频" value={job?.id || ""} disabled={busy} onChange={e => { setJob(history.find(j => j.id === e.target.value) || null); setError(""); }} className="ml-2 max-w-full rounded-lg border border-[var(--border)] bg-[var(--background)] p-2">{!history.some(h => h.id === job?.id) && <option value={job?.id || ""}>当前任务</option>}{history.map(h => <option key={h.id} value={h.id}>{new Date(h.created_at * 1000).toLocaleString()} · {statusName(h.status)} · {h.plan?.title || "Manim 视频"}</option>)}</select></label>}
        {plan && <>
          <div><h3 className="font-semibold">{plan.title}</h3><p className="mt-1 text-sm text-[var(--muted-foreground)]">{plan.summary}</p><p className="mt-1 text-xs text-indigo-600">{job?.model} · Manim · {plan.scenes.length} 个分镜 · {duration} 秒 · 1920 × 1080</p></div>
          {job?.status === "complete" && job.video && <div className="space-y-3"><video key={job.id} aria-label="生成的Manim复习视频" src={apiUrl(`/api/summary-notes${base}/${job.id}/file?inline=true`)} controls playsInline preload="metadata" className="w-full rounded-xl" /><a href={apiUrl(`/api/summary-notes${base}/${job.id}/file`)} className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] px-4 py-2 text-sm"><Download size={16} />下载 MP4 视频</a></div>}
          <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={() => void rerender()}>重新渲染（不调用 AI）</button><a href={apiUrl(`/api/summary-notes${base}/${job!.id}/source`)} className={button}>下载 Manim 源码与分镜</a></div>
          <details className="rounded-lg border border-[var(--border)] p-3 text-sm"><summary className="cursor-pointer">查看 DeepSeek 分镜与笔记依据</summary><ol className="mt-3 space-y-3">{plan.scenes.map((scene, i) => <li key={i} className="border-t border-[var(--border)] pt-2"><strong>{i + 1}. {scene.title}</strong><span className="ml-2 text-xs text-[var(--muted-foreground)]">{scene.duration} 秒</span><p>{scene.caption}</p>{scene.caution && <p className="text-amber-700">{scene.caution}</p>}<blockquote className="mt-1 border-l-2 pl-3 text-xs text-[var(--muted-foreground)]">笔记依据：{scene.source_quote}</blockquote></li>)}</ol></details>
        </>}
      </div>
    </section>
  </div>;
}
