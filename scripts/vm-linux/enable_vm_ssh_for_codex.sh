#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/mnt/hgfs/rt/vm_logs"
PUBKEY_FILE="/mnt/hgfs/rt/board_ssh/rock5b_ed25519.pub"
LOG_FILE="$LOG_DIR/enable_vm_ssh_for_codex.log"

mkdir -p "$LOG_DIR"
exec > >(tee "$LOG_FILE") 2>&1

echo "== Enable SSH access for Codex from Windows host =="
date

if [ ! -f "$PUBKEY_FILE" ]; then
    echo "Missing public key: $PUBKEY_FILE"
    exit 1
fi

echo "== Install public key for current VM user: $USER =="
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"

PUBKEY="$(cat "$PUBKEY_FILE")"
if grep -qxF "$PUBKEY" "$HOME/.ssh/authorized_keys"; then
    echo "Public key already exists in authorized_keys"
else
    printf '%s\n' "$PUBKEY" >> "$HOME/.ssh/authorized_keys"
    echo "Public key appended"
fi

echo "== Ensure OpenSSH server is installed =="
if command -v sshd >/dev/null 2>&1; then
    echo "openssh-server already installed"
else
    sudo apt update
    sudo apt install -y openssh-server
fi

echo "== Start SSH service =="
if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable ssh
    sudo systemctl restart ssh
else
    sudo service ssh restart
fi

echo "== Network addresses =="
hostname -I || true

echo "== SSH listening check =="
if command -v ss >/dev/null 2>&1; then
    ss -ltn | grep ':22' || true
else
    netstat -ltn | grep ':22' || true
fi

echo "== Done =="
echo "Log: $LOG_FILE"
