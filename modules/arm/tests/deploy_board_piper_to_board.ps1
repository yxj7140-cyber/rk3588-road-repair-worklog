param(
    [string]$HostName = "192.168.1.1",
    [string]$User = "rock",
    [string]$IdentityFile = "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519",
    [string]$RemoteDir = "~/board_piper"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Archive = Join-Path $env:TEMP ("board_piper_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".zip")
$Remote = "${User}@${HostName}"

Write-Host "Packing board Piper files from: $ScriptDir"
if (Test-Path -LiteralPath $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}

$Include = @(
    "README.md",
    "requirements-board.txt",
    "setup_board_piper_env.sh",
    "install_board_piper_offline.sh",
    "check_board_piper_deps.sh",
    "detect_board_can.py",
    "check_board_can.sh",
    "check_board_can1.sh",
    "run_board_piper_probe_with_log.sh",
    "run_board_piper_motion_with_log.sh",
    "run_board_arm_task_with_log.sh",
    "run_board_piper_device_demo_with_log.sh",
    "run_board_mission_with_piper_arm_with_log.sh",
    "run_board_piper_micro_motion_with_log.sh",
    "road_repair_piper_arm.py",
    "road_repair_piper_device.py",
    "run_road_repair_arm_task.py",
    "run_road_repair_piper_device_demo.py",
    "run_road_repair_mission_with_piper_arm.py",
    "run_piper_probe.py",
    "run_piper_micro_motion.py",
    "run_piper_safe_motion.py",
    "road_repair_arm_control.py",
    "piper_motion_profiles.json"
)

$TempPack = Join-Path $env:TEMP ("board_piper_pack_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempPack | Out-Null
foreach ($Name in $Include) {
    Copy-Item -LiteralPath (Join-Path $ScriptDir $Name) -Destination (Join-Path $TempPack $Name) -Force
}
if (Test-Path -LiteralPath (Join-Path $ScriptDir "offline_pkgs")) {
    Copy-Item -LiteralPath (Join-Path $ScriptDir "offline_pkgs") -Destination (Join-Path $TempPack "offline_pkgs") -Recurse -Force
}
Compress-Archive -Path (Join-Path $TempPack "*") -DestinationPath $Archive -Force
Remove-Item -LiteralPath $TempPack -Recurse -Force

Write-Host "Checking board SSH: $Remote"
ssh -i $IdentityFile -o ConnectTimeout=5 -o StrictHostKeyChecking=no $Remote "mkdir -p $RemoteDir"

Write-Host "Uploading: $Archive"
scp -i $IdentityFile -o StrictHostKeyChecking=no $Archive "$User@$HostName`:~/board_piper_upload.zip"

Write-Host "Unpacking on board into: $RemoteDir"
ssh -i $IdentityFile -o StrictHostKeyChecking=no $Remote "rm -rf $RemoteDir && mkdir -p $RemoteDir && unzip -o ~/board_piper_upload.zip -d $RemoteDir >/dev/null && rm -f ~/board_piper_upload.zip && chmod +x $RemoteDir/*.sh"

Write-Host "Board Piper deployed to ${Remote}:$RemoteDir"
