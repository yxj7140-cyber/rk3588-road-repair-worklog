param(
    [string]$BoardIp = "192.168.137.152",
    [string]$Key = "",
    [string]$KnownHosts = "",
    [string]$BoardPassword = "rock",
    [string]$VersionName = "20260615_chassis_control_current_combo_lifted",
    [int]$CurrentLimit = 1200,
    [double]$Period = 0.02,
    [int]$GatewaySeconds = 18,
    [int]$MaxSpeedRpm = 0,
    [int]$MaxRotateRpm = 0,
    [string]$ScenarioFile = "",
    [string[]]$MissionArg = @(),
    [switch]$EnableCurrent
)

$ErrorActionPreference = "Stop"

$ToolsDir = $PSScriptRoot
$Root = Split-Path -Parent $ToolsDir
if (-not $Key) {
    $Key = Join-Path $Root "board_ssh\rock5b_ed25519"
}
if (-not $KnownHosts) {
    $KnownHosts = Join-Path $Root "board_ssh\codex_wireless_known_hosts"
}

$Board = "rock@$BoardIp"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RemoteDir = "/tmp/rr_virtual_mission_$Stamp"
$ArchiveDir = Join-Path $Root "rk3588_migration\versions\$VersionName\logs"
$ModeName = if ($EnableCurrent) { "current_lifted" } else { "safelock" }
$DryRunLog = Join-Path $ArchiveDir "virtual_mission_dryrun_$Stamp.txt"
$StdoutLog = Join-Path $ArchiveDir "virtual_mission_${ModeName}_stdout_$Stamp.txt"
$CleanupLog = Join-Path $ArchiveDir "virtual_mission_cleanup_$Stamp.txt"

New-Item -ItemType Directory -Force $ArchiveDir | Out-Null

$Files = @(
    "can_gateway_service.py",
    "chassis_vcmd_client.py",
    "road_repair_3508_model.py",
    "road_repair_vcmd_adapter.py",
    "chassis_control.py",
    "road_repair_competition_behavior.py",
    "road_repair_competition_plan.py",
    "road_repair_competition_api.py",
    "road_repair_competition_scenario.py",
    "road_repair_virtual_devices.py",
    "road_repair_virtual_mission.py",
    "sample_road_repair_scenario.json",
    "run_road_repair_virtual_mission_test.sh"
) | ForEach-Object { Join-Path $ToolsDir $_ }

if ($ScenarioFile) {
    if ([System.IO.Path]::IsPathRooted($ScenarioFile)) {
        $ScenarioPath = $ScenarioFile
    }
    else {
        $ScenarioPath = Join-Path $ToolsDir $ScenarioFile
    }
    if (-not (Test-Path $ScenarioPath)) {
        throw "Missing scenario file: $ScenarioPath"
    }
    $Files += $ScenarioPath
}

$SshOptions = @(
    "-i", $Key,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=$KnownHosts"
)

foreach ($File in $Files) {
    if (-not (Test-Path $File)) {
        throw "Missing required file: $File"
    }
}

Write-Host "Board: $Board"
Write-Host "Remote temp dir: $RemoteDir"
Write-Host "Archive dir: $ArchiveDir"
Write-Host "Mode: $ModeName"
if ($MaxSpeedRpm -gt 0 -or $MaxRotateRpm -gt 0) {
    Write-Host "Scale: max_speed_rpm=$MaxSpeedRpm max_rotate_rpm=$MaxRotateRpm"
}

$EffectiveMissionArg = @($MissionArg)
if ($ScenarioFile) {
    $ScenarioBaseName = Split-Path -Leaf $ScenarioPath
    $EffectiveMissionArg += "--scenario-file"
    $EffectiveMissionArg += $ScenarioBaseName
}
if ($MaxSpeedRpm -gt 0) {
    $EffectiveMissionArg += "--max-speed-rpm"
    $EffectiveMissionArg += "$MaxSpeedRpm"
}
if ($MaxRotateRpm -gt 0) {
    $EffectiveMissionArg += "--max-rotate-rpm"
    $EffectiveMissionArg += "$MaxRotateRpm"
}

try {
    ssh @SshOptions $Board "rm -rf $RemoteDir; mkdir -p $RemoteDir/logs"
    scp @SshOptions @Files "${Board}:$RemoteDir/"

    $DryRunArgs = @("--dry-run", "--current-limit $CurrentLimit")
    foreach ($Arg in $EffectiveMissionArg) {
        $DryRunArgs += $Arg
    }
    $DryRunCmd = "cd $RemoteDir && python3 ./road_repair_virtual_mission.py $($DryRunArgs -join ' ')"
    ssh @SshOptions $Board $DryRunCmd 2>&1 |
        Tee-Object -FilePath $DryRunLog

    $RunArgs = @(
        "--current-limit $CurrentLimit",
        "--period $Period",
        "--gateway-seconds $GatewaySeconds",
        "--log-prefix virtual_mission_${ModeName}_$Stamp"
    )
    if ($EnableCurrent) {
        $RunArgs += "--enable-current"
    }
    foreach ($Arg in $EffectiveMissionArg) {
        $RunArgs += "--mission-arg $Arg"
    }

    $RunCmd = "cd $RemoteDir && chmod +x ./run_road_repair_virtual_mission_test.sh && LOG_DIR=$RemoteDir/logs SUDO_PASSWORD=$BoardPassword bash ./run_road_repair_virtual_mission_test.sh $($RunArgs -join ' ')"
    ssh @SshOptions $Board $RunCmd 2>&1 |
        Tee-Object -FilePath $StdoutLog

    scp @SshOptions "${Board}:$RemoteDir/logs/*" "$ArchiveDir\"

    $Analyzer = Join-Path $ToolsDir "analyze_can_gateway_log.ps1"
    if (Test-Path $Analyzer) {
        $RunLogs = Get-ChildItem -Path $ArchiveDir -Filter "virtual_mission_${ModeName}_${Stamp}_*.log" -File
        foreach ($RunLog in $RunLogs) {
            $AnalysisLog = Join-Path $ArchiveDir "$($RunLog.BaseName)_analysis.txt"
            & $Analyzer -LogPath $RunLog.FullName -OutFile $AnalysisLog
            Write-Host "Analysis log: $AnalysisLog"
        }
    }
}
finally {
    $CleanupCmd = "set +e; echo $BoardPassword | sudo -S systemctl stop can-gateway.service >/dev/null 2>&1; echo $BoardPassword | sudo -S pkill -f '[c]an_gateway_service.py' >/dev/null 2>&1; echo $BoardPassword | sudo -S ip link set can0 down >/dev/null 2>&1; case '$RemoteDir' in /tmp/rr_virtual_mission_*) echo $BoardPassword | sudo -S /bin/rm -rf -- '$RemoteDir' ;; *) echo 'refuse cleanup: unexpected remote dir $RemoteDir' ;; esac; systemctl is-active can-gateway.service || true; ip -br link show can0 || true; pgrep -af '[c]an_gateway_service.py|[r]oad_repair_virtual' || true; ls -d /tmp/rr_virtual_mission_* 2>/dev/null || true"
    ssh @SshOptions $Board $CleanupCmd 2>&1 |
        Tee-Object -FilePath $CleanupLog
}

Write-Host "Dry-run log: $DryRunLog"
Write-Host "Stdout log:  $StdoutLog"
Write-Host "Cleanup log: $CleanupLog"
