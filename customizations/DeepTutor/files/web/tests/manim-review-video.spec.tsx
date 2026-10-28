import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ManimReviewVideo from "../components/summary-notes/ManimReviewVideo";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiFetch, apiUrl: (url: string) => url }));

describe("Manim review video", () => {
  it("opens the clicked collection note and lets the user switch notes without starting a paid request", async () => {
    apiFetch.mockClear();
    apiFetch.mockImplementation(async () => ({ ok: true, json: async () => ({ jobs: [] }) }));
    const notes = [
      { id: "older-note", title: "收集栏点击的笔记", notes: "重点", status: "complete" },
      { id: "latest-note", title: "最新笔记", notes: "另一篇重点", status: "complete" },
    ];
    const { rerender } = render(<ManimReviewVideo open onClose={() => {}} sessionId="session" initialNoteId="older-note" notes={notes} />);
    const select = screen.getByLabelText("选择视频笔记");
    await waitFor(() => expect(select).toHaveValue("older-note"));
    fireEvent.change(select, { target: { value: "latest-note" } });
    await waitFor(() => expect(select).toHaveValue("latest-note"));
    rerender(<ManimReviewVideo open={false} onClose={() => {}} sessionId="session" initialNoteId="older-note" notes={notes} />);
    rerender(<ManimReviewVideo open onClose={() => {}} sessionId="session" initialNoteId="older-note" notes={notes} />);
    await waitFor(() => expect(screen.getByLabelText("选择视频笔记")).toHaveValue("older-note"));
    expect(apiFetch.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
  });

  it("calls DeepSeek once and then presents the server-rendered MP4 and source download", async () => {
    const scene = { title: "新品调研", layout: "matrix", duration: 6, caption: "四维框架", source_quote: "从四维调研", caution: "" };
    const completed = { id: "job", status: "complete", renderer: "manim", model: "deepseek-test", created_at: 1, error: "", progress: 100, video: true, plan: { title: "AI设计的Manim视频", summary: "根据AI笔记设计", scenes: [scene] } };
    apiFetch.mockImplementation(async (url: string, options?: RequestInit) => ({ ok: true, json: async () => options?.method === "POST" ? { ...completed, status: "queued", plan: null, video: false } : url.endsWith("/video-plans") ? { jobs: [] } : completed }));
    render(<ManimReviewVideo open onClose={() => {}} sessionId="session" notes={[{ id: "note", title: "已完成AI笔记", notes: "从四维调研", status: "complete" }]} />);
    const generate = screen.getByRole("button", { name: "DeepSeek 自动设计并生成 Manim 视频" });
    await waitFor(() => expect(generate).toBeEnabled()); fireEvent.click(generate);
    await waitFor(() => expect(screen.getByLabelText("生成的Manim复习视频")).toBeInTheDocument());
    expect(screen.getByLabelText("生成的Manim复习视频")).toHaveAttribute("src", expect.stringContaining("/file?inline=true"));
    expect(screen.getByRole("link", { name: "下载 MP4 视频" })).toHaveAttribute("href", expect.stringContaining("/file"));
    expect(screen.getByRole("link", { name: "下载 Manim 源码与分镜" })).toHaveAttribute("href", expect.stringContaining("/source"));
    const posts = apiFetch.mock.calls.filter(([, options]) => options?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1].body)).toMatchObject({ confirm_api_cost: true });
    expect(posts[0][0]).toContain("/session/turns/note/video-plans");
  });
});
