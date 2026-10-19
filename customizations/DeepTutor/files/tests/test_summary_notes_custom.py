"""Local customization contracts; all model calls are mocked, never bill an API."""

import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from fastapi import FastAPI
import httpx

from deeptutor.api.routers import summary_notes as api
from deeptutor.services.summary_notes.render import COMPLETE, render_html, validate_notes

NOTES = """《信息的二进制表示》读书笔记

**整理范围：**依据验证用文字节选整理，未核对音频，作者未注明。

### 一、阅读概览
- **标题：**信息的二进制表示
- **作者／主讲人：**材料未注明
- **核心问题：**两种状态怎样表示信息？
- **一句话总结：**按约定组合二进制状态可以编码数字与文字。

逻辑主线：先辨认两种状态，再组合状态，最后按约定解释编码。

### 二、核心观点与论证
#### 1. 两种状态便于区分
**核心观点｜课程观点**：用0和1标记两种状态。

**解释与依据**：材料举出开和关的例子。

**关联关系**：区分状态是组合编码的前提。

**适用条件**：原文未明确说明。

### 三、关键概念与方法
#### 1. 关键概念
|概念|含义|
|---|---|
|位|一项二进制状态|
|编码|状态组合与信息的对应约定|

### 四、结构化思维导图
- **二进制表示信息**
    - **1. 状态**
        - 两种状态：0和1
    - **2. 组合**
        - 多个位：形成组合
    - **3. 约定**
        - 编码规则：赋予含义
    - **4. 理解**
        - 解读：依赖同一规则

### 五、阅读思考
以下均为延伸思考，不属于原文结论。

#### 1. 新理解
表示与解释需要共同约定。

#### 2. 待验证
不同编码的使用边界需要另找材料核实。

#### 3. 问题
- 如果约定不同，会发生什么？
- 如何确认使用了同一编码？

### 六、实践与复习
#### 1. 小行动
以下是自拟行动，并非作者原有步骤。

|小行动|具体做法|对应原文观点|
|---|---|---|
|列状态|用纸写0和1|区分两种状态|

#### 2. 复习要点
- 两种状态可以组合。
- 解释组合依赖约定。

#### 3. 快速回顾
本篇文字节选讨论如何用两种状态表示信息。材料先以开与关说明状态区分，再引出多个状态组合，最后说明编码是组合与含义之间的约定。复习时应区分状态、组合和解释三个层次。作者和适用边界未注明，本笔记没有核对音频，也没有补充节选之外的技术结论。
"""


class RenderTests(unittest.TestCase):
    def test_extra_mindmap_branches_preserved_in_four_cards(self):
        extra = "".join(f"    - **{i}. 额外主题{i}**\n        - 完整保留细节{i}\n" for i in range(5, 8))
        notes = NOTES.replace("\n### 五、阅读思考", "\n" + extra + "\n### 五、阅读思考")
        _, html = render_html(validate_notes(notes + COMPLETE))
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(soup.select(".map-branch")), 4)
        for i in range(5, 8):
            self.assertIn(f"完整保留细节{i}", soup.get_text())
        self.assertIn("解读：依赖同一规则", soup.get_text())

    def test_complete_template_and_safe_full_content(self):
        text = validate_notes(NOTES + "\n" + COMPLETE)
        title, html = render_html(text)
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(title, "信息的二进制表示")
        self.assertEqual(len(soup.select("#note-content > section")), 6)
        self.assertEqual(len(soup.select(".reading-map .map-branch")), 4)
        self.assertEqual(len(soup.select(".table-wrap table")), 2)
        ids = [node["id"] for node in soup.select("[id]")]
        self.assertEqual(len(ids), len(set(ids)))
        for a in soup.select('a[href^="#"]'):
            self.assertIn(a["href"][1:], ids)
        self.assertNotIn("模板示例", html)
        self.assertNotIn("在这里填写", html)
        self.assertNotIn("**", soup.get_text())
        self.assertEqual(soup.get_text().count("按约定组合二进制状态可以编码数字与文字。"), 1)
        self.assertNotIn("两种状态怎样表示信息？", soup.select_one("#overview").parent.get_text())
        self.assertIn("本笔记没有核对音频", soup.get_text())
        self.assertFalse(soup.select('script[src], link[rel="stylesheet"], img[src^="http"]'))
        original = BeautifulSoup(
            (api.ASSETS / "note-template.html").read_text(encoding="utf-8-sig"), "html.parser"
        )
        self.assertEqual(
            [n.get_text() for n in soup.select("style")],
            [n.get_text() for n in original.select("style")],
        )
        self.assertEqual(soup.script.get_text(), original.script.get_text())

    def test_truncated_or_incomplete_not_success(self):
        with self.assertRaises(ValueError):
            validate_notes(NOTES)
        with self.assertRaises(ValueError):
            validate_notes(NOTES.replace("### 六、实践与复习", "### 遗漏章节") + COMPLETE)

    def test_raw_html_is_not_executable(self):
        _, html = render_html(
            NOTES.replace("两种状态便于区分", '<script>alert("untrusted")</script>')
        )
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(soup.select("script")), 1)  # Only the supplied directory script.


class ContextTests(unittest.TestCase):
    def test_old_revisions_do_not_overflow_or_modify_history(self):
        turns = [{"status": "complete", "message": "旧材料" * 10000, "notes": "旧笔记" * 10000} for _ in range(8)]
        turns.append({"status": "complete", "message": "最近材料", "notes": "最近完整笔记"})
        turns.append({"status": "failed", "message": "失败重复输入", "notes": ""})
        result = api.build_generation_history(turns, "本次修改")
        self.assertEqual([x["content"] for x in result], ["最近材料", "最近完整笔记", "本次修改"])
        self.assertEqual(len(turns), 10)

    def test_actual_large_request_rejected_without_truncation(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            api.build_generation_history([], "字" * 60001)
        self.assertEqual(error.exception.status_code, 413)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_chats_downloads_dedup_and_incomplete(self):
        app = FastAPI()
        app.include_router(api.router)
        count = 0
        truncated = False
        auth_failed = False

        async def fake_stream(**kwargs):
            nonlocal count
            count += 1
            if auth_failed:
                yield "已收到的部分文字"
                class AuthenticationFailure(Exception):
                    status_code = 401
                raise AuthenticationFailure("secret-value-must-not-be-exposed")
            self.assertEqual(kwargs["max_retries"], 0)
            self.assertEqual(kwargs["max_tokens"], 16000)
            self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "disabled"}})
            self.assertIn("材料", kwargs["messages"][-1]["content"])
            kwargs["outcome"].finish_reason = "length" if truncated else "stop"
            yield NOTES + "\n" + COMPLETE

        config = SimpleNamespace(
            model="test-only", api_key="unused", base_url="https://api.deepseek.com", binding="deepseek"
        )
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(api, "directory", return_value=Path(temp)),
            patch("deeptutor.services.llm.get_llm_config", return_value=config),
            patch("deeptutor.services.llm.factory.stream", fake_stream),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local"
            ) as client:
                session = (await client.post("/summary-notes")).json()
                url = f"/summary-notes/{session['id']}"
                body = {"message": "材料：0和1表示两种状态。", "request_id": "a" * 32}
                self.assertEqual((await client.post(url + "/generate", json=body)).status_code, 400)
                body["confirm_api_cost"] = True
                result = (await client.post(url + "/generate", json=body)).json()
                self.assertEqual(result["turns"][0]["status"], "complete")
                await client.post(url + "/generate", json=body)
                self.assertEqual(count, 1)
                self.assertEqual((await client.get(url)).json()["title"], "信息的二进制表示")
                for format in ["html", "md"]:
                    response = await client.get(
                        url + "/turns/" + "a" * 32 + "/download?format=" + format
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("attachment", response.headers["content-disposition"])
                    self.assertTrue(
                        (Path(temp) / session["id"] / ("a" * 32 + "." + format)).exists()
                    )
                auth_failed = True
                body["request_id"] = "c" * 32
                auth_result = (await client.post(url + "/generate", json=body)).json()["turns"][-1]
                self.assertEqual(auth_result["status"], "failed")
                self.assertIn("401", auth_result["error"])
                self.assertNotIn("secret-value", auth_result["error"])
                self.assertEqual(auth_result["notes"], "已收到的部分文字")
                self.assertEqual(auth_result["message"], body["message"])
                auth_failed = False
                truncated = True
                body["request_id"] = "b" * 32
                failed = (await client.post(url + "/generate", json=body)).json()["turns"][-1]
                self.assertEqual(failed["status"], "failed")
                self.assertTrue(failed["notes"])
                self.assertFalse(failed["html"])
                self.assertEqual(
                    (await client.get(url + "/turns/" + "b" * 32 + "/download")).status_code, 404
                )
                self.assertEqual(
                    (await client.get("/summary-notes/not-a-valid-id")).status_code, 404
                )


if __name__ == "__main__":
    unittest.main()
