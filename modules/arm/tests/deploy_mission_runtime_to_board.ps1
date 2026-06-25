param(
    [string]$HostName = "10.11.198.140",
    [string]$User = "rock",
    [string]$IdentityFile = "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519",
    [string]$RemoteDir = "~/board_piper/mission_runtime"
)

$ErrorActionPreference = "Stop"

$BoardTools = "E:\BaiduNetdiskDownload\rt\board_tools"
$TempPack = Join-Path $env:TEMP ("mission_runtime_pack_" + [guid]::NewGuid().ToString("N"))
$Archive = Join-Path $env:TEMP ("mission_runtime_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".zip")
$Remote = "${User}@${HostName}"

$Include = @(
    "chassis_control.py",
    "chassis_vcmd_client.py",
    "road_repair_3508_model.py",
    "road_repair_competition_api.py",
    "road_repair_competition_behavior.py",
    "road_repair_competition_plan.py",
    "road_repair_competition_scenario.py",
    "road_repair_vcmd_adapter.py",
    "road_repair_virtual_devices.py",
    "road_repair_virtual_mission.py"
)

New-Item -ItemType Directory -Force -Path $TempPack | Out-Null
foreach ($Name in $Include) {
    Copy-Item -LiteralPath (Join-Path $BoardTools $Name) -Destination (Join-Path $TempPack $Name) -Force
}
Compress-Archive -Path (Join-Path $TempPack "*") -DestinationPath $Archive -Force
Remove-Item -LiteralPath $TempPack -Recurse -Force

Write-Host "Checking board SSH: $Remote"
ssh -i $IdentityFile -o ConnectTimeout=5 -o StrictHostKeyChecking=no $Remote "mkdir -p ~/board_piper"

Write-Host "Uploading mission runtime: $Archive"
scp -i $IdentityFile -o StrictHostKeyChecking=no $Archive "$User@$HostName`:~/mission_runtime_upload.zip"

Write-Host "Unpacking on board into: $RemoteDir"
ssh -i $IdentityFile -o StrictHostKeyChecking=no $Remote "rm -rf $RemoteDir && mkdir -p $RemoteDir && unzip -o ~/mission_runtime_upload.zip -d $RemoteDir >/dev/null && rm -f ~/mission_runtime_upload.zip"

Write-Host "Mission runtime deployed to ${Remote}:$RemoteDir"
