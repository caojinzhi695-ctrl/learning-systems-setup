"""Local service lifecycle. No provider requests and no configuration migration."""
import argparse
import contextlib
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
from pathlib import Path
import socket
import shutil
import subprocess
import time
import urllib.request

# Set by launch-ui.py / runtime.ps1; never infer another installation.
if not os.environ.get('LEARNING_SYSTEMS_ROOT'):
    raise RuntimeError('Set LEARNING_SYSTEMS_ROOT to the existing installation directory.')
ROOT = Path(os.environ['LEARNING_SYSTEMS_ROOT']).resolve()
if not ROOT.is_dir():
    raise RuntimeError('Installation directory does not exist.')
REAL_ROOT = ROOT.resolve()
LOGS = ROOT / 'logs'
STATE = LOGS / 'services'
STATE.mkdir(parents=True, exist_ok=True)
node_candidates = sorted((ROOT/'tools').glob('node-*-win-x64/node.exe'))
NODE = Path(os.environ.get('LEARNING_SYSTEMS_NODE') or (str(node_candidates[-1]) if len(node_candidates) == 1 else shutil.which('node') or 'node.exe'))
PYTHON = ROOT / 'DeepTutor/.venv/Scripts/pythonw.exe'
PG = ROOT / 'tools/pgsql/bin'
PGDATA = ROOT / 'OpenMAIC-data/postgres'
NO_WINDOW = subprocess.CREATE_NO_WINDOW
DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PORTS = {'backend': 8001, 'frontend': 3782, 'openmaic': 3001}
URLS = {'backend': 'http://127.0.0.1:8001/health/ready',
        'frontend': 'http://127.0.0.1:3782', 'openmaic': 'http://127.0.0.1:3001'}
LABELS = {'backend':'DeepTutor 学习服务','frontend':'DeepTutor 网页','openmaic':'OpenMAIC 课堂'}
KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
KERNEL.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
KERNEL.OpenProcess.restype = wintypes.HANDLE
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
KERNEL.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
KERNEL.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

def say(message):
    print(message, flush=True)

def process_identity(pid):
    handle = KERNEL.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        if not KERNEL.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not KERNEL.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        if not KERNEL.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            return None
        return {'pid': int(pid), 'created': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                'image': str(Path(name.value).resolve()).casefold()}
    finally:
        KERNEL.CloseHandle(handle)

def record(role, pid):
    identity = process_identity(pid)
    if identity:
        (STATE / f'{role}.json').write_text(json.dumps(identity), encoding='utf-8')
    return identity

def saved(role):
    try:
        identity = json.loads((STATE / f'{role}.json').read_text(encoding='utf-8'))
        return identity if process_identity(identity['pid']) == identity else None
    except (OSError, ValueError, KeyError):
        return None

def legacy(role):
    # Only adopt commands explicitly tied to this installation. Never use port ownership alone.
    command = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, creationflags=NO_WINDOW, timeout=20)
    if result.returncode:
        return None
    rows = json.loads(result.stdout.decode('utf-8-sig'))
    roots = [str(p).replace('/', '\\').casefold() for p in (ROOT, REAL_ROOT)]
    for row in rows:
        cmd = (row.get('CommandLine') or '').replace('/', '\\').casefold()
        matches = (role == 'backend' and 'deeptutor.api.main:app' in cmd and any(r + '\\deeptutor\\.venv\\scripts\\' + p in cmd for r in roots for p in ('python.exe','pythonw.exe'))
                   or role == 'frontend' and any(r + '\\deeptutor\\web\\.next-deeptutor\\standalone\\server.js' in cmd for r in roots)
                   or role == 'openmaic' and any(r + '\\openmaic\\node_modules\\next\\dist\\bin\\next' in cmd for r in roots))
        if matches:
            return record(role, row['ProcessId'])
    return None

def owned(role):
    return saved(role) or legacy(role)

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.25):
            return True
    except OSError:
        return False

def healthy(role):
    if not listening(PORTS[role]):
        return False
    try:
        with OPENER.open(URLS[role], timeout=1.5) as response:
            if response.status != 200:
                return False
            return role != 'backend' or json.load(response).get('status') == 'ready'
    except Exception:
        return False

def spawn(role, args, cwd, extra_env=None):
    env = os.environ.copy()
    env.update({'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1', 'NEXT_TELEMETRY_DISABLED': '1',
                'NO_PROXY': '127.0.0.1,localhost,::1'})
    env.update(extra_env or {})
    env.setdefault('NODE_OPTIONS', '--max-old-space-size=2048')
    with (LOGS / f'{role}.stdout.log').open('ab') as stdout, (LOGS / f'{role}.stderr.log').open('ab') as stderr:
        options = dict(cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                       close_fds=True)
        flags = DETACHED
        if role == 'postgres-control':
            # pg_ctl starts cmd.exe with inherited console settings. Give the
            # database its own hidden console so that child cannot create a
            # visible Windows Terminal window when the launcher exits.
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow = 0
            options['startupinfo'] = info
            flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            child = subprocess.Popen([str(a) for a in args], creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
        except OSError as error:
            if error.winerror != 5:
                raise
            child = subprocess.Popen([str(a) for a in args], creationflags=flags, **options)
    record(role, child.pid)
    return child

def stop_role(role):
    identity = owned(role)
    if identity:
        # Compare executable AND creation time before terminating this exact process tree.
        if process_identity(identity['pid']) != identity:
            raise RuntimeError('进程已变化，拒绝停止其他程序。')
        result = subprocess.run(['taskkill.exe', '/PID', str(identity['pid']), '/T', '/F'],
                                capture_output=True, creationflags=NO_WINDOW, timeout=20)
        if result.returncode and process_identity(identity['pid']):
            raise RuntimeError(f'{role} 无法停止，请检查本地日志。')
        for _ in range(20):
            if not listening(PORTS[role]):
                break
            time.sleep(.2)
    elif listening(PORTS[role]):
        raise RuntimeError(f'端口 {PORTS[role]} 不属于本安装，未停止其他程序。')

def pg_ready():
    if not listening(55432):
        return False
    return subprocess.run([str(PG/'pg_isready.exe'), '-h', '127.0.0.1', '-p', '55432', '-t', '1'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW).returncode == 0

def pg_owned():
    try:
        lines = (PGDATA/'postmaster.pid').read_text().splitlines()
        pid = int(lines[0])
        identity = process_identity(pid)
        if not identity or identity['image'] != str((PG/'postgres.exe').resolve()).casefold():
            return False
        created_unix = identity['created'] / 10000000 - 11644473600
        return (Path(lines[1]).resolve() == PGDATA.resolve() and int(lines[3]) == 55432
                and abs(created_unix - int(lines[2])) < 10)
    except (OSError, ValueError, IndexError):
        return False

def start_pg():
    if pg_ready():
        if not pg_owned():
            raise RuntimeError('数据库端口由其他安装占用，未进行修改。')
        return
    if listening(55432) and not pg_owned():
        raise RuntimeError('数据库端口被其他程序占用。')
    say('正在准备 OpenMAIC 数据库……')
    child = spawn('postgres-control', [PG/'pg_ctl.exe', '-D', PGDATA, '-l', LOGS/'postgres.log', 'start', '-w', '-t', '60'], ROOT)
    until = time.monotonic() + 65
    while time.monotonic() < until:
        if pg_ready() and pg_owned():
            return
        if child.poll() not in (None, 0):
            raise RuntimeError('数据库启动失败，请查看 logs/postgres.log，未删除任何数据。')
        time.sleep(.5)
    raise RuntimeError('数据库尚未就绪，请查看 logs/postgres.log。')

def start_role(role):
    identity = owned(role)
    if healthy(role):
        if not identity:
            raise RuntimeError(f'端口 {PORTS[role]} 的服务归属无法确认。')
        say(f'{LABELS[role]} 已就绪，复用后台服务。')
        return
    if listening(PORTS[role]) and not identity:
        raise RuntimeError(f'端口 {PORTS[role]} 被其他程序占用。')
    if identity:
        stop_role(role)
    say(f'正在启动 {LABELS[role]}……')
    if role == 'backend':
        args = [PYTHON, '-m', 'uvicorn', 'deeptutor.api.main:app', '--host', '127.0.0.1', '--port', '8001',
                '--no-access-log', '--no-proxy-headers', '--ws-max-size', '43341141', '--timeout-keep-alive', '300', '--workers', '1']
        cwd = ROOT/'DeepTutor'
        env = {'DEEPTUTOR_HOME': str(ROOT/'DeepTutor-runtime'), 'BACKEND_PORT': '8001', 'FRONTEND_PORT': '3782'}
    elif role == 'frontend':
        server = ROOT/'DeepTutor/web/.next-deeptutor/standalone/server.js'
        if not server.exists():
            raise RuntimeError('DeepTutor 的生产构建缺失；不会在双击时自动安装或重新构建。')
        args, cwd = [NODE, server], server.parent
        auth_path = ROOT/'DeepTutor-runtime/data/user/settings/auth.json'
        auth = json.loads(auth_path.read_text(encoding='utf-8-sig')).get('enabled', False)
        env = {'PORT': '3782', 'HOSTNAME': '127.0.0.1', 'NODE_ENV': 'production',
               'DEEPTUTOR_API_BASE_URL': 'http://127.0.0.1:8001', 'DEEPTUTOR_AUTH_ENABLED': str(auth).lower()}
    else:
        if not (ROOT/'OpenMAIC/.next/BUILD_ID').exists():
            raise RuntimeError('OpenMAIC 的生产构建缺失，不会在启动时自动重建。')
        args, cwd = [NODE, ROOT/'OpenMAIC/node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3001'], ROOT/'OpenMAIC'
        env = {}
    child = spawn(role, args, cwd, env)
    until = time.monotonic() + (120 if role == 'backend' else 60)
    while time.monotonic() < until:
        if healthy(role):
            return
        if child.poll() is not None:
            raise RuntimeError(f'{role} 启动失败，请查看 logs/{role}.stderr.log。')
        time.sleep(.4)
    raise RuntimeError(f'{role} 尚未就绪，请查看 logs/{role}.stderr.log。')

@contextlib.contextmanager
def project_lock(project):
    with (STATE/f'{project}.lock').open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0'); stream.flush()
        until = time.monotonic() + 180
        while True:
            try:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > until:
                    raise RuntimeError('已有启动操作长时间未完成，请查看日志。')
                time.sleep(.3)
        try:
            yield
        finally:
            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

def open_browser(project):
    edge_candidates = [Path(os.environ.get(key, ''))/'Microsoft/Edge/Application/msedge.exe'
                       for key in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA')]
    edge = next((p for p in edge_candidates if p.is_file()), None)
    if edge is None:
        raise RuntimeError('未找到 Microsoft Edge，请先安装或手动打开网页地址。')
    profile = ROOT/('DeepTutor-runtime/browser' if project == 'DeepTutor' else 'OpenMAIC-data/browser')
    url = URLS['frontend' if project == 'DeepTutor' else 'openmaic']
    subprocess.Popen([str(edge), f'--user-data-dir={profile}', '--lang=zh-CN', '--no-first-run', '--new-window', url],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=DETACHED, close_fds=True)

def manage(action, project, open_page=False):
    start = time.monotonic()
    project_times = {}
    for name in (['DeepTutor','OpenMAIC'] if project == 'Both' else [project]):
        project_start = time.monotonic()
        with project_lock(name):
            roles = ['backend','frontend'] if name == 'DeepTutor' else ['openmaic']
            if action == 'Check':
                say(json.dumps({'project':name, 'services':{r:healthy(r) for r in roles}}, ensure_ascii=False))
                continue
            if action in ('Stop','Restart'):
                for role in reversed(roles):
                    stop_role(role)
                if name == 'OpenMAIC' and pg_owned():
                    result = subprocess.run([str(PG/'pg_ctl.exe'), '-D', str(PGDATA), 'stop', '-m', 'fast', '-w'],capture_output=True,creationflags=NO_WINDOW,timeout=65)
                    if result.returncode:
                        raise RuntimeError('数据库未能正常停止，已保留数据。')
                    until=time.monotonic()+60
                    while pg_owned() and time.monotonic()<until:
                        time.sleep(.3)
                    if pg_owned():
                        raise RuntimeError('数据库正在停止，请稍后再启动。')
            if action in ('Start','Restart'):
                if name == 'OpenMAIC': start_pg()
                for role in roles: start_role(role)
                if open_page: open_browser(name)
                say(f'{name} 已就绪。')
            project_times[name] = round(time.monotonic()-project_start, 2)
    duration = round(time.monotonic()-start, 2)
    with (LOGS/'startup-timings.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'time':time.strftime('%Y-%m-%d %H:%M:%S'), 'project':project, 'action':action,'seconds':duration,'projects':project_times})+'\n')
    say(f'本次操作耗时 {duration:.2f} 秒。')

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--action', choices=['Start','Stop','Restart','Check'], default='Start')
    parser.add_argument('--project', choices=['DeepTutor','OpenMAIC','Both'], default='Both')
    parser.add_argument('--open', action='store_true')
    args=parser.parse_args()
    try:
        manage(args.action,args.project,args.open)
    except Exception as exc:
        say(str(exc)); raise SystemExit(1)
