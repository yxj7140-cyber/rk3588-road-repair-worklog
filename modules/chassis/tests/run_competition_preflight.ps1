param(
    [string]$BoardIp = "192.168.137.152",
    [string]$Key = "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519",
    [string]$BoardPassword = "rock",
    [switch]$StartGateway,
    [switch]$TailLog
)

$ErrorActionPreference = "Stop"

$remoteArgs = @()
if ($StartGateway) {
    $remoteArgs += "--start-gateway"
}
if ($TailLog) {
    $remoteArgs += "--tail-log"
}

$remoteCommand = "SUDO_PASSWORD='$BoardPassword' bash /home/rock/images/competition_preflight.sh $($remoteArgs -join ' ')"

Write-Host "Board: rock@$BoardIp"
Write-Host "Remote: $remoteCommand"
ssh -i $Key -o StrictHostKeyChecking=no rock@$BoardIp $remoteCommand
