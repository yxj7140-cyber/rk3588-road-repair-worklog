$ErrorActionPreference = "Continue"

$Log = "E:\BaiduNetdiskDownload\rt\vm_logs\enable_windows_ics_to_ethernet.log"
"== $(Get-Date) Enable Windows ICS: WiFi to Ethernet ==" | Out-File -FilePath $Log -Encoding utf8

try {
    $share = New-Object -ComObject HNetCfg.HNetShare
    $connections = @($share.EnumEveryConnection())

    $publicNeedle = "Intel(R) Wi-Fi 6 AX203"
    $privateNeedle = "Intel(R) Ethernet Connection (23) I219-V"
    $publicConn = $null
    $privateConn = $null

    foreach ($conn in $connections) {
        $props = $share.NetConnectionProps($conn)
        "Found connection: name=[$($props.Name)] device=[$($props.DeviceName)]" |
            Add-Content -Path $Log -Encoding utf8

        if ($props.DeviceName -eq $publicNeedle) {
            $publicConn = $conn
            "Selected public connection: $($props.Name)" | Add-Content -Path $Log -Encoding utf8
        }
        if ($props.DeviceName -eq $privateNeedle) {
            $privateConn = $conn
            "Selected private connection: $($props.Name)" | Add-Content -Path $Log -Encoding utf8
        }
    }

    if ($null -eq $publicConn) {
        throw "Cannot find public connection device: $publicNeedle"
    }
    if ($null -eq $privateConn) {
        throw "Cannot find private connection device: $privateNeedle"
    }

    foreach ($conn in $connections) {
        $cfg = $share.INetSharingConfigurationForINetConnection($conn)
        if ($cfg.SharingEnabled) {
            $props = $share.NetConnectionProps($conn)
            "Disable existing sharing on $($props.Name)" | Add-Content -Path $Log -Encoding utf8
            $cfg.DisableSharing()
        }
    }

    $publicCfg = $share.INetSharingConfigurationForINetConnection($publicConn)
    $privateCfg = $share.INetSharingConfigurationForINetConnection($privateConn)

    # 0 = public/shared internet connection, 1 = private/home network connection.
    $publicCfg.EnableSharing(0)
    $privateCfg.EnableSharing(1)

    "ICS enabled: WiFi to Ethernet" | Add-Content -Path $Log -Encoding utf8
    Get-NetIPAddress -InterfaceIndex 14 -AddressFamily IPv4 |
        Select-Object InterfaceAlias, IPAddress, PrefixLength, AddressState, PrefixOrigin |
        Format-Table -AutoSize |
        Out-String |
        Add-Content -Path $Log -Encoding utf8
}
catch {
    "ERROR: $($_.Exception.Message)" | Add-Content -Path $Log -Encoding utf8
    exit 1
}
