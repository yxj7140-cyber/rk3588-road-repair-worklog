# WT901C-TTL IMU Acceptance

This folder is for standalone IMU validation before connecting anything to the
RK3588 board. It intentionally stays separate from chassis, arm, and laser
radar work.

## Hardware

Recommended parts from the previous discussion:

- `WT901C-TTL` attitude sensor.
- `USB-TTL` serial adapter/cable.

Do not buy or use the RS232, RS485, CAN, or Bluetooth version for this path.

## Wiring

Check the labels on the physical module/cable before powering it.

Typical TTL wiring:

```text
WT901C-TTL VCC  -> USB-TTL 5V or 3V3, according to the module label/manual
WT901C-TTL GND  -> USB-TTL GND
WT901C-TTL TX   -> USB-TTL RX
WT901C-TTL RX   -> USB-TTL TX
```

Do not connect it to the RK3588 board yet.

## Windows Acceptance Steps

1. Plug only the USB-TTL adapter into the Windows PC.
2. Find the new COM port:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\imu_dev\list_serial_ports.ps1"
```

3. Install Python dependency if needed:

```powershell
cd "E:\BaiduNetdiskDownload\rt\imu_dev"
python -m pip install -r requirements-windows.txt
```

4. Connect the WT901C-TTL to the USB-TTL adapter.
5. Read data for 60 seconds:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\imu_dev\read_imu_with_log.ps1" -DurationS 60
```

If auto-detection fails, specify the COM port and baud rate:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\imu_dev\read_imu_with_log.ps1" -Port COM7 -Baud 9600 -DurationS 60
```

## What To Check

- Static yaw drift for 3-5 minutes.
- Whether yaw increases or decreases when rotating the sensor clockwise.
- Whether gyro_z changes sign consistently with yaw.
- Whether the output frequency is stable.
- Whether the mounting direction can be marked clearly on the chassis.

## Project Rule

IMU yaw calculation is validated on Windows/Linux first. RT-Thread does not
directly read this IMU at this stage.
