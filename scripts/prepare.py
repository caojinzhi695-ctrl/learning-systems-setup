"""Version-scoped local compatibility and Chinese-copy changes, with backups."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--project', choices=['DeepTutor', 'OpenMAIC'], required=True)
args = parser.parse_args()
root = args.root.resolve()
backup = root / 'backups' / ('prepare-' + args.project + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
backup.mkdir(parents=True)

def replace(path, pairs):
    text = path.read_text(encoding='utf-8')
    updated = text
    for old, new in pairs.items():
        if old not in updated and new not in updated:
            raise SystemExit(f'Expected version-specific text missing in {path.name}; no blind replacement.')
        updated = updated.replace(old, new)
    if updated != text:
        shutil.copy2(path, backup / path.name)
        path.write_text(updated, encoding='utf-8')

if args.project == 'DeepTutor':
    replace(root / 'DeepTutor/.venv/Lib/site-packages/deeptutor/services/llm/client.py', {
        'if api_key := self.config.get_api_key():': 'if api_key := (self.config.get_api_key() if callable(getattr(self.config, "get_api_key", None)) else self.config.api_key):',
    })
else:
    replace(root / 'OpenMAIC/lib/i18n/locales/zh-CN.json', {
        'Generative Learning in Multi-Agent Interactive Classroom': '在多智能体互动课堂中，开启生成式学习',
        'Jump unavailable for this line': '此行暂不支持跳转',
        'Previous line': '上一句',
        'Line {{current}} / {{total}}': '第 {{current}} 句，共 {{total}} 句',
        '"Backend"': '"后端服务"',
        'Prompt {{count}}': '参考提示 {{count}}',
        '"Access Key"': '"访问密钥"',
    })
    replace(root / 'OpenMAIC/app/page.tsx', {'OpenMAIC Open Source Project': "{t('home.openSourceProject', { defaultValue: 'OpenMAIC 开源项目' })}"})
print('Version-scoped preparation complete; originals backed up privately.')
