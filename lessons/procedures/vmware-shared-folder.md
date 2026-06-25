# Procedure: VMware Shared Folder

Use this when `/mnt/hgfs/rt` is missing after VM reboot.

## Expected Shared Path

- Windows path: `E:\BaiduNetdiskDownload\rt`
- VM path: `/mnt/hgfs/rt`

## Check Shared Folder

```bash
ls /mnt/hgfs
vmware-hgfsclient
```

Expected client output includes:

```text
rt
```

## Remount

```bash
sudo mkdir -p /mnt/hgfs
sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
ls /mnt/hgfs/rt
```

## Lessons

- After VM reboot, `/mnt/hgfs` can be empty even though VMware shared folder is configured.
- If `vmware-hgfsclient` lists `rt`, the share exists; remount it.
- Keep logs under `/mnt/hgfs/rt/vm_logs` so Windows and Codex can read them.
- Large image processing over `/mnt/hgfs` can be slow or hang on checksums. Prefer copying large images to VM local disk, processing there, then copying results back.

## Safe Pattern For VM Scripts

```bash
LOG=/tmp/my_task.log
exec >"$LOG" 2>&1
# work here
```

Then copy `/tmp/my_task.log` back to Windows.
