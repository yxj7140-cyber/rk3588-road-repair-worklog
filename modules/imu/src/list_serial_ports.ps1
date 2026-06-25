param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "Windows serial ports from WMI:"
Get-CimInstance Win32_SerialPort |
    Select-Object DeviceID, Name, PNPDeviceID |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Serial port names from .NET:"
[System.IO.Ports.SerialPort]::getportnames()

Write-Host ""
Write-Host "If pyserial is installed, list detailed ports:"
$script = @'
try:
    from serial.tools import list_ports
except Exception as exc:
    print(f"pyserial unavailable: {exc}")
else:
    for port in list_ports.comports():
        print(f"{port.device}\t{port.description}\t{port.hwid}")
'@
$script | & $Python -
