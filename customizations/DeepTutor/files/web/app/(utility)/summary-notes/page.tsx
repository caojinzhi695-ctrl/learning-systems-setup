"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Plus, Paperclip, NotebookPen, PanelRight, X, LoaderCircle } from "lucide-react";
import Image from "next/image";
import dynamic from "next/dynamic";
import ReviewExam from "@/components/summary-notes/ReviewExam";
import DownloadExam from "@/components/summary-notes/DownloadExam";
const NoteMindmap = dynamic(() => import("@/components/summary-notes/NoteMindmap"), { ssr: false });
import { useTranslation } from "react-i18next";
import MarkdownRenderer from "@/components/common/MarkdownRenderer";
import { apiFetch, apiUrl } from "@/lib/api";

type Turn = { id: string; message: string; notes: string; html: string; status: string; error: string; title?: string };
type Session = { id: string; title: string; turns: Turn[] };
type Entry = { id: string; title: string };

async function request(path: string, init?: RequestInit) {
  const response = await apiFetch(apiUrl(`/api/summary-notes${path}`), init);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "请求失败，请检查服务状态。");
  return result;
}

export default function SummaryNotesPage() {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<Entry[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [message, setMessage] = useState("");
  const [collectionOpen, setCollectionOpen] = useState(false);
  const [collectionWidth, setCollectionWidth] = useState(380);
  const [resizingCollection, setResizingCollection] = useState(false);
  const collectionRef = useRef<HTMLElement>(null);
  const clampCollectionWidth = (width: number) => {
    const parentWidth = collectionRef.current?.parentElement?.getBoundingClientRect().width || window.innerWidth;
    const maximum = window.innerWidth >= 1024 ? parentWidth - 240 : parentWidth * 0.92;
    return Math.max(Math.min(300, maximum), Math.min(width, maximum));
  };
  useEffect(() => {
    try { const width = Number(localStorage.getItem('summary-collection-width')); if (width >= 300 && Number.isFinite(width)) setCollectionWidth(width); } catch {}
  }, []);
  const saveCollectionWidth = (width: number) => {
    const next = clampCollectionWidth(width);
    setCollectionWidth(next);
    try { localStorage.setItem('summary-collection-width', String(next)); } catch {}
  };
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [importStatus, setImportStatus] = useState("");
  const [deleting, setDeleting] = useState("");
  const dragDepth = useRef(0);
  const [copiedId, setCopiedId] = useState("");
  const activeRequest = useRef(false);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const selection = useRef(0);

  const select = useCallback(async (id: string) => {
    const version = ++selection.current;
    setLoading(true); setError("");
    try {
      const data = await request(`/${id}`) as Session;
      if (version !== selection.current) return;
      setSession(data); localStorage.setItem("summary-notes-session", id);
    } catch (e) { if (version === selection.current) setError(e instanceof Error ? e.message : "读取失败。"); }
    finally { if (version === selection.current) setLoading(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void request("").then(async data => {
      if (cancelled) return;
      setSessions(data.sessions);
      setCollectionOpen(window.matchMedia("(min-width: 1024px)").matches);
      const saved = localStorage.getItem("summary-notes-session");
      const id = data.sessions.find((item: Entry) => item.id === saved)?.id ?? data.sessions[0]?.id;
      if (id) await select(id);
      else setLoading(false);
    }).catch(e => { if (!cancelled) { setError(e.message); setLoading(false); } });
    // This ref is a request counter, not a DOM node; invalidate pending reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => { cancelled = true; selection.current++; };
  }, [select]);

  async function copyNotes(turn: Turn) {
    try {
      await navigator.clipboard.writeText(turn.notes);
      setCopiedId(turn.id);
      setTimeout(() => setCopiedId(id => id === turn.id ? "" : id), 2500);
    } catch {
      setError("复制失败，请允许剪贴板权限，或展开文字笔记后手动复制。");
    }
  }

  async function create() {
    if (activeRequest.current) return;
    setError(""); setLoading(true);
    try {
      const data = await request("", { method: "POST" }) as Session;
      setSessions(items => [{ id: data.id, title: data.title }, ...items]);
      setSession(data); setMessage("");
      localStorage.setItem("summary-notes-session", data.id);
    } catch (e) { setError(e instanceof Error ? e.message : "创建失败。"); }
    finally { setLoading(false); }
  }

  async function generate() {
    if (activeRequest.current || !message.trim() || !session) return;
    activeRequest.current = true; setBusy(true); setError("");
    try {
      const data = await request(`/${session.id}/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, confirm_api_cost: true, request_id: crypto.randomUUID().replaceAll("-", "") }),
      }) as Session;
      setSession(data);
      setCollectionOpen(true);
      setSessions(items => items.map(item => item.id === data.id ? { id: data.id, title: data.title } : item));
      setMessage("");
    } catch (e) {
      setError((e instanceof Error ? e.message : "请求中断。") + " 材料仍在输入框中。请先重新打开本聊天查看是否已有结果，避免重复提交。");
    } finally { activeRequest.current = false; setBusy(false); }
  }

  async function deleteNote(turn: Turn) {
    if (!session || activeRequest.current || !window.confirm("确定删除这条笔记及其材料、网页和草稿吗？删除后无法恢复。")) return;
    activeRequest.current = true; setDeleting(turn.id); setError("");
    try {
      const data = await request(`/${session.id}/turns/${turn.id}`, { method: "DELETE" }) as Session;
      setSession(data);
      setSessions(items => items.map(item => item.id === data.id ? { id: data.id, title: data.title } : item));
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败，请稍后重试。"); }
    finally { activeRequest.current = false; setDeleting(""); }
  }

  async function importFiles(files: File[]) {
    if (!files.length || activeRequest.current) return;
    activeRequest.current = true; setImporting(true); setError(""); setImportStatus("");
    try {
      if (files.some(file => file.size > 50 * 1024 * 1024)) throw new Error("单个文件不能超过50MB。");
      let combined = message;
      for (const [index, file] of files.entries()) {
        const isMedia = /\.(mp3|wav|m4a|aac|flac|ogg|mp4|webm)$/i.test(file.name);
        setImportStatus(`${isMedia ? "正在转录文字" : "正在提取并识别文字"}（${index + 1}/${files.length}）：${file.name}`);
        const body = new FormData(); body.set("file", file);
        const data = await request("/import", { method: "POST", body });
        combined += `${combined.trim() ? "\n\n" : ""}【文件：${file.name}】\n${data.text}`;
        if (combined.length > 40000) throw new Error("合并材料超过4万字，请拆分导入。原有输入保留，本次文件没有填入或发送模型。");
      }
      setMessage(combined); setImportStatus("");
      messageInput.current?.focus();
    } catch (e) { setError(e instanceof Error ? e.message : "文件提取失败。"); setImportStatus(""); }
    finally { activeRequest.current = false; setImporting(false); }
  }

  return <div className="flex h-full min-h-0 flex-col bg-[var(--background)]">
    <header className="flex shrink-0 items-center gap-3 border-b border-[var(--border)] px-4 py-3 sm:px-6">
      <h1 className="shrink-0 font-serif text-base font-semibold">{t("总结笔记")}</h1>
      <select aria-label={t("选择笔记聊天")} disabled={busy || importing || loading} value={session?.id ?? ""} onChange={e => { setMessage(""); void select(e.target.value); }} className="ml-auto min-w-0 max-w-[50%] truncate rounded-lg border-0 bg-transparent px-2 py-2 text-sm text-[var(--muted-foreground)] focus-visible:outline-2">
        {!session && <option value="">{t("选择聊天")}</option>}
        {sessions.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      <button type="button" aria-label={t("新建笔记聊天")} title={t("新建笔记聊天")} disabled={busy || importing || loading} onClick={() => void create()} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-[var(--muted-foreground)] hover:bg-[var(--muted)] focus-visible:outline-2 disabled:opacity-50"><Plus size={20} /></button>
      <button type="button" aria-label={t("收集栏")} title={t("收集栏")} aria-expanded={collectionOpen} aria-controls="note-collection" onClick={() => setCollectionOpen(open => !open)} className="flex h-10 shrink-0 items-center gap-1.5 rounded-lg px-2 text-sm text-[var(--muted-foreground)] hover:bg-[var(--muted)] focus-visible:outline-2"><PanelRight size={18} /><span className="hidden sm:inline">{t("收集栏")}</span><span className="text-xs">{session?.turns.length || 0}</span></button>
    </header>
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
    <div className="flex min-w-0 flex-1 flex-col">
    <main className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center gap-8 px-5 py-10 sm:px-8 sm:pb-[12vh]">
        <div className="flex items-center justify-center gap-3 sm:gap-4">
          <Image src="/logo_black.png" alt="" width={44} height={44} className="h-9 w-9 shrink-0 select-none sm:h-11 sm:w-11" />
          <h2 className="font-serif text-[clamp(26px,3vw,40px)] font-medium leading-tight tracking-tight">{t("今天想整理什么笔记？")}</h2>
        </div>
        {loading && <p role="status" className="text-center text-sm text-[var(--muted-foreground)]">{t("正在读取笔记聊天…")}</p>}
        {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {!loading && !session && <button type="button" onClick={() => void create()} className="mx-auto rounded-full border border-[var(--border)] px-5 py-2.5 text-sm hover:bg-[var(--muted)]">{t("新建笔记聊天")}</button>}
        {!loading && session && <>
      <form className="w-full" onSubmit={e => { e.preventDefault(); void generate(); }}>
        <div onDragEnter={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); dragDepth.current++; setDragging(true); } }} onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.dataTransfer.dropEffect = busy || importing ? "none" : "copy"; } }} onDragLeave={e => { e.preventDefault(); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); }} onDrop={e => { e.preventDefault(); dragDepth.current = 0; setDragging(false); if (!busy && !importing) void importFiles(Array.from(e.dataTransfer.files)); }} className={`rounded-[28px] border bg-[var(--card)] px-4 pb-3 pt-4 shadow-sm focus-within:border-[var(--primary)]/40 ${dragging ? "border-[var(--primary)] ring-2 ring-[var(--primary)]/30" : "border-[var(--border)]"}`}>
          {dragging && <p role="status" className="mb-2 text-xs text-[var(--muted-foreground)]">松开鼠标导入文件</p>}
          {(importing || busy) && <div className="mb-3 space-y-2" aria-busy="true">
            <style>{`@keyframes summary-note-spin { to { transform: rotate(360deg); } } .summary-note-spinner { animation: summary-note-spin 1s linear infinite !important; }`}</style>
            <div className="flex items-start gap-2"><LoaderCircle aria-hidden="true" size={18} className="summary-note-spinner mt-0.5 shrink-0 text-[var(--primary)]" /><p role="status" className="break-words text-xs text-[var(--muted-foreground)]">{importing ? importStatus || "正在读取文件…" : "正在生成文字笔记和 HTML 网页，请稍候…"}</p></div>
            <progress aria-label={importing ? "文字提取与转录进度，处理中" : "笔记生成进度，处理中"} className="block h-1.5 w-full accent-[var(--primary)]" />
          </div>}
          <label className="sr-only" htmlFor="summary-note-message">{t("粘贴材料或继续提问")}</label>
          <textarea ref={messageInput} id="summary-note-message" rows={2} maxLength={40000} required disabled={busy || importing} value={message} onChange={e => setMessage(e.target.value)} placeholder={t("今天想整理什么笔记？粘贴材料即可开始…")} className="block max-h-40 min-h-24 w-full resize-none border-0 bg-transparent text-sm leading-7 outline-none" onInput={e => { e.currentTarget.style.height = "auto"; e.currentTarget.style.height = `${Math.min(e.currentTarget.scrollHeight, 160)}px`; }} />
          <div className="mt-2 flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-sm text-[var(--muted-foreground)]"><NotebookPen size={17} />{t("总结笔记")}</span>
            <label title={t("导入文件")} className={`flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full text-[var(--muted-foreground)] hover:bg-[var(--muted)] ${busy ? "pointer-events-none opacity-50" : ""}`}>
              <Paperclip size={19} /><span className="sr-only">{t("导入文件")}</span>
              <input aria-label={t("导入文字材料")} type="file" multiple accept=".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.txt,.md,.csv,.srt,.vtt,.mp3,.wav,.m4a,.aac,.flac,.ogg,.mp4,.webm" disabled={busy || importing} onChange={e => { void importFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} className="sr-only" />
            </label>
            <button type="submit" aria-label={t("发送并生成笔记")} title={t("发送并生成笔记")} disabled={busy || importing || !message.trim()} className="ml-auto flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--foreground)] text-[var(--background)] focus-visible:outline-2 disabled:opacity-30"><ArrowUp size={19} /></button>
          </div>
        </div>

      </form>
        <div className="space-y-1 text-sm text-[var(--muted-foreground)]">
          {[
            ["整理一段阅读材料", "请根据以下阅读材料整理固定六章笔记，并生成 HTML：\n\n"],
            ["优化已有笔记的结构", "请在忠实保留原意的前提下，优化这份笔记的结构：\n\n"],
            ["按固定模板制作网页", "请整理以下笔记，并按照固定模板生成 HTML 网页：\n\n"],
          ].map(([label, prompt]) => <button key={label} type="button" disabled={busy || importing} onClick={() => { setMessage(prompt); messageInput.current?.focus(); }} className="flex w-full items-center gap-3 rounded-lg px-1 py-2 text-left hover:text-[var(--foreground)] focus-visible:outline-2 disabled:opacity-50"><span>{t(label)}</span><span aria-hidden className="text-[var(--primary)]">→</span></button>)}
        </div>
        </>}
      </div>
    </main>
    </div>
    {collectionOpen && <aside ref={collectionRef} id="note-collection" aria-label={t("笔记收集栏")} style={{width: collectionWidth}} className={`absolute inset-y-0 right-0 z-20 flex max-w-[92%] shrink-0 flex-col border-l border-[var(--border)] bg-[var(--background)] shadow-lg lg:relative lg:inset-auto lg:max-w-[calc(100%-240px)] lg:shadow-none ${resizingCollection?'select-none [&_iframe]:pointer-events-none':''}`}>
      <div role="separator" aria-label="调整收集栏宽度" aria-orientation="vertical" aria-valuemin={300} aria-valuenow={Math.round(collectionWidth)} tabIndex={0} title="左右拖动调整宽度，双击恢复默认" className="absolute inset-y-0 -left-1.5 z-30 w-3 touch-none cursor-col-resize hover:bg-[var(--primary)]/15 focus-visible:bg-[var(--primary)]/20 focus-visible:outline-none" onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);setResizingCollection(true);}} onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;const edge=collectionRef.current?.getBoundingClientRect().right;if(edge!==undefined)saveCollectionWidth(edge-e.clientX);}} onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);setResizingCollection(false);}} onPointerCancel={()=>setResizingCollection(false)} onLostPointerCapture={()=>setResizingCollection(false)} onDoubleClick={()=>saveCollectionWidth(380)} onKeyDown={e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();saveCollectionWidth(collectionWidth+(e.key==='ArrowLeft'?40:-40));}if(e.key==='Home'){e.preventDefault();saveCollectionWidth(380);}}}/>
      <header className="flex shrink-0 items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <h2 className="text-sm font-semibold">{t("收集栏")} <span className="ml-1 text-xs font-normal text-[var(--muted-foreground)]">{session?.turns.length || 0}</span></h2>
        <button type="button" aria-label={t("收起收集栏")} onClick={() => setCollectionOpen(false)} className="flex h-9 w-9 items-center justify-center rounded-lg hover:bg-[var(--muted)] focus-visible:outline-2"><X size={17} /></button>
      </header>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
        {!loading && session?.turns.slice().reverse().map((turn, index) => <section key={turn.id} aria-label={`${t("笔记结果")} ${session.turns.length - index}`} className="space-y-3">
          <details className="w-full rounded-2xl bg-[var(--muted)] px-4 py-3">
            <summary className="cursor-pointer text-sm"><span className="inline-block max-w-[90%] truncate align-bottom">{turn.message.split("\n").find(line => line.trim()) || t("查看本次材料／修改要求")}</span></summary>
            <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words text-sm leading-6">{turn.message}</pre>
          </details>
          <div className="space-y-3 rounded-2xl border border-[var(--border)] px-4 py-4 ">
            <div className="flex justify-end"><button type="button" disabled={busy || importing || !!deleting} onClick={() => void deleteNote(turn)} className="rounded-lg px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-40" aria-label={`删除笔记 ${turn.title || index + 1}`}>{deleting === turn.id ? "正在删除…" : "删除笔记"}</button></div>
            <div className="flex items-center gap-2 text-sm font-medium"><NotebookPen size={16} className="shrink-0 text-[var(--muted-foreground)]" /><span className="min-w-0 break-words">{turn.title || t("笔记结果")}</span><span className="ml-auto shrink-0 text-xs font-normal text-[var(--muted-foreground)]">{turn.status === "complete" ? t("已完成") : t("未完成")}</span></div>
            {turn.status !== "complete" && <p role="status" className="text-sm text-amber-700">{turn.error || t("请求正在处理，请稍后重新打开本聊天查看。")}</p>}
            {turn.status === "complete" && <>
              <div className="grid grid-cols-1 gap-2 border-b border-[var(--border)] pb-3 sm:grid-cols-2 xl:grid-cols-4">
                <button type="button" className="flex min-h-11 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-center text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] focus-visible:outline-2 focus-visible:outline-offset-2" onClick={() => void copyNotes(turn)}><span role="status">{copiedId === turn.id ? t("已复制") : t("复制笔记")}</span></button>
                <a className="flex min-h-11 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-center text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] focus-visible:outline-2 focus-visible:outline-offset-2" href={apiUrl(`/api/summary-notes/${session.id}/turns/${turn.id}/download?format=html`)}>{t("下载 HTML 网页")}</a>
                <DownloadExam sessionId={session.id} turnId={turn.id}/>
                <a className="flex min-h-11 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-center text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] focus-visible:outline-2 focus-visible:outline-offset-2" href={apiUrl(`/api/summary-notes/${session.id}/turns/${turn.id}/download?format=enex`)}>{t("导出到印象笔记")}</a>
                <p className="text-xs leading-5 text-[var(--muted-foreground)] sm:col-span-2 xl:col-span-4">{t("下载 ENEX 后在印象笔记桌面端导入，顶部附有 HTML 网页文件；重复导入会新增笔记。")}</p>
              </div>
            </>}
            {turn.status === "complete" && <ReviewExam sessionId={session.id} turnId={turn.id}/>}
            {turn.notes && <details className="group rounded-lg bg-[var(--muted)]/40">
              <summary className="cursor-pointer px-3 py-2.5 text-sm font-medium">{turn.status === "complete" ? t("文字笔记 · 点击展开") : t("文字草稿 · 点击展开")}</summary>
              <div className="border-t border-[var(--border)] px-3 py-4 sm:px-4"><MarkdownRenderer content={turn.notes} allowHtml={false} enableImages={false} variant="prose" /></div>
            </details>}
            {turn.status === "complete" && <>
              <details className="rounded-lg border border-[var(--border)]"><summary className="cursor-pointer px-3 py-2.5 text-sm font-medium">思维导图 · 点击展开</summary><NoteMindmap key={turn.id} noteId={turn.id} markdown={turn.notes}/></details><details className="rounded-lg bg-[var(--muted)]/40"><summary className="cursor-pointer px-3 py-2.5 text-sm font-medium">{t("HTML 网页 · 点击预览")}</summary><iframe title={`${turn.title} HTML`} sandbox="" srcDoc={turn.html} className="h-[60vh] w-full rounded-b-lg border-t border-[var(--border)] bg-white" /></details>

            </>}
          </div>
        </section>)}

        {!loading && !session?.turns.length && <p className="px-2 py-6 text-center text-sm text-[var(--muted-foreground)]">{t("输入的材料、文字笔记和网页会保存在这里。")}</p>}
      </div>
    </aside>}
    </div>
  </div>;
}
