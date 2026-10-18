param(
  [Parameter(Mandatory=$true)][string]$Root,
  [ValidateSet('Start','Stop','Restart','Check','Shortcuts')][string]$Action='Check',
  [ValidateSet('DeepTutor','OpenMAIC','Both')][string]$Project='Both',
  [string]$Node,
  [string]$ShortcutDirectory = [Environment]::GetFolderPath('Desktop'),
  [switch]$Open
)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root)
$repo=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot))
if($Root -eq $repo -or $Root.StartsWith($repo+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Installation root must be outside this repository.'}
$python=Join-Path $Root 'DeepTutor/.venv/Scripts/python.exe'
$pythonw=Join-Path $Root 'DeepTutor/.venv/Scripts/pythonw.exe'
if(-not(Test-Path -LiteralPath $python)){throw 'Existing DeepTutor Python environment is required.'}
$env:LEARNING_SYSTEMS_ROOT=$Root
$env:PYTHONUTF8='1'
if($Node){$env:LEARNING_SYSTEMS_NODE=[IO.Path]::GetFullPath($Node)}
$runtime=Join-Path $PSScriptRoot 'windows-runtime'
if($Action -ne 'Shortcuts'){
  $arguments=@('-X','utf8',(Join-Path $runtime 'services.py'),'--action',$Action,'--project',$Project)
  if($Open){$arguments+='--open'}
  & $python @arguments
  if($LASTEXITCODE -ne 0){throw 'Runtime operation failed; inspect installation logs.'}
  exit
}
if(-not(Test-Path -LiteralPath $ShortcutDirectory -PathType Container)){throw 'Shortcut directory must already exist.'}
# Keep launchers independent of the checkout location and preserve old shortcuts.
$deploy=Join-Path $Root 'launcher'
$backup=Join-Path $Root ('backups/launcher-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $deploy,$backup -Force | Out-Null
foreach($file in @('services.py','launch-ui.py')){
  $target=Join-Path $deploy $file
  if(Test-Path -LiteralPath $target){Copy-Item -LiteralPath $target -Destination $backup}
  Copy-Item -LiteralPath (Join-Path $runtime $file) -Destination $target -Force
}
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class LearningIcon { [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr hIcon); }'
$icons=Join-Path $Root 'shortcut-icons'
New-Item -ItemType Directory -Path $icons -Force | Out-Null
$wsh=New-Object -ComObject WScript.Shell
foreach($name in @('DeepTutor','OpenMAIC')){
  if($Project -ne 'Both' -and $Project -ne $name){continue}
  # Official artwork from the installed upstream source; no generated substitute.
  $source=if($name -eq 'DeepTutor'){Join-Path $Root 'DeepTutor/web/public/apple-touch-icon.png'}else{Join-Path $Root 'OpenMAIC/app/apple-icon.png'}
  $iconPath=Join-Path $icons ($name+'.ico')
  $bitmap=[Drawing.Bitmap]::new($source)
  $handle=$bitmap.GetHicon()
  $icon=[Drawing.Icon]::FromHandle($handle)
  try {
    $stream=[IO.File]::Create($iconPath)
    try{$icon.Save($stream)}finally{$stream.Dispose()}
  } finally {$icon.Dispose();[LearningIcon]::DestroyIcon($handle)|Out-Null;$bitmap.Dispose()}
  $title=if($name -eq 'DeepTutor'){'DeepTutor 学习助手.lnk'}else{'OpenMAIC 学习课堂.lnk'}
  $path=Join-Path $ShortcutDirectory $title
  if(Test-Path -LiteralPath $path){Copy-Item -LiteralPath $path -Destination $backup}
  $link=$wsh.CreateShortcut($path)
  $link.TargetPath=$pythonw
  $link.Arguments='"'+(Join-Path $deploy 'launch-ui.py')+'" --root "'+$Root+'" --project '+$name
  $link.WorkingDirectory=$Root
  $link.IconLocation=$iconPath+',0'
  $link.Save()
}
Write-Host 'Official icons and console-free shortcuts created. Existing launchers were backed up.'
