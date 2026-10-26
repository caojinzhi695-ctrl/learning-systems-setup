'use client';
import './mindmap.css';
import {useEffect, useMemo, useRef, useState} from 'react';
import {Transformer} from 'markmap-lib/no-plugins';
import {Markmap} from 'markmap-view';
import {mindmapOutline} from './outline';

function download(content: string | Blob, type: string, filename: string) {
 const url = URL.createObjectURL(new Blob([content], {type}));
 const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
 setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function NoteMindmap({noteId, markdown}: {noteId: string; markdown: string}) {
 const original = useMemo(() => mindmapOutline(markdown), [markdown]);
 const storageKey = `deeptutor:mindmap:v1:${noteId}`;
 const [outline, setOutline] = useState(original);
 const [editing, setEditing] = useState(false), [wide, setWide] = useState(false);
 const [saved, setSaved] = useState(''), [error, setError] = useState(''), [ready, setReady] = useState(false);
 const [level, setLevel] = useState(-1);
 const [exporting, setExporting] = useState(false);
 const svg = useRef<SVGSVGElement>(null), container = useRef<HTMLDivElement>(null);
 const map = useRef<Markmap | null>(null);
 const transformer = useMemo(() => {
  const value = new Transformer();
  // Notes are untrusted text. No model HTML, remote images, links or asset loaders.
  value.md.set({html: false, linkify: false});
  value.md.renderer.rules.image = (tokens: {content: string}[], index: number) => value.md.utils.escapeHtml(tokens[index].content);
  value.md.renderer.rules.link_open = () => '';
  value.md.renderer.rules.link_close = () => '';
  return value;
 }, []);

 useEffect(() => {
  try {const draft = localStorage.getItem(storageKey); if (draft !== null) {setOutline(draft); setSaved('已载入此浏览器保存的大纲');}}
  catch {setSaved('浏览器不允许保存，请下载大纲留存');}
 }, [storageKey]);

 useEffect(() => {
  if (!svg.current) return;
  const instance = Markmap.create(svg.current, {duration: 0, maxWidth: 240, spacingHorizontal: 50, zoom: true, pan: true});
  // D3's default SVG extent reads percentage lengths during a queued transition.
  // A detached responsive canvas cannot resolve those lengths when switching views.
  const canvas = svg.current;
  instance.zoom.extent((): [[number, number], [number, number]] => [[0, 0], [canvas.clientWidth || 1, canvas.clientHeight || 1]]);
  map.current = instance;
  let frame = 0;
  const observer = new ResizeObserver(() => {
   cancelAnimationFrame(frame);
   frame = requestAnimationFrame(() => {
    if (canvas.isConnected && instance.state.data) void instance.fit();
   });
  });
  if (container.current) observer.observe(container.current);
  return () => {observer.disconnect(); cancelAnimationFrame(frame); instance.svg.interrupt(); instance.destroy(); map.current = null;};
 }, []);

 useEffect(() => {
  let cancelled = false;
  setReady(false); setError('');
  const timer = setTimeout(async () => {
   try {
    if (!outline.trim()) return;
    const {root} = transformer.transform(outline);
    await map.current?.setData(root, {initialExpandLevel: level});
    if (cancelled) return;
    await map.current?.fit();
    if (!cancelled) setReady(true);
   } catch {if (!cancelled) setError('导图无法显示，请检查大纲，或恢复 AI 原始大纲。');}
  }, 250);
  return () => {cancelled = true; clearTimeout(timer);};
 }, [outline, level, transformer]);

 useEffect(() => {
  if (!wide) return;
  const previous = document.activeElement as HTMLElement | null;
  const panel = container.current;
  const close = panel?.querySelector<HTMLButtonElement>('[data-close-map]');
  close?.focus();
  function keydown(event: KeyboardEvent) {
   if (event.key === 'Escape') {event.preventDefault(); event.stopPropagation(); setWide(false);}
   if (event.key === 'Tab' && panel) {
    const controls = [...panel.querySelectorAll<HTMLElement>('button:not(:disabled), textarea, a[href], [tabindex="0"]')];
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus();}
    else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus();}
   }
  }
  document.addEventListener('keydown', keydown, true);
  return () => {document.removeEventListener('keydown', keydown, true); previous?.focus();};
 }, [wide]);

 function change(value: string) {
  setOutline(value);
  try {localStorage.setItem(storageKey, value); setSaved('大纲已自动保存到此浏览器');}
  catch {setSaved('保存失败，请下载大纲留存');}
 }
 function exportCanvas() {
  if (!svg.current || !map.current || !ready) return null;
  const clone = svg.current.cloneNode(true) as SVGSVGElement;
  const {x1, y1, x2, y2} = map.current.state.rect;
  const width = Math.ceil(x2 - x1 + 64), height = Math.ceil(y2 - y1 + 64);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(width)); clone.setAttribute('height', String(height));
  clone.setAttribute('viewBox', `0 0 ${width} ${height}`);
  clone.style.cssText = 'background:white;color:#17233b;font:16px sans-serif';
  clone.querySelector('g')?.setAttribute('transform', `translate(${32-x1},${32-y1}) scale(1)`);
  return {clone, width, height};
 }
 function exportSvg() {
  const result = exportCanvas();
  if (result) download(new XMLSerializer().serializeToString(result.clone), 'image/svg+xml;charset=utf-8', '学习笔记-思维导图.svg');
 }
 async function exportJpg() {
  setExporting(true); setError('');
  try {
   await document.fonts.ready;
   const result = exportCanvas();
   if (!result || !svg.current) return;
   const {clone, width, height} = result;
   // Native SVG text rasterizes safely in canvas. Preserve the browser's actual
   // Chinese wrapping and bold text without drawing HTML foreignObjects.
   const originals = svg.current.querySelectorAll('foreignObject');
   clone.querySelectorAll('foreignObject').forEach((copy, index) => {
    const source = originals[index], matrix = source.getScreenCTM()?.inverse();
    if (!matrix) throw new Error('画布尚未准备好');
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const walker = document.createTreeWalker(source, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
     const node = walker.currentNode as Text;
     const style = getComputedStyle(node.parentElement!);
     let line = '', left = 0, top = 0;
     const flush = () => {
      if (!line) return;
      const point = new DOMPoint(left, top).matrixTransform(matrix);
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', String(point.x));
      text.setAttribute('y', String(point.y + parseFloat(style.fontSize) * .85));
      text.setAttribute('fill', style.color);
      text.style.cssText = `font-family:${style.fontFamily};font-size:${style.fontSize};font-weight:${style.fontWeight};font-style:${style.fontStyle};white-space:pre`;
      text.textContent = line; group.append(text); line = '';
     };
     for (let i = 0; i < node.length;) {
      const length = (node.textContent!.codePointAt(i) ?? 0) > 0xffff ? 2 : 1;
      const range = document.createRange(); range.setStart(node, i); range.setEnd(node, i + length);
      const box = range.getBoundingClientRect();
      if (line && Math.abs(box.top - top) > 1) flush();
      if (!line) {left = box.left; top = box.top;}
      line += node.data.slice(i, i + length); i += length;
     }
     flush();
    }
    copy.replaceWith(group);
   });
   const image = new Image();
   image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
   await image.decode();
   // 2x resolution, bounded for large maps and mobile canvas limits.
   const scale = Math.min(2, 8192 / width, 8192 / height, Math.sqrt(16000000 / (width * height)));
   const canvas = document.createElement('canvas');
   canvas.width = Math.max(1, Math.ceil(width * scale)); canvas.height = Math.max(1, Math.ceil(height * scale));
   const context = canvas.getContext('2d');
   if (!context) throw new Error('无法创建图片');
   context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height);
   context.drawImage(image, 0, 0, canvas.width, canvas.height);
   const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('图片生成失败')), 'image/jpeg', .95));
   download(blob, 'image/jpeg', '学习笔记-思维导图.jpg');
  } catch {setError('JPG 图片生成失败，请重试，或先下载 SVG。');}
  finally {setExporting(false);}
 }
 return <div ref={container} className={`note-mindmap${wide ? ' is-wide' : ''}`} role={wide ? 'dialog' : 'region'} aria-modal={wide || undefined} aria-label="交互式思维导图">
  <div className="mindmap-toolbar">
   <strong>AI 思维导图</strong>
   <button onClick={() => setEditing(v => !v)} aria-expanded={editing}>{editing ? '收起大纲' : '编辑大纲'}</button>
   <button disabled={!ready} onClick={() => {void map.current?.fit();}}>适应画布</button>
   <button disabled={!ready} onClick={() => {void map.current?.rescale(1.25);}} aria-label="放大思维导图">放大</button>
   <button disabled={!ready} onClick={() => {void map.current?.rescale(.8);}} aria-label="缩小思维导图">缩小</button>
   <button onClick={() => setLevel(v => v === 2 ? -1 : 2)}>{level === 2 ? '展开全部' : '收起分支'}</button>
   <button data-close-map onClick={() => setWide(v => !v)}>{wide ? '退出大图' : '查看大图'}</button>
   <button disabled={!ready} onClick={exportSvg}>下载 SVG</button>
   <button disabled={!ready || exporting} onClick={exportJpg}>{exporting ? '正在生成 JPG…' : '下载 JPG'}</button>
   <button disabled={!outline.trim()} onClick={() => download(outline, 'text/markdown;charset=utf-8', '学习笔记-导图大纲.md')}>下载大纲</button>
  </div>
  <p className="mindmap-hint">由笔记第四章生成，不额外调用 AI。拖动画布或使用缩放按钮；点击节点圆点展开、收起。可编辑大纲核对内容。</p>
  {editing && <div className="mindmap-editor"><label htmlFor={`map-outline-${noteId}`}>导图大纲（Markdown）</label><textarea id={`map-outline-${noteId}`} maxLength={40000} value={outline} onChange={e => change(e.target.value)} spellCheck={false}/><div><button disabled={outline === original} onClick={() => change(original)}>恢复 AI 原始大纲</button><span role="status">{saved}</span></div><p className="mindmap-hint">修改按笔记版本保存在此浏览器，不改动原笔记。换设备前请下载大纲备份。</p></div>}
  {error && <p className="error" role="alert">{error}</p>}
  {!outline.trim() && <p role="status">这份笔记暂无可用导图大纲。可编辑大纲，或重新生成完整 AI 笔记。</p>}
  {outline.trim() && !ready && !error && <p role="status">正在绘制思维导图…</p>}
  <svg ref={svg} className="mindmap-canvas" style={{visibility: ready ? 'visible' : 'hidden'}} aria-label="笔记知识结构导图"/>
  <p className="mindmap-attribution">可视化由 <a href="https://github.com/markmap/markmap" target="_blank" rel="noreferrer">Markmap</a> 提供 · MIT</p>
 </div>;
}
