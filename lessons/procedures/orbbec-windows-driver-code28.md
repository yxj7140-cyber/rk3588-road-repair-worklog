# Orbbec Windows Driver Code 28 Recovery

Date: 2026-06-26

## Symptom

OrbbecViewer can start, but the device dropdown keeps waiting for a device or only color is visible. Windows shows:

```text
ORBBEC Depth Sensor
USB\VID_2BC5&PID_0657\...
Problem Code: 28 [CM_PROB_FAILED_INSTALL]
```

In this state, `Dabai DC1` / color UVC may still be OK, but the depth sensor driver is not bound.

## Confirm Device State

Run in PowerShell:

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -match 'VID_2BC5|ORBBEC|Dabai' -or $_.FriendlyName -match 'ORBBEC|Orbbec|Dabai' } |
  Format-List Status,Class,FriendlyName,InstanceId,Problem,ConfigManagerErrorCode
```

Good state after recovery:

```text
ORBBEC Depth Sensor
Class: Orbbec
Status: OK
Driver Name from pnputil: oem*.inf
```

## Recovery That Worked

Use the signed installer from the extracted OrbbecViewer package, not the copied desktop exe and not an unsigned extracted duplicate.

Known good path:

```text
C:\OrbbecViewer_v1.10.27_202509252154_win_x64_release\driver\SensorDriver_V4.3.0.22.exe
```

Run it as administrator, then unplug/replug the camera.

After install, verify:

```powershell
pnputil /enum-devices /connected /instanceid "USB\VID_2BC5*"
```

Expected depth binding:

```text
Device Description: ORBBEC Depth Sensor
Class Name: Orbbec
Manufacturer Name: Orbbec Co., Ltd.
Status: Started
Driver Name: oem149.inf
```

`oem149.inf` on this machine matched `USB\VID_2BC5&PID_0657` and used driver version `4.3.0.22`.

## Smart App Control Note

Before this, Windows Smart App Control blocked `live555.dll`, causing OrbbecViewer startup errors. Turning Smart App Control off and rebooting fixed Viewer launch. Do not repeat this unless the same Code Integrity block appears.

## Viewer Launch Path

Use:

```text
C:\OrbbecViewer_v1.10.27_202509252154_win_x64_release\OrbbecViewer.exe
```

Avoid the desktop `OrbbecViewer.exe` copy. It may not run with the correct DLL working directory.

## Current Verified State

On 2026-06-26:

- `Dabai DC1 SN: CC13653019J USB2.0` appeared in OrbbecViewer.
- Color stream started successfully at `640x480 MJPG 30`.
- The checkerboard target was visible in the color image.
- Windows showed `ORBBEC Depth Sensor` as `Status: OK`.

## Important Follow-Ups

- Viewer currently reports `USB2.0`; this is acceptable for first-pass color checkerboard hand-eye capture, but depth bandwidth may be limited. Prefer a direct USB3 port/cable later.
- Depth stream still needs an explicit capture/verification step before using depth for crack/pothole 3D measurement.
- For hand-eye calibration, do not rely on Viewer UI alone. Save images and robot poses into the calibration session folder with matching sample names.
