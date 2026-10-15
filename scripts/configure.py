"""Configure two private installs; never print credentials or call a model."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
key = os.environ.get('LEARNING_DEEPSEEK_SETUP_KEY', '').strip()
if not key or any(c in key for c in '\r\n'):
    raise SystemExit('Empty or invalid key; no settings changed.')
cli = root / 'DeepTutor/.venv/Scripts/deeptutor.exe'
env_file = root / 'OpenMAIC/.env.local'
if not cli.exists() or not env_file.exists():
    raise SystemExit('Install both projects before configuring.')
backup = root / 'backups' / ('config-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
backup.mkdir(parents=True)
settings = root / 'DeepTutor-runtime/data/user/settings'
if settings.exists():
    shutil.copytree(settings, backup / 'DeepTutor-settings')
shutil.copy2(env_file, backup / 'OpenMAIC.env.local')
setup = root / 'deepseek-setup.json'
if setup.exists():
    shutil.copy2(setup, backup / 'deepseek-setup.json')
setup.write_text(json.dumps({'llm': {'provider': 'deepseek', 'model': 'deepseek-flash', 'base_url': 'https://api.deepseek.com', 'api_format': 'openai_chat', 'api_key_env': 'LEARNING_DEEPSEEK_SETUP_KEY'}}, indent=2), encoding='utf-8')
env = os.environ.copy()
env['DEEPTUTOR_HOME'] = str(root / 'DeepTutor-runtime')
env['PYTHONUTF8'] = '1'
for extra in (['--check'], []):
    result = subprocess.run([str(cli), 'config', 'apply', str(setup), *extra], env=env, capture_output=True)
    if result.returncode:
        raise SystemExit('DeepTutor setup failed; diagnostic output withheld to protect credentials. Backup retained.')
text = env_file.read_text(encoding='utf-8-sig')
for name, value in {'DEEPSEEK_API_KEY': key, 'DEEPSEEK_BASE_URL': 'https://api.deepseek.com/v1', 'DEEPSEEK_MODELS': 'deepseek-flash', 'DEFAULT_MODEL': 'deepseek:deepseek-flash'}.items():
    pattern = rf'(?m)^{name}=.*$'
    line = name + '=' + value
    text = re.sub(pattern, lambda _: line, text) if re.search(pattern, text) else text.rstrip() + '\n' + line + '\n'
temporary = env_file.with_name('.env.configuring')
temporary.write_text(text, encoding='utf-8')
temporary.replace(env_file)
print('Both private installations configured. No model request sent.')
