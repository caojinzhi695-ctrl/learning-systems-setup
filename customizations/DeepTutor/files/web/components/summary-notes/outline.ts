/** Extract only the AI's map chapter; never mix review suggestions into source claims. */
export function mindmapOutline(markdown: string): string {
 const normalized = markdown.replace(/\r\n?/g, '\n');
 const heading = /^###\s+四、结构化思维导图\s*$/m.exec(normalized);
 if (!heading) return '';
 const rest = normalized.slice(heading.index + heading[0].length);
 const next = /^###\s+/m.exec(rest);
 return (next ? rest.slice(0, next.index) : rest).replace(/<!-- NOTE_COMPLETE -->/g, '').trim();
}
