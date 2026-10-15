"""Deterministic, offline HTML export using the user's unmodified template styles."""

from __future__ import annotations

from pathlib import Path
import re

from bs4 import BeautifulSoup, Comment
from markdown_it import MarkdownIt

ASSETS = Path(__file__).parent / "assets"
SECTIONS = [
    "一、阅读概览",
    "二、核心观点与论证",
    "三、关键概念与方法",
    "四、结构化思维导图",
    "五、阅读思考",
    "六、实践与复习",
]
IDS = ["overview", "ideas", "concepts", "mindmap", "reflection", "practice"]
COMPLETE = "<!-- NOTE_COMPLETE -->"
MD = MarkdownIt("commonmark", {"html": False}).enable("table")


def normalise(text: str) -> str:
    # CommonMark needs a boundary after punctuation inside Chinese bold labels.
    text = re.sub(r"(\*\*[^*\n]+[：:]\*\*)(?=\S)", r"\1 ", text)
    return re.sub(
        r"(?m)^(\*\*(?:核心观点[｜|]|解释与依据|关联关系|适用条件|原文位置))", r"\n\1", text
    )


def markdown(text: str) -> str:
    return MD.render(normalise(text))


def validate_notes(text: str) -> str:
    if not text.rstrip().endswith(COMPLETE):
        raise ValueError("回答未完整结束或材料不足，未当作完成笔记。请查看草稿和提示。")
    notes = text[: text.rfind(COMPLETE)].strip()
    headings = re.findall(r"^#{2,3}\s+(.+?)\s*$", notes, re.M)
    if headings != SECTIONS or "整理范围" not in notes:
        raise ValueError("回答缺少固定六章或整理范围，已保留草稿，未生成不完整网页。")
    for index, name in enumerate(SECTIONS):
        part = re.split(r"^#{2,3}\s+" + re.escape(name) + r"\s*$", notes, flags=re.M)[1]
        part = re.split(r"^#{2,3}\s+", part, maxsplit=1, flags=re.M)[0]
        if not part.strip():
            raise ValueError(f"{name} 没有正文，未生成不完整网页。")
    if len(re.findall(r"^```", notes, re.M)) % 2:
        raise ValueError("回答中的代码块未完整结束，已保留草稿。")
    return normalise(notes)


def render_html(notes: str) -> tuple[str, str]:
    """Only material content is rendered; raw HTML in model output is escaped."""
    parts = re.split(
        r"^#{2,3}\s+(?:" + "|".join(map(re.escape, SECTIONS)) + r")\s*$", notes, flags=re.M
    )
    if len(parts) != 7:
        raise ValueError("文字笔记必须包含按顺序排列的六章。")
    first = notes.splitlines()[0].strip().lstrip("# ")
    title = first.removesuffix("读书笔记").strip().strip("《》") or "学习材料"
    scope = re.search(r"^\*\*整理范围[：:]\*\*\s*(.+)$", parts[0], re.M)
    if not scope:
        raise ValueError("整理范围格式不完整，已保留文字。")

    overview = BeautifulSoup(markdown(parts[1]), "html.parser")
    fields: dict[str, str] = {}
    for li in list(overview.find_all("li", recursive=True)):
        strong = li.find("strong")
        if not strong:
            continue
        key = strong.get_text().strip().rstrip("：:")
        if key not in {"标题", "作者／主讲人", "所属书籍／课程", "核心问题", "一句话总结"}:
            continue
        strong.extract()
        fields[key] = li.get_text(" ", strip=True).lstrip("：:").strip()
        li.decompose()
    for ul in overview.find_all(["ul", "ol"]):
        if not ul.find("li"):
            ul.decompose()
    if not fields.get("核心问题") or not fields.get("一句话总结"):
        raise ValueError("阅读概览缺少核心问题或一句话总结，已保留文字。")

    try:
        template = (ASSETS / "note-template.html").read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError("文字笔记已整理，但固定 HTML 模板无法读取。请恢复或提供模板；文字草稿已保留。") from exc
    soup = BeautifulSoup(template, "html.parser")
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()
    soup.title.string = f"《{title}》读书笔记"
    hero = soup.select_one(".note-hero")
    hero.clear()

    def add(parent, tag, text=None, **attrs):
        node = soup.new_tag(tag, attrs=attrs)
        if text is not None:
            node.string = text
        parent.append(node)
        return node

    add(hero, "p", "结构化读书笔记", **{"class": "template-label"})
    add(hero, "h1", f"《{title}》读书笔记", **{"class": "note-title"})
    add(hero, "p", "核心问题：" + fields["核心问题"], **{"class": "learning-question"})
    add(
        hero,
        "p",
        "整理范围："
        + BeautifulSoup(markdown(scope.group(1)), "html.parser").get_text(" ", strip=True),
        **{"class": "note-intro"},
    )
    meta = add(hero, "ul", **{"class": "note-meta", "aria-label": "笔记元信息"})
    for field in ["作者／主讲人", "所属书籍／课程"]:
        if fields.get(field):
            add(meta, "li", field + "：" + fields[field])
    soup.select_one(".summary-card p").string = fields["一句话总结"]
    article = soup.select_one("#note-content")
    article.clear()
    for index, name in enumerate(SECTIONS):
        section = add(article, "section", **{"aria-labelledby": IDS[index]})
        add(section, "h2", name, id=IDS[index])
        body = overview if index == 0 else BeautifulSoup(markdown(parts[index + 1]), "html.parser")
        if index == 3:
            root = body.find("ul")
            center = root.find("li", recursive=False) if root else None
            branches_ul = center.find("ul", recursive=False) if center else None
            branches = branches_ul.find_all("li", recursive=False) if branches_ul else []
            if not 1 <= len(branches) <= 4:
                raise ValueError(
                    "思维导图须为中心主题及1至4个真实分支，已保留文字，未生成布局错误网页。"
                )
            branches_ul.extract()
            callout = add(section, "div", **{"class": "module callout"})
            add(callout, "h3", center.get_text(" ", strip=True))
            grid = add(section, "div", **{"class": "reading-map"})
            for branch in branches:
                card = add(grid, "div", **{"class": "module map-branch"})
                label = branch.find("strong", recursive=False)
                if not label:
                    raise ValueError("导图分支未使用指定文字层级，已保留文字。")
                add(card, "h3", label.get_text(" ", strip=True))
                label.extract()
                for node in list(branch.contents):
                    card.append(node.extract())
        else:
            # The fixed note uses ### for chapters and #### for subtopics;
            # the supplied website's directory tracks h2/h3.
            for heading in body.find_all("h4"):
                heading.name = "h3"
            if index == 1:
                for paragraph in list(body.find_all("p")):
                    label = paragraph.find("strong", recursive=False)
                    if not label:
                        continue
                    label_text = label.get_text().strip().rstrip("：:")
                    if not (
                        label_text.startswith("核心观点｜")
                        or label_text in {"解释与依据", "关联关系", "适用条件"}
                    ):
                        continue
                    heading = body.new_tag("h4")
                    heading.string = label_text
                    label.extract()
                    paragraph.insert_before(heading)
                    if label_text.startswith("核心观点｜"):
                        box = body.new_tag("div", attrs={"class": "module callout"})
                        heading.wrap(box)
                        box.append(paragraph.extract())
            for node in list(body.contents):
                section.append(node.extract())
    for table in article.find_all("table"):
        table.wrap(
            soup.new_tag(
                "div",
                attrs={
                    "class": "table-wrap",
                    "role": "region",
                    "tabindex": "0",
                    "aria-label": "笔记表格",
                },
            )
        )
    for index, heading in enumerate(article.select("h3, h4")):
        heading["id"] = f"detail-{index + 1}"
    for selector in ["#side-toc-list", "#mobile-toc-list", "#module-nav-links"]:
        container = soup.select_one(selector)
        container.clear()
        headings = (
            article.select("h2") if selector == "#module-nav-links" else article.select("h2, h3")
        )
        for heading in headings:
            parent = (
                container
                if selector == "#module-nav-links"
                else add(container, "li", **{"class": "toc-" + heading.name})
            )
            add(parent, "a", heading.get_text(), href="#" + heading["id"])
    return title, str(soup)
