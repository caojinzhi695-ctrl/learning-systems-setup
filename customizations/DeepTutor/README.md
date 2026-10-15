# DeepTutor v1.6.14 总结笔记定制包

`tracked.patch` 为六个原有文件的最小差异；`files/` 仅包含新增功能代码、固定规则、模板、本地字体和无真实模型调用的测试。`manifest.json` 固定上游提交及每个分发文件的 SHA-256。应用方法见 [使用说明](../../docs/summary-notes.md)。

不包含完整上游源码、虚拟环境、构建产物、密钥、浏览器配置、个人材料或学习记录。

上游 DeepTutor 基于 Apache-2.0，许可证随附于 `UPSTREAM-LICENSE-Apache-2.0.txt`。对上游文件的修改由补丁明确标示。新增整合代码沿用仓库 MIT 许可；随包字体分别保留 `Geist-OFL.txt`、`Lora-OFL.txt`，遵守 SIL Open Font License，不能将字体改标为 MIT。名称与图标权利属于原权利人。

Geist 与 Lora 的 Latin 字体来自官方 DeepTutor v1.6.14 安装包自带资源，本地打包以避免构建时访问 Google Fonts；许可原文来自 google/fonts 的对应字体目录。固定 HTML 模板与笔记整理规则由维护者提供，生成后的个人内容不随包分发。
