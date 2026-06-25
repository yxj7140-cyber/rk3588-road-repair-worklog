param(
    [Parameter(Mandatory = $true)]
    [string]$LogPath,
    [string]$OutFile = "",
    [int]$AngleThreshold = 50,
    [int]$RpmThreshold = 20,
    [int]$HighCurrentThreshold = 1000
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $LogPath)) {
    throw "Log file not found: $LogPath"
}

function Get-AbsInt([int]$Value) {
    return [Math]::Abs($Value)
}

function Get-WrappedAngleDelta([int]$Previous, [int]$Current) {
    $Delta = $Current - $Previous
    if ($Delta -gt 4096) {
        $Delta -= 8192
    }
    elseif ($Delta -lt -4096) {
        $Delta += 8192
    }
    return $Delta
}

function New-MotorStats([string]$MotorId) {
    return [ordered]@{
        MotorId = $MotorId
        Samples = 0
        FirstAngle = $null
        LastAngle = $null
        CumAngleDelta = 0
        MaxAbsRpm = 0
        MaxAbsFeedbackCurrent = 0
        NonzeroRpmSamples = 0
        HighFeedbackCurrentSamples = 0
    }
}

$MotorIds = @("201", "202", "203", "204")
$MotorStats = @{}
foreach ($MotorId in $MotorIds) {
    $MotorStats[$MotorId] = New-MotorStats $MotorId
}

$ReqMaxAbs = @(0, 0, 0, 0)
$ReqNonzeroLines = 0
$ReqHighLines = 0
$TxEnobufsMax = 0
$TxEnobufsNonzeroLines = 0
$LineCount = 0
$RtPeerDetected = $false
$FinalZeroCurrent = $false
$NonzeroCurrentEnabled = $false

$MotorPattern = '(?<id>20[1-4]):cnt=(?<cnt>\d+)\s+angle=(?<angle>-?\d+)\s+rpm=(?<rpm>-?\d+)\s+cur=(?<cur>-?\d+)'
$ReqPattern = 'req=(?<req>-?\d+,-?\d+,-?\d+,-?\d+)'
$TxPattern = 'tx_enobufs=(?<tx>\d+)'

foreach ($Line in Get-Content -Path $LogPath) {
    $LineCount += 1

    if ($Line -match 'RT UDP peer detected') {
        $RtPeerDetected = $true
    }
    if ($Line -match 'final zero-current frame sent') {
        $FinalZeroCurrent = $true
    }
    if ($Line -match 'non-zero current output is enabled') {
        $NonzeroCurrentEnabled = $true
    }

    if ($Line -match $ReqPattern) {
        $Parts = $Matches.req.Split(',') | ForEach-Object { [int]$_ }
        $LineHasNonzeroReq = $false
        $LineHasHighReq = $false
        for ($Index = 0; $Index -lt 4; $Index++) {
            $AbsReq = Get-AbsInt $Parts[$Index]
            if ($AbsReq -gt $ReqMaxAbs[$Index]) {
                $ReqMaxAbs[$Index] = $AbsReq
            }
            if ($AbsReq -gt 0) {
                $LineHasNonzeroReq = $true
            }
            if ($AbsReq -ge $HighCurrentThreshold) {
                $LineHasHighReq = $true
            }
        }
        if ($LineHasNonzeroReq) {
            $ReqNonzeroLines += 1
        }
        if ($LineHasHighReq) {
            $ReqHighLines += 1
        }
    }

    if ($Line -match $TxPattern) {
        $Tx = [int]$Matches.tx
        if ($Tx -gt $TxEnobufsMax) {
            $TxEnobufsMax = $Tx
        }
        if ($Tx -gt 0) {
            $TxEnobufsNonzeroLines += 1
        }
    }

    $MatchesInLine = [regex]::Matches($Line, $MotorPattern)
    foreach ($Match in $MatchesInLine) {
        $MotorId = $Match.Groups["id"].Value
        $Angle = [int]$Match.Groups["angle"].Value
        $Rpm = [int]$Match.Groups["rpm"].Value
        $Current = [int]$Match.Groups["cur"].Value
        $Stats = $MotorStats[$MotorId]

        if ($Stats.Samples -eq 0) {
            $Stats.FirstAngle = $Angle
        }
        else {
            $Stats.CumAngleDelta += Get-WrappedAngleDelta $Stats.LastAngle $Angle
        }

        $Stats.LastAngle = $Angle
        $Stats.Samples += 1

        $AbsRpm = Get-AbsInt $Rpm
        if ($AbsRpm -gt $Stats.MaxAbsRpm) {
            $Stats.MaxAbsRpm = $AbsRpm
        }
        if ($AbsRpm -ge $RpmThreshold) {
            $Stats.NonzeroRpmSamples += 1
        }

        $AbsCurrent = Get-AbsInt $Current
        if ($AbsCurrent -gt $Stats.MaxAbsFeedbackCurrent) {
            $Stats.MaxAbsFeedbackCurrent = $AbsCurrent
        }
        if ($AbsCurrent -ge $HighCurrentThreshold) {
            $Stats.HighFeedbackCurrentSamples += 1
        }
    }
}

$Output = New-Object System.Collections.Generic.List[string]
$Output.Add("Log: $LogPath")
$Output.Add("lines=$LineCount rt_peer_detected=$RtPeerDetected nonzero_current_enabled=$NonzeroCurrentEnabled final_zero_current=$FinalZeroCurrent")
$Output.Add("tx_enobufs max=$TxEnobufsMax nonzero_lines=$TxEnobufsNonzeroLines")
$Output.Add("request max_abs_req=$([Math]::Max([Math]::Max($ReqMaxAbs[0], $ReqMaxAbs[1]), [Math]::Max($ReqMaxAbs[2], $ReqMaxAbs[3]))) per_motor=$($ReqMaxAbs -join ',') nonzero_lines=$ReqNonzeroLines high_lines_ge_$HighCurrentThreshold=$ReqHighLines")

$MovedCount = 0
foreach ($MotorId in $MotorIds) {
    $Stats = $MotorStats[$MotorId]
    $Moved = ($Stats.Samples -gt 0) -and ((Get-AbsInt $Stats.CumAngleDelta) -ge $AngleThreshold -or $Stats.MaxAbsRpm -ge $RpmThreshold)
    if ($Moved) {
        $MovedCount += 1
    }
    $Output.Add(
        ("motor{0}: samples={1} angle_delta={2} first_angle={3} last_angle={4} max_abs_rpm={5} rpm_samples_ge_{6}={7} max_abs_cur={8} cur_samples_ge_{9}={10} moved={11}" -f
            $MotorId,
            $Stats.Samples,
            $Stats.CumAngleDelta,
            $Stats.FirstAngle,
            $Stats.LastAngle,
            $Stats.MaxAbsRpm,
            $RpmThreshold,
            $Stats.NonzeroRpmSamples,
            $Stats.MaxAbsFeedbackCurrent,
            $HighCurrentThreshold,
            $Stats.HighFeedbackCurrentSamples,
            $Moved
        )
    )
}

$AllMotorsMoved = ($MovedCount -eq 4)
$CommunicationOk = $RtPeerDetected -and ($TxEnobufsNonzeroLines -eq 0)
$Output.Add("motion_summary moved_motors=$MovedCount/4 all_motors_moved=$AllMotorsMoved")
$Output.Add("communication_summary ok=$CommunicationOk")

if ($OutFile) {
    $Parent = Split-Path -Parent $OutFile
    if ($Parent) {
        New-Item -ItemType Directory -Force $Parent | Out-Null
    }
    $Output | Out-File -FilePath $OutFile -Encoding utf8
}

$Output | ForEach-Object { Write-Host $_ }
