"""ENEX export with editable text and a real, top-positioned HTML file attachment.

Reuses Content Shelf's verified ENEX structure; no cloud API or extra model call.
"""
from __future__ import annotations
import base64
from datetime import datetime, timezone
import hashlib
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from .render import MD


def clean(value: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)


def export_enex(turn: dict) -> str:
    title = clean(turn.get("title") or "学习笔记")
    html = turn["html"]
    notes = clean(turn["notes"])
    payload = html.encode("utf-8")
    digest = hashlib.md5(payload).hexdigest()
    root = ET.Element("en-export", {"export-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "application": "DeepTutor", "version": "1.0"})
    note = ET.SubElement(root, "note")
    ET.SubElement(note, "title").text = title
    enml = ET.Element("en-note")
    attachment = ET.SubElement(enml, "div")
    ET.SubElement(attachment, "en-media", {"type": "application/octet-stream", "hash": digest})
    ET.SubElement(ET.SubElement(enml, "div"), "br")
    soup = BeautifulSoup(MD.render(notes), "html.parser")
    allowed = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "s", "blockquote", "pre", "code", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "br", "hr", "a"}
    for node in list(soup.find_all(True)):
        if node.name not in allowed:
            node.unwrap()
            continue
        href = node.get("href", "")
        node.attrs = {}
        if node.name == "a" and re.match(r"^https?://", href, re.I):
            node["href"] = href
        if node.name in {"h1", "h2", "h3", "h4"}:
            node["style"] = "color:#155e75; margin-top:20px;"
        if node.name in {"td", "th"}:
            node["style"] = "border:1px solid #d9e1e8; padding:8px;"
    fragment = ET.fromstring("<div>" + soup.decode(formatter="minimal").replace("&nbsp;", "&#160;") + "</div>")
    if fragment.text:
        ET.SubElement(enml, "div").text = fragment.text
    for child in list(fragment):
        enml.append(child)
    content = '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">' + ET.tostring(enml, encoding="unicode")
    ET.SubElement(note, "content").text = content
    created = datetime.fromtimestamp(float(turn.get("created_at") or 0), timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ET.SubElement(note, "created").text = created
    ET.SubElement(note, "updated").text = created
    ET.SubElement(note, "tag").text = "DeepTutor"
    ET.SubElement(note, "tag").text = "总结笔记"
    resource = ET.SubElement(note, "resource")
    ET.SubElement(resource, "data", {"encoding": "base64"}).text = base64.b64encode(payload).decode("ascii")
    ET.SubElement(resource, "mime").text = "application/octet-stream"
    attrs = ET.SubElement(resource, "resource-attributes")
    ET.SubElement(attrs, "file-name").text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)[:80] + "-网页笔记.html"
    ET.SubElement(attrs, "attachment").text = "true"
    return '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE en-export SYSTEM "http://xml.evernote.com/pub/evernote-export3.dtd">' + ET.tostring(root, encoding="unicode")
