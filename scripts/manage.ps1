param(
  [ValidateSet('Check','Install','Configure','Start','Stop','Restart','DeepSeekPortal','CustomizeNotes')][string]$Action = 'Check',
  [ValidateSet('Both','DeepTutor','OpenMAIC')][string]$Project = 'Both',
  [string]$Root = (Join-Path $env:LOCALAPPDATA 'LearningSystems')
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$repo = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot))
if($Root -eq $repo -or $Root.StartsWith($repo + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Choose an installation root outside this public repository.' }
$env:PYTHONUTF8 = '1'
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:pnpm_config_verify_deps_before_run = 'false'
$dtHome = Join-Path $Root 'DeepTutor-runtime'
$dt = Join-Path $Root 'DeepTutor/.venv/Scripts/deeptutor.exe'
$dtPython = Join-Path $Root 'DeepTutor/.venv/Scripts/python.exe'
$om = Join-Path $Root 'OpenMAIC'
function Run-Native([string]$Exe,[string[]]$Params) {
  & $Exe @Params
  if($LASTEXITCODE -ne 0){throw "Command failed: $Exe (exit $LASTEXITCODE)"}
}
function Check-Tools {
  foreach($name in @('git','python','node','npm','pnpm')) {
    if(-not(Get-Command $name -ErrorAction SilentlyContinue)){throw "Missing $name. Install it from its official source, then reopen PowerShell."}
  }
  Run-Native python @('-c','import sys; assert (3,11)<=sys.version_info[:2]<(3,15), "Python 3.11-3.14 required"; print(sys.version.split()[0])')
  Run-Native node @('-e','const [a,b]=process.versions.node.split(".").map(Number); if(a<22||(a===22&&b<19))process.exit(1); console.log(process.version)')
  Run-Native pnpm @('--version')
  Run-Native git @('--version')
}
function Assert-PortFree([int]$Port) {
  if(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue){throw "Port $Port is occupied; no other program was stopped."}
}
function Get-DtOwned {
  $all = @(Get-CimInstance Win32_Process)
  $python = Join-Path $Root 'DeepTutor\.venv\Scripts\python.exe'
  $web = Join-Path $dtHome 'data\user\runtime\web\server.js'
  $sourceWeb = Join-Path $Root 'DeepTutor\web\.next-deeptutor\standalone\server.js'
  $parents = @($all | Where-Object {$_.CommandLine -and $_.CommandLine.Contains($python) -and $_.CommandLine.Contains('deeptutor.api.main:app')} | Select-Object -ExpandProperty ProcessId)
  @($all | Where-Object {$_.CommandLine -and (($_.CommandLine.Contains($python) -and $_.CommandLine.Contains('deeptutor.api.main:app')) -or ($_.CommandLine.Contains('deeptutor.api.main:app') -and $parents -contains $_.ParentProcessId) -or $_.CommandLine.Contains($web) -or $_.CommandLine.Contains($sourceWeb))})
}
function Install-Notes {
  $source = Join-Path $Root 'DeepTutor'
  Run-Native $dtPython @((Join-Path $PSScriptRoot 'prepare-notes.py'),'--source',$source)
  Run-Native $dtPython @('-m','pip','install','beautifulsoup4>=4.15.0,<5','markdown-it-py>=3,<5')
  Run-Native $dtPython @('-m','pip','install','-r',(Join-Path $source 'requirements-summary-notes.txt'))
  Run-Native $dtPython @('-m','pip','install','--no-deps','-e',$source)
  Push-Location (Join-Path $source 'web')
  try { Run-Native npm @('ci','--legacy-peer-deps','--no-audit','--no-fund') } finally { Pop-Location }
  Run-Native $dtPython @('-c','import shutil,sys; from pathlib import Path; from deeptutor.runtime.launcher import _ensure_source_production_build; _ensure_source_production_build(Path(sys.argv[1]),shutil.which("npm"),api_base="http://127.0.0.1:8001",auth_enabled=False)',(Join-Path $source 'web'))
}
function Install-One([string]$Name) {
  $dir = Join-Path $Root $Name
  if(Test-Path -LiteralPath $dir){throw "$Name already exists; reuse or update it manually. No overwrite performed."}
  if($Name -eq 'DeepTutor') {
    Run-Native git @('clone','--depth','1','--branch','v1.6.14','https://github.com/HKUDS/DeepTutor.git',$dir)
    Run-Native python @('-m','venv',(Join-Path $dir '.venv'))
    Run-Native $dtPython @('-m','pip','install','deeptutor==1.6.14')
    New-Item -ItemType Directory -Path $dtHome -Force | Out-Null
    Run-Native $dt @('init','--home',$dtHome,'--non-interactive')
    Run-Native $dtPython @((Join-Path $PSScriptRoot 'prepare.py'),'--root',$Root,'--project','DeepTutor')
    Install-Notes
  } else {
    Run-Native git @('clone','--depth','1','--branch','v1.1.4','https://github.com/THU-MAIC/OpenMAIC.git',$dir)
    Push-Location $dir
    try {
      Run-Native pnpm @('install','--frozen-lockfile')
      Copy-Item -LiteralPath '.env.example' -Destination '.env.local'
      Run-Native python @((Join-Path $PSScriptRoot 'prepare.py'),'--root',$Root,'--project','OpenMAIC')
      Run-Native npm @('run','build')
    } finally {Pop-Location}
  }
}
function Stop-One([string]$Name) {
  if($Name -eq 'DeepTutor') {
    & $dt stop --home $dtHome
    # Only recover children positively tied to this installation's path.
    foreach($p in @(Get-DtOwned)){Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue}
  } else {
    $file = Join-Path $Root 'logs/openmaic-process.json'
    if(Test-Path -LiteralPath $file){
      $saved = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
      $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($saved.pid)" -ErrorAction SilentlyContinue
      if($p -and $p.CommandLine.Contains($om) -and $p.CommandLine.Contains('next')){Stop-Process -Id $p.ProcessId}
    }
  }
}
function Start-One([string]$Name) {
  if($Name -eq 'DeepTutor') {
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In 3782,8001)
    if($listeners.Count){
      $owned = @(Get-DtOwned | Select-Object -ExpandProperty ProcessId)
      if(@($listeners | Where-Object {$owned -notcontains $_.OwningProcess}).Count){throw 'An unrecognized process occupies a DeepTutor port.'}
      if(@($listeners.LocalPort | Sort-Object -Unique).Count -eq 2 -and (Invoke-RestMethod 'http://127.0.0.1:8001/health/ready' -TimeoutSec 10).status -eq 'ready'){Write-Host 'DeepTutor already running.';return}
      throw 'Partial DeepTutor instance; use Restart.'
    }
    Run-Native $dt @('start','--home',$dtHome,'--detach','--no-browser')
  } else {
    Assert-PortFree 3001
    if(-not(Test-Path -LiteralPath (Join-Path $om '.next/BUILD_ID'))){throw 'OpenMAIC production build not found.'}
    $next = Join-Path $om 'node_modules/next/dist/bin/next'
    $p = Start-Process -FilePath (Get-Command node).Source -ArgumentList @(('"'+$next+'"'),'start','--hostname','127.0.0.1','--port','3001') -WorkingDirectory $om -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Root 'logs/openmaic.stdout.log') -RedirectStandardError (Join-Path $Root 'logs/openmaic.stderr.log') -PassThru
    @{pid=$p.Id;started=(Get-Date -Format o)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Root 'logs/openmaic-process.json')
  }
}
if($Action -eq 'Check') {
  Check-Tools
  foreach($port in @(3782,8001,3001)) {Write-Host "Port $port occupied: $([bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue))"}
  return
}
if($Action -eq 'DeepSeekPortal') {
  & (Join-Path $PSScriptRoot 'deepseek-shortcut.ps1') -Root $Root
  return
}
if($Action -eq 'CustomizeNotes') {
  Check-Tools
  Stop-One 'DeepTutor'
  Install-Notes
  Write-Host 'Notes customization built. Use Start to launch DeepTutor.'
  return
}
if($Action -eq 'Install'){Check-Tools}
foreach($dir in @($Root,(Join-Path $Root 'logs'),(Join-Path $Root 'backups'),(Join-Path $Root 'OpenMAIC-data/exports'))){New-Item -ItemType Directory -Path $dir -Force | Out-Null}
if($Action -eq 'Configure') {
  $secret = Read-Host 'Paste DeepSeek API key (hidden)' -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
  try {
    $env:LEARNING_DEEPSEEK_SETUP_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    Run-Native $dtPython @((Join-Path $PSScriptRoot 'configure.py'),'--root',$Root)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Item Env:LEARNING_DEEPSEEK_SETUP_KEY -ErrorAction SilentlyContinue
    $secret.Dispose()
  }
  Write-Host 'Saved without model requests. Restart services, then test only after approving API costs.'
  return
}
$names = if($Project -eq 'Both'){@('DeepTutor','OpenMAIC')}else{@($Project)}
foreach($name in $names){
  if($Action -eq 'Install'){Install-One $name}
  if($Action -In @('Stop','Restart')){Stop-One $name}
  if($Action -eq 'Restart'){Start-Sleep -Seconds 3}
  if($Action -In @('Start','Restart')){Start-One $name}
}
if($Action -eq 'Install') {
  & (Join-Path $PSScriptRoot 'deepseek-shortcut.ps1') -Root $Root
}
