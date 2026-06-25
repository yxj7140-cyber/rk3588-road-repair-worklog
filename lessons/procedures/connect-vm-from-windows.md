# Procedure: Connect To VMware Ubuntu VM From Windows

Use this when Codex needs to operate the Ubuntu VM through `vmrun`.

## Known VM Facts

- VMX path: `D:\robot\robot.vmx`
- VM user: `yx`
- VM password: `000000`
- VMware `vmrun.exe` path:

  ```powershell
  E:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe
  ```

## Check VM Is Running

```powershell
& 'E:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe' -T ws list
```

Expected:

```text
D:\robot\robot.vmx
```

## Run A Command In Guest

```powershell
& 'E:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe' `
  -T ws -gu yx -gp 000000 `
  runProgramInGuest 'D:\robot\robot.vmx' `
  /bin/bash -lc "hostname; whoami"
```

## Important Output Lesson

`vmrun runProgramInGuest` often does not return guest stdout clearly. Prefer:

1. Write guest command output to `/tmp/some_log.log`.
2. Copy it back:

```powershell
& 'E:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe' `
  -T ws -gu yx -gp 000000 `
  CopyFileFromGuestToHost 'D:\robot\robot.vmx' `
  /tmp/some_log.log `
  'E:\BaiduNetdiskDownload\rt\vm_logs\some_log.log'
```

## Do Not Repeat These Mistakes

- Do not rely on direct stdout from `vmrun`.
- Avoid complex nested quoting in one-liners. Put logic in a script under `scripts/vm-linux/`.
- If a process hangs on a large file or shared folder, inspect `ps`, `mount`, and logs before killing it.
