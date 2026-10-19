# DeepTutor + OpenMAIC 中文学习系统安装指南

[![平台](https://img.shields.io/badge/平台-Windows%2011-blue)](#环境要求)
[![文档](https://img.shields.io/badge/文档-简体中文-green)](docs/usage.md)
[![协议](https://img.shields.io/badge/协议-MIT-green)](LICENSE)

面向非专业开发者的两套开源学习工具安装、启动、DeepSeek API 配置和备份方案。

**最新定制（0.5.0）：文字笔记一键复制、收集栏最新置顶、简短来源说明；仅“解释与依据”采用简洁分点表达。修复密钥错误提示、导图分支过多及历史上下文累积问题。保留印象笔记导出、文件导入与版本管理。**

**2026-10-19 更新：** 总结笔记支持多格式文件拖入、可配置的本机音视频转写、单条删除与最新优先排序；修复 DeepSeek 长笔记被截断的问题。配置与验证范围见 [总结笔记说明](docs/summary-notes.md)。

**DeepTutor 固定模板总结笔记。** 主页式居中输入框、可折叠右侧收集栏，粘贴材料后同时获得六章文字笔记与独立 HTML 网页。新安装会自动应用定制；已有安装见 [定制安装与使用](docs/summary-notes.md)。

**本仓库是安装与使用整合仓库，并非 DeepTutor 或 OpenMAIC 官方项目，也不重新分发两者完整源码。** 安装时直接从各自官方来源获取指定稳定版本，再应用随包注明版本的本地定制补丁。

## 2026-10-18 启动优化更新

新增已安装实例的无命令行窗口启动、健康服务复用、半启动修复、数据库独立后台运行及官方图标快捷方式。新版实例验证为 DeepTutor v1.6.14 / OpenMAIC v1.2.0。使用条件、命令和测试边界见 [启动修复说明](docs/startup-2026-10-18.md)。下文旧版安装流程及 10 月 15 日测试记录保留，不能视为新版全新安装验证。

## 两个项目分别做什么

| 项目 | 用途 | 官方来源 | 本次验证版本 |
| --- | --- | --- | --- |
| DeepTutor | 规划知识体系、逐点讲解、练习反馈、掌握路线与复习 | [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) | `v1.6.14` |
| OpenMAIC | 生成课程大纲、课件、课堂讲解和互动练习 | [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) | `v1.1.4` |

推荐流程：用 DeepTutor 规划路线 → 用 OpenMAIC 学一节短课 → 回到 DeepTutor 练习和查漏补缺。

版本记录日期：2026-10-15。这里固定的是已验证版本，不承诺它们永远是最新版本；升级前查看官方 Releases 和迁移说明。

## 已完成的验证

测试主题：**计算机如何用 0 和 1 表示信息**。

| 检查 | DeepTutor | OpenMAIC |
| --- | --- | --- |
| 启动与浏览器页面 | 通过 | 通过 |
| DeepSeek API 实际调用 | 通过，`deepseek-flash` | 通过，`deepseek-flash` |
| 学习内容 | 普通问答、两个知识点的正式掌握路线 | 两页课件、一页选择题及完成页 |
| 练习 | 提交正确选项后正确判分 | 选择题 10/10 |
| 重启保存 | 路线、讲解、答题记录保留 | 课程、答题报告保留 |
| 导出 | 本次未测试聊天导出 | 课堂 ZIP 导出成功，完整性校验通过 |

**通过这些检查不代表所有功能或所有生成内容都正确。** 完整通关、跨日期复习、知识库检索、复杂公式、图片/语音/视频和 OpenMAIC Pro 工作台未验证。详细边界见 [测试记录](docs/verification.md)。

## 环境要求

- Windows 11，PowerShell 7（建议使用 `pwsh` 运行脚本）。
- Git；Python 3.11–3.14，建议 3.12；Node.js ≥22.19；pnpm ≥10。
- 官方 npm 命令必须可用。已有环境不会被卸载或替换。
- 可访问 GitHub、PyPI、npm 与模型供应商。
- 磁盘空间取决于依赖、课程和资料量，建议预留至少 15 GB。

实际安装验证使用 Windows 11、Python 3.12、Node.js 24。基础云端文字学习不需要独立显卡。

## 快速开始

```powershell
git clone https://github.com/caojinzhi695-ctrl/learning-systems-setup.git
cd learning-systems-setup

# 先检查环境、工具和默认端口
pwsh -NoProfile -File ./scripts/manage.ps1 -Action Check

# 安装到当前仓库之外的目录；可改成自己选择的绝对路径
pwsh -NoProfile -File ./scripts/manage.ps1 -Action Install -Root 'E:\LearningSystems'

# 在本机隐藏输入 DeepSeek 密钥，分别保存到两个项目
pwsh -NoProfile -File ./scripts/manage.ps1 -Action Configure -Root 'E:\LearningSystems'

pwsh -NoProfile -File ./scripts/manage.ps1 -Action Start -Root 'E:\LearningSystems'
```

安装完成后会从 DeepSeek 官网下载图标，在当前 Windows 桌面创建 **“DeepSeek 官方 API 密钥”** 快捷方式，并用默认浏览器打开官方密钥页面，供你手动登录。不会自动登录、读取浏览器凭据、创建密钥或充值。

已有安装可以单独补建快捷方式并打开登录页，无需重装：

```powershell
pwsh -NoProfile -File ./scripts/manage.ps1 -Action DeepSeekPortal -Root 'E:\LearningSystems'
# 只创建快捷方式，不打开网页
pwsh -NoProfile -File ./scripts/deepseek-shortcut.ps1 -Root 'E:\LearningSystems' -NoOpen
```

图标保存在安装目录 `shortcut-icons`；桌面位置由 Windows 解析，不写死用户名，也支持已重定向的桌面。遇到验证码或登录限制由用户手动处理，不绕过。官方下载失败会报错；可重复执行上述命令，已有快捷方式修改前会备份。

脚本不购买、不充值、不发送模型测试请求。配置成功只表示设置已保存；第一次问答或生成课程会调用 API 并产生费用。

安装脚本与文档整理后进行了静态检查，**尚未在另一台全新电脑重新安装验证**。本机原安装的运行验证与整合脚本的可移植性验证是两件事。

## 浏览器地址与日常管理

| 项目 | 网页 | 服务 |
| --- | --- | --- |
| DeepTutor | <http://127.0.0.1:3782> | 后端 8001，网页 3782 |
| 总结笔记定制 | <http://127.0.0.1:3782/summary-notes> | 使用 DeepTutor 已配置模型 |
| OpenMAIC | <http://127.0.0.1:3001> | 应用服务 3001 |

```powershell
# 分别启动或停止，也可以用 -Project Both
pwsh -NoProfile -File ./scripts/manage.ps1 -Action Start -Project DeepTutor -Root 'E:\LearningSystems'
pwsh -NoProfile -File ./scripts/manage.ps1 -Action Stop -Project OpenMAIC -Root 'E:\LearningSystems'
pwsh -NoProfile -File ./scripts/manage.ps1 -Action Restart -Root 'E:\LearningSystems'
```

没有开机自启。退出网页不等于停止后台服务。启动前先检查端口，遇到其他程序占用不停止其他程序。

## DeepSeek API

- [官方开放平台与充值](https://platform.deepseek.com/)
- [官方密钥管理](https://platform.deepseek.com/api_keys)
- [官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

本方案使用官方 `deepseek-flash`，DeepTutor 端点为 `https://api.deepseek.com`，OpenMAIC 使用兼容路径 `https://api.deepseek.com/v1`。不要购买来源不明的共享密钥。API 费用与 ChatGPT 订阅无关。

**不要把密钥粘贴到聊天、Issue、README、截图或 Git 提交。** 使用本地隐藏输入。重新配置前会备份原配置；备份也可能包含密钥，只能私下保存。

文字模型不等于嵌入模型；本方案未配置知识库向量检索。语音、图片、视频属于额外配置与费用，本次未启用。

## 数据布局

```text
安装根目录（不放进 Git）/
├── DeepTutor/             # 官方参考源码 + 独立 .venv
├── DeepTutor-runtime/     # 私有配置、聊天、学习记录、文件
├── OpenMAIC/              # 官方源码、node_modules、.env.local
├── OpenMAIC-data/exports/ # 手动导出的课堂 ZIP
├── backups/               # 私有备份，可能含凭据
└── logs/                  # 本机运行日志
```

OpenMAIC 当前使用官方默认浏览器 IndexedDB。请固定使用同一浏览器、同一主机名和端口；`localhost` 与 `127.0.0.1` 是不同站点。源码目录备份不会包含浏览器课程。详见 [备份、更新与卸载](docs/maintenance.md)。

## 已知问题与本地修改

- DeepTutor：总结笔记定制包位于 `customizations/DeepTutor`，包含固定规则与模板、文字/HTML 双文件交付、主页式输入和右侧收集栏，严格适配 v1.6.14。它是本仓库定制，使用源码安装，见 [完整说明](docs/summary-notes.md)。
- DeepTutor：浏览器保存的语言优先于服务端。需在当前浏览器设置“界面语言”和“模型输出语言”为中文；不要依赖自动网页翻译。
- DeepTutor：选择题随机排序后，解析可能仍引用旧选项字母；本次判分正确，文字解析有歧义，尚未修复。以完整选项含义判断，可申请复核。
- DeepTutor：配置兼容问题的最小补丁见 `scripts/prepare.py`；改动前备份原文件。
- OpenMAIC：中文包补译与页脚调整由 `scripts/prepare.py` 应用，需重新构建。
- 重复启动会检查已有健康服务；不关闭安全软件，不绕过登录与证书限制。
- 未包含实验性的 ChatGPT 网页适配层：此前专用浏览器登录被拦截，无法证明其能替代项目完整模型接口。

## 文档与反馈

- [第一次学习操作](docs/usage.md)
- [总结笔记：定制安装与固定模板使用](docs/summary-notes.md)
- [测试记录与内容检查](docs/verification.md)
- [备份、更新、卸载](docs/maintenance.md)
- [安全与隐私](SECURITY.md)
- [变更记录](CHANGELOG.md)

报告问题时写明操作系统、版本、失败步骤和脱敏错误；不要附带密钥或私人学习材料。

## 致谢与许可证

DeepTutor 由 HKUDS 等上游贡献者开发，按 [Apache-2.0](https://github.com/HKUDS/DeepTutor/blob/v1.6.14/LICENSE) 发布；OpenMAIC 由 THU-MAIC 等上游贡献者开发，按 [MIT](https://github.com/THU-MAIC/OpenMAIC/blob/v1.1.4/LICENSE) 发布。各自名称、图标、源码和依赖的权利属于对应权利人。

本仓库新增的整合脚本与说明使用 [MIT](LICENSE)。不覆盖或改变上游及第三方依赖许可证。
