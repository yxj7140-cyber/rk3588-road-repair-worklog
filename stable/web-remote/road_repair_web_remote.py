#!/usr/bin/env python3
"""Simple browser remote for the Road_Repair RK3588 chassis port.

This is a manual debugging tool, not part of the competition task logic. It
serves a small web page and forwards button/keyboard commands to the validated
VCMD path. The Linux CAN gateway defaults to safe-lock unless --enable-current
is explicitly supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from chassis_vcmd_client import ChassisVcmdClient, ChassisVelocityCommand
from road_repair_3508_model import ROAD_REPAIR_AXIS_DEADBAND, apply_axis_deadband
from road_repair_vcmd_adapter import clamp_float


DEFAULT_HOST = "0.0.0.0"
DEFAULT_WEB_PORT = 8080
DEFAULT_CURRENT_LIMIT = 1800
DEFAULT_MAX_SPEED_RPM = 2000
DEFAULT_MAX_STRAFE_RPM = 1500
DEFAULT_MAX_ROTATE_RPM = 1600
DEFAULT_FORWARD_LEFT_TURN_COMPENSATION = 0.0
DEFAULT_FEEDBACK_JSON = "/tmp/road_repair_web_remote_motor_feedback.json"
DEFAULT_FEEDBACK_JSON_PERIOD_S = 0.05
DEFAULT_STRAIGHT_ASSIST_ENABLED = True
DEFAULT_STRAIGHT_ASSIST_KP = 0.35
DEFAULT_STRAIGHT_ASSIST_TRIM_LIMIT = 0.08
DEFAULT_STRAIGHT_ASSIST_MAX_FEEDBACK_AGE_S = 0.30
DEFAULT_STRAIGHT_ASSIST_MIN_AXIS = 0.12
DEFAULT_STRAIGHT_ASSIST_MIN_RPM = 80.0
DEFAULT_STRAIGHT_ASSIST_IDLE_AXIS = 0.03
DEFAULT_RT_IP = "10.10.10.30"
DEFAULT_RT_IFACE = "enp255s5"
DEFAULT_REMOTE_PRIORITY_PERIOD_S = 0.01
DEFAULT_REMOTE_PRIORITY_HOLD_S = 0.35

MOTOR_IDS = (0x201, 0x202, 0x203, 0x204)
LEFT_MOTOR_IDS = (0x201, 0x202)
RIGHT_MOTOR_IDS = (0x203, 0x204)
FORWARD_SPEED_SIGNS = {
    0x201: 1.0,
    0x202: 1.0,
    0x203: -1.0,
    0x204: -1.0,
}


def _axis_to_rpm(value: float, max_rpm: int, deadband: float = ROAD_REPAIR_AXIS_DEADBAND) -> int:
    axis = apply_axis_deadband(clamp_float(value, -1.0, 1.0), deadband)
    max_rpm_abs = abs(int(max_rpm))
    return int(clamp_float(int(axis * max_rpm_abs), -max_rpm_abs, max_rpm_abs))


def _forward_left_turn_compensation(
    forward: float,
    compensation: float,
    deadband: float = ROAD_REPAIR_AXIS_DEADBAND,
) -> float:
    """Add a small left-yaw trim only while driving forward."""

    forward_axis = apply_axis_deadband(clamp_float(forward, -1.0, 1.0), deadband)
    if forward_axis <= 0.0:
        return 0.0
    return clamp_float(abs(float(compensation)), 0.0, 0.5)


def _feedback_motor_dict(feedback: dict[str, Any] | None, motor_id: int) -> dict[str, Any] | None:
    if not feedback:
        return None
    motors = feedback.get("motors")
    if not isinstance(motors, dict):
        return None
    return motors.get(f"0x{motor_id:03x}") or motors.get(str(motor_id))


def _signed_forward_rpm(feedback: dict[str, Any], motor_id: int) -> float | None:
    motor = _feedback_motor_dict(feedback, motor_id)
    if not motor:
        return None
    count = int(motor.get("count", 0) or 0)
    if count <= 0:
        return None
    speed = float(motor.get("speed_rpm", 0.0) or 0.0)
    return speed * FORWARD_SPEED_SIGNS[motor_id]


def _average_signed_forward_rpm(feedback: dict[str, Any], motor_ids: tuple[int, ...]) -> float | None:
    values = []
    for motor_id in motor_ids:
        speed = _signed_forward_rpm(feedback, motor_id)
        if speed is None:
            return None
        values.append(speed)
    if not values:
        return None
    return sum(values) / len(values)


def calculate_straight_assist(
    forward: float,
    strafe: float,
    rotate: float,
    feedback: dict[str, Any] | None,
    *,
    enabled: bool = DEFAULT_STRAIGHT_ASSIST_ENABLED,
    kp: float = DEFAULT_STRAIGHT_ASSIST_KP,
    trim_limit: float = DEFAULT_STRAIGHT_ASSIST_TRIM_LIMIT,
    max_feedback_age_s: float = DEFAULT_STRAIGHT_ASSIST_MAX_FEEDBACK_AGE_S,
    min_axis: float = DEFAULT_STRAIGHT_ASSIST_MIN_AXIS,
    min_rpm: float = DEFAULT_STRAIGHT_ASSIST_MIN_RPM,
    idle_axis: float = DEFAULT_STRAIGHT_ASSIST_IDLE_AXIS,
) -> dict[str, Any]:
    """Return a small rotate trim for straight forward/backward driving.

    Positive rotate means left turn in the user-facing VCMD convention. If the
    left-side forward speed is higher than the right side during a straight
    command, the chassis tends to yaw right, so the correction is positive.
    """

    disabled = {
        "enabled": bool(enabled),
        "active": False,
        "trim": 0.0,
        "reason": "disabled",
        "left_forward_rpm": None,
        "right_forward_rpm": None,
        "error_rpm": 0.0,
        "feedback_age_s": None,
    }
    if not enabled:
        return disabled

    forward_axis = apply_axis_deadband(clamp_float(forward, -1.0, 1.0))
    strafe_axis = clamp_float(strafe, -1.0, 1.0)
    rotate_axis = clamp_float(rotate, -1.0, 1.0)
    if abs(forward_axis) < max(0.0, float(min_axis)):
        disabled["reason"] = "forward_axis_too_small"
        return disabled
    if abs(strafe_axis) > max(0.0, float(idle_axis)):
        disabled["reason"] = "user_strafe_active"
        return disabled
    if abs(rotate_axis) > max(0.0, float(idle_axis)):
        disabled["reason"] = "user_rotate_active"
        return disabled
    if not feedback:
        disabled["reason"] = "no_feedback"
        return disabled

    feedback_age = None
    try:
        feedback_age = max(
            float(_feedback_motor_dict(feedback, motor_id).get("age_s"))
            for motor_id in MOTOR_IDS
            if _feedback_motor_dict(feedback, motor_id) is not None
        )
    except (TypeError, ValueError):
        feedback_age = None
    disabled["feedback_age_s"] = feedback_age
    if feedback_age is None or feedback_age > max(0.0, float(max_feedback_age_s)):
        disabled["reason"] = "feedback_stale"
        return disabled

    left_forward = _average_signed_forward_rpm(feedback, LEFT_MOTOR_IDS)
    right_forward = _average_signed_forward_rpm(feedback, RIGHT_MOTOR_IDS)
    disabled["left_forward_rpm"] = left_forward
    disabled["right_forward_rpm"] = right_forward
    if left_forward is None or right_forward is None:
        disabled["reason"] = "incomplete_feedback"
        return disabled

    direction = 1.0 if forward_axis >= 0.0 else -1.0
    left_motion = left_forward * direction
    right_motion = right_forward * direction
    speed_floor = abs(float(min_rpm))
    if max(abs(left_motion), abs(right_motion)) < speed_floor:
        disabled["reason"] = "feedback_rpm_too_small"
        return disabled

    error = left_motion - right_motion
    denominator = max(speed_floor, (abs(left_motion) + abs(right_motion)) / 2.0)
    raw_trim = float(kp) * error / denominator
    trim = clamp_float(raw_trim, -abs(float(trim_limit)), abs(float(trim_limit)))
    return {
        "enabled": True,
        "active": abs(trim) > 0.0005,
        "trim": trim,
        "reason": "active",
        "left_forward_rpm": left_forward,
        "right_forward_rpm": right_forward,
        "error_rpm": error,
        "feedback_age_s": feedback_age,
    }


def build_web_vcmd(
    forward: float,
    strafe: float,
    rotate: float,
    current_limit: int = DEFAULT_CURRENT_LIMIT,
    max_speed_rpm: int = DEFAULT_MAX_SPEED_RPM,
    max_strafe_rpm: int = DEFAULT_MAX_STRAFE_RPM,
    max_rotate_rpm: int = DEFAULT_MAX_ROTATE_RPM,
) -> ChassisVelocityCommand:
    """Build a web-remote-only VCMD with separate forward/strafe scaling."""

    return ChassisVelocityCommand(
        forward_rpm=_axis_to_rpm(forward, max_speed_rpm),
        strafe_rpm=_axis_to_rpm(strafe, max_strafe_rpm),
        rotate_rpm=_axis_to_rpm(rotate, max_rotate_rpm),
        current_limit=current_limit,
        enabled=True,
    )


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Road Repair Chassis Remote</title>
  <style>
    :root {
      --bg: #f3efe5;
      --panel: #fffaf0;
      --ink: #1d2a24;
      --muted: #657067;
      --accent: #d65f36;
      --accent-dark: #9b321c;
      --safe: #2f7d4f;
      --warn: #b42318;
      --line: #ddcfb7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 15% 20%, rgba(214,95,54,.18), transparent 28rem),
        radial-gradient(circle at 85% 10%, rgba(47,125,79,.16), transparent 22rem),
        linear-gradient(145deg, #f7f0df, var(--bg));
      display: grid;
      place-items: center;
      padding: 20px;
    }
    main {
      width: min(920px, 100%);
      background: color-mix(in srgb, var(--panel) 88%, white);
      border: 1px solid var(--line);
      border-radius: 28px;
      padding: 24px;
      box-shadow: 0 22px 70px rgba(43, 32, 15, .16);
    }
    h1 {
      margin: 0 0 6px;
      font-size: clamp(28px, 6vw, 56px);
      letter-spacing: -.04em;
      line-height: .95;
    }
    .sub {
      color: var(--muted);
      margin: 0 0 18px;
      font-size: 16px;
    }
    .status {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 18px;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: white;
      font-size: 14px;
    }
    .safe { color: var(--safe); }
    .danger { color: var(--warn); font-weight: 700; }
    .safety {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 18px 0;
    }
    .pad {
      display: grid;
      grid-template-columns: repeat(3, minmax(76px, 1fr));
      gap: 12px;
      max-width: 520px;
      margin: 18px auto;
    }
    button {
      min-height: 74px;
      border: 0;
      border-radius: 20px;
      background: var(--accent);
      color: white;
      font-size: 18px;
      font-weight: 700;
      box-shadow: inset 0 -5px 0 rgba(0,0,0,.18), 0 8px 18px rgba(155,50,28,.22);
      cursor: pointer;
      touch-action: none;
    }
    button:active, button.active {
      transform: translateY(2px);
      background: var(--accent-dark);
      box-shadow: inset 0 -2px 0 rgba(0,0,0,.2), 0 5px 12px rgba(155,50,28,.2);
    }
    button.stop {
      grid-column: 2;
      background: #24342d;
      box-shadow: inset 0 -5px 0 rgba(0,0,0,.2), 0 8px 18px rgba(36,52,45,.18);
    }
    button.secondary {
      background: var(--safe);
      box-shadow: inset 0 -5px 0 rgba(0,0,0,.18), 0 8px 18px rgba(47,125,79,.18);
    }
    button.dangerButton {
      background: var(--warn);
      box-shadow: inset 0 -5px 0 rgba(0,0,0,.18), 0 8px 18px rgba(180,35,24,.2);
    }
    button:disabled {
      cursor: not-allowed;
      opacity: .45;
      transform: none;
    }
    .controls {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
      max-width: 640px;
      margin: 12px auto 0;
      color: var(--muted);
    }
    input[type="range"] { width: 100%; accent-color: var(--accent); }
    pre {
      min-height: 92px;
      white-space: pre-wrap;
      background: #1f2b26;
      color: #eaf4ec;
      border-radius: 18px;
      padding: 14px;
      overflow: auto;
      font-size: 13px;
    }
    .hint {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    @media (max-width: 620px) {
      .safety { grid-template-columns: 1fr; }
      button { min-height: 66px; }
    }
  </style>
</head>
<body>
<main>
  <h1>Road Repair Remote</h1>
  <p class="sub">临时网页遥控器。键盘：W/S 前后，A/D 左右平移，Q/E 旋转，空格急停。</p>
  <div class="status">
    <span id="mode" class="pill">mode: loading</span>
    <span id="gateway" class="pill">gateway: loading</span>
    <span id="scale" class="pill">scale</span>
    <span id="last" class="pill">last command: none</span>
  </div>
  <div class="safety">
    <button class="dangerButton" id="enableCurrent">启用真实运动</button>
    <button class="secondary" id="safeLock">回到安全锁</button>
  </div>
  <div class="pad">
    <div></div>
    <button data-f="1">前进 W</button>
    <div></div>
    <button data-s="-1">左移 A</button>
    <button class="stop" id="stop">停止</button>
    <button data-s="1">右移 D</button>
    <button data-r="1">左转 Q</button>
    <button data-f="-1">后退 S</button>
    <button data-r="-1">右转 E</button>
  </div>
  <section class="controls">
    <label>速度强度 <b id="magText">0.40</b>
      <input id="mag" type="range" min="0.10" max="1.00" value="0.40" step="0.05">
    </label>
    <p class="hint">
      开机默认进入 safe-lock：网页和 RT/CAN 通路可用，但 Linux 网关把物理电流锁为 0。
      只有确认周围安全后，点击“启用真实运动”才会重启网关并允许非零电流。
      网页遥控是人工最高优先级入口：按键时会高频刷新 VCMD，松手、切锁或页面失焦都会停止。
      出现任何异常，先点“停止”，再点“回到安全锁”。
    </p>
    <pre id="log">ready</pre>
  </section>
</main>
<script>
const logEl = document.querySelector("#log");
const modeEl = document.querySelector("#mode");
const gatewayEl = document.querySelector("#gateway");
const scaleEl = document.querySelector("#scale");
const lastEl = document.querySelector("#last");
const mag = document.querySelector("#mag");
const magText = document.querySelector("#magText");
const enableCurrentBtn = document.querySelector("#enableCurrent");
const safeLockBtn = document.querySelector("#safeLock");
let activeTimer = null;
const activeInputs = new Map();
let currentStatus = null;
let commandInFlight = false;

function log(message) {
  const now = new Date().toLocaleTimeString();
  logEl.textContent = `[${now}] ${message}\\n` + logEl.textContent.slice(0, 1600);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function renderStatus(data) {
  currentStatus = data;
  modeEl.textContent = data.enable_current ? "真实运动已启用" : "安全锁";
  modeEl.className = data.enable_current ? "pill danger" : "pill safe";
  gatewayEl.textContent = data.gateway_alive ? `gateway pid ${data.gateway_pid}` : "gateway offline";
  gatewayEl.className = data.gateway_alive ? "pill safe" : "pill danger";
  const fb = data.feedback_available ? "fb ok" : "fb wait";
  const assist = data.straight_assist_enabled ? `straight assist on kp=${data.straight_assist_kp}` : "straight assist off";
  scaleEl.textContent = `forward ${data.max_speed_rpm} rpm, strafe ${data.max_strafe_rpm} rpm, rotate ${data.max_rotate_rpm} rpm, fixed trim ${data.forward_left_turn_compensation}, ${assist}, ${fb}`;
  enableCurrentBtn.disabled = Boolean(data.enable_current);
  safeLockBtn.disabled = !data.enable_current;
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();
  renderStatus(data);
}

function clampAxis(value) {
  return Math.max(-1, Math.min(1, value));
}

function commandFromActiveInputs() {
  const m = Number(mag.value);
  let forward = 0;
  let strafe = 0;
  let rotate = 0;
  for (const btn of activeInputs.values()) {
    forward += Number(btn.dataset.f || 0);
    strafe += Number(btn.dataset.s || 0);
    rotate += Number(btn.dataset.r || 0);
  }
  return {
    forward: clampAxis(forward) * m,
    strafe: clampAxis(strafe) * m,
    rotate: clampAxis(rotate) * m
  };
}

async function sendCommand(command) {
  const data = await api("/api/drive", command);
  lastEl.textContent = `rpm ${data.forward_rpm},${data.strafe_rpm},${data.rotate_rpm}`;
  const assist = data.straight_assist || {};
  const assistText = `assist=${Number(assist.trim || 0).toFixed(3)} ${assist.reason || "none"}`;
  const sideText = assist.left_forward_rpm == null
    ? ""
    : ` L=${Number(assist.left_forward_rpm).toFixed(0)} R=${Number(assist.right_forward_rpm).toFixed(0)}`;
  log(`${data.mode} axes=${data.forward.toFixed(2)},${data.strafe.toFixed(2)},${data.rotate.toFixed(2)} fixed=${data.rotate_compensation.toFixed(2)} ${assistText}${sideText} rpm=${data.forward_rpm},${data.strafe_rpm},${data.rotate_rpm}`);
}

function sendActiveCommand() {
  if (activeInputs.size === 0) return;
  if (commandInFlight) return;
  commandInFlight = true;
  sendCommand(commandFromActiveInputs())
    .catch(err => log(`ERROR ${err.message}`))
    .finally(() => { commandInFlight = false; });
}

function ensureActiveTimer() {
  if (activeTimer) clearInterval(activeTimer);
  sendActiveCommand();
  activeTimer = setInterval(sendActiveCommand, 50);
}

function startHold(key, btn) {
  activeInputs.set(key, btn);
  btn.classList.add("active");
  ensureActiveTimer();
}

async function stopHold(key = null, sendStop = true) {
  if (key !== null) {
    const btn = activeInputs.get(key);
    if (btn) btn.classList.remove("active");
    activeInputs.delete(key);
  } else {
    for (const btn of activeInputs.values()) {
      btn.classList.remove("active");
    }
    activeInputs.clear();
  }

  if (activeInputs.size > 0) {
    ensureActiveTimer();
    return;
  }

  if (activeTimer) clearInterval(activeTimer);
  activeTimer = null;
  if (sendStop) {
    try {
      const data = await api("/api/stop", {});
      lastEl.textContent = "stopped";
      log(`${data.mode} stop`);
    } catch (err) {
      log(`ERROR ${err.message}`);
    }
  }
}

async function setSafetyMode(enable) {
  await stopHold(null, true);
  const promptText = enable
    ? "确认周围安全，并启用真实运动？"
    : "回到安全锁？这会先停止电机并锁定物理电流。";
  if (!window.confirm(promptText)) return;
  enableCurrentBtn.disabled = true;
  safeLockBtn.disabled = true;
  try {
    const data = await api(enable ? "/api/enable_current" : "/api/safe_lock", {});
    renderStatus(data);
    log(enable ? "真实运动模式已启用" : "已回到安全锁");
  } catch (err) {
    log(`ERROR ${err.message}`);
    await refreshStatus().catch(statusErr => log(`status error ${statusErr.message}`));
  }
}

document.querySelectorAll("button[data-f],button[data-s],button[data-r]").forEach(btn => {
  btn.addEventListener("pointerdown", event => {
    event.preventDefault();
    btn.setPointerCapture?.(event.pointerId);
    startHold(`pointer:${event.pointerId}`, btn);
  });
  btn.addEventListener("pointerup", event => stopHold(`pointer:${event.pointerId}`, true));
  btn.addEventListener("pointercancel", event => stopHold(`pointer:${event.pointerId}`, true));
  btn.addEventListener("lostpointercapture", event => stopHold(`pointer:${event.pointerId}`, true));
});
document.querySelector("#stop").addEventListener("click", () => stopHold(null, true));
enableCurrentBtn.addEventListener("click", () => setSafetyMode(true));
safeLockBtn.addEventListener("click", () => setSafetyMode(false));
mag.addEventListener("input", () => { magText.textContent = Number(mag.value).toFixed(2); });

const keyMap = {
  "w": "[data-f='1']",
  "s": "[data-f='-1']",
  "a": "[data-s='-1']",
  "d": "[data-s='1']",
  "q": "[data-r='1']",
  "e": "[data-r='-1']"
};
window.addEventListener("keydown", event => {
  if (event.repeat) return;
  if (event.code === "Space") {
    event.preventDefault();
    stopHold(null, true);
    return;
  }
  const selector = keyMap[event.key.toLowerCase()];
  if (selector) {
    event.preventDefault();
    startHold(`key:${event.key.toLowerCase()}`, document.querySelector(selector));
  }
});
window.addEventListener("keyup", event => {
  if (event.code === "Space") {
    stopHold(null, true);
    return;
  }
  if (keyMap[event.key.toLowerCase()]) stopHold(`key:${event.key.toLowerCase()}`, true);
});
window.addEventListener("blur", () => stopHold(null, true));
setInterval(() => refreshStatus().catch(err => log(`status error ${err.message}`)), 3000);
refreshStatus().catch(err => log(`status error ${err.message}`));
</script>
</body>
</html>
"""


class WebRemote:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = ChassisVcmdClient(args.target, args.vcmd_port)
        self.gateway_process: subprocess.Popen[bytes] | None = None
        self.gateway_log_handle = None
        self.enable_current = bool(args.enable_current)
        self.lock = threading.RLock()
        self.gateway_started_at: float | None = None
        self.gateway_restart_count = 0
        self.last_manual_command_at = 0.0

    def mode_name(self) -> str:
        return "current-enabled" if self.enable_current else "safe-lock"

    def start_gateway(self, enable_current: bool | None = None) -> None:
        with self.lock:
            if enable_current is not None:
                self.enable_current = bool(enable_current)
            self._start_gateway_locked()

    def _start_gateway_locked(self) -> None:
        if self.args.no_gateway:
            return

        self._stop_gateway_locked()

        gateway = Path(__file__).with_name("can_gateway_service.py")
        command = [
            sys.executable,
            str(gateway),
            "--iface",
            "can0",
            "--setup-can",
            "--no-shm",
            "--udp",
            "--udp-bind",
            "0.0.0.0",
            "--udp-port",
            "15550",
            "--udp-command-timeout",
            "0.25",
            "--require-rt-ping",
            self.args.rt_ip,
            "--rt-ping-iface",
            self.args.rt_iface,
            "--rt-ping-timeout",
            str(self.args.rt_ping_timeout),
            "--require-udp-peer-timeout",
            str(self.args.udp_peer_timeout),
            "--send-before-feedback",
            "--feedback-json",
            self.args.feedback_json,
            "--feedback-json-period",
            str(self.args.feedback_json_period_s),
            "--log-period",
            "0.2",
        ]
        if self.enable_current:
            command.extend(["--allow-nonzero-current", "--i-understand-this-can-move-motors"])

        log_path = Path(self.args.gateway_log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.gateway_log_handle = log_path.open("ab")
        self.gateway_log_handle.write(
            f"\n=== web remote gateway start mode={self.mode_name()} "
            f"restart={self.gateway_restart_count} ===\n".encode()
        )
        self.gateway_log_handle.flush()
        wrapped = self._sudo_wrap(command)
        self.gateway_process = subprocess.Popen(
            wrapped,
            stdin=subprocess.PIPE if self._needs_sudo_password(wrapped) else None,
            stdout=self.gateway_log_handle,
            stderr=subprocess.STDOUT,
        )
        if self.gateway_process.stdin is not None:
            password = os.environ.get("SUDO_PASSWORD", "")
            self.gateway_process.stdin.write((password + "\n").encode())
            self.gateway_process.stdin.flush()
            self.gateway_process.stdin.close()
        time.sleep(max(0.0, self.args.gateway_warmup_s))
        if self.gateway_process.poll() is not None:
            raise RuntimeError(
                f"CAN gateway exited during startup with status {self.gateway_process.returncode}; "
                f"see {log_path}"
            )
        self.gateway_started_at = time.time()
        self.gateway_restart_count += 1

    def _stop_gateway_locked(self) -> None:
        if self.gateway_process is not None:
            self.gateway_process.terminate()
            try:
                self.gateway_process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.gateway_process.kill()
                self.gateway_process.wait(timeout=2.0)
            self.gateway_process = None
        if self.gateway_log_handle is not None:
            self.gateway_log_handle.close()
            self.gateway_log_handle = None
        self.gateway_started_at = None

    def _sudo_wrap(self, command: list[str]) -> list[str]:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return command
        if os.environ.get("SUDO_PASSWORD"):
            return ["sudo", "-S", *command]
        return ["sudo", *command]

    def _needs_sudo_password(self, command: list[str]) -> bool:
        return len(command) >= 2 and command[0] == "sudo" and command[1] == "-S"

    def send_axis(self, forward: float, strafe: float, rotate: float) -> dict[str, Any]:
        with self.lock:
            self._ensure_gateway_alive_locked()
            forward_axis = clamp_float(forward, -1.0, 1.0)
            strafe_axis = clamp_float(strafe, -1.0, 1.0)
            rotate_axis = clamp_float(rotate, -1.0, 1.0)
            feedback = self._read_feedback_locked()
            straight_assist = calculate_straight_assist(
                forward_axis,
                strafe_axis,
                rotate_axis,
                feedback,
                enabled=self.args.straight_assist,
                kp=self.args.straight_assist_kp,
                trim_limit=self.args.straight_assist_trim_limit,
                max_feedback_age_s=self.args.straight_assist_max_feedback_age_s,
                min_axis=self.args.straight_assist_min_axis,
                min_rpm=self.args.straight_assist_min_rpm,
                idle_axis=self.args.straight_assist_idle_axis,
            )
            rotate_compensation = _forward_left_turn_compensation(
                forward_axis,
                self.args.forward_left_turn_compensation,
            )
            compensated_rotate_axis = clamp_float(
                rotate_axis + rotate_compensation + float(straight_assist["trim"]),
                -1.0,
                1.0,
            )
            vcmd = build_web_vcmd(
                forward=forward_axis,
                strafe=strafe_axis,
                rotate=compensated_rotate_axis,
                current_limit=self.args.current_limit,
                max_speed_rpm=self.args.max_speed_rpm,
                max_strafe_rpm=self.args.max_strafe_rpm,
                max_rotate_rpm=self.args.max_rotate_rpm,
            )
            self.client.send(vcmd)
            time.sleep(max(0.0, float(self.args.remote_priority_period_s)))
            self.client.send(vcmd)
            self.last_manual_command_at = time.time()
            return {
                "ok": True,
                "mode": self.mode_name(),
                "enable_current": self.enable_current,
                "manual_priority": True,
                "forward": forward_axis,
                "strafe": strafe_axis,
                "rotate": rotate_axis,
                "rotate_compensation": rotate_compensation,
                "straight_assist": straight_assist,
                "compensated_rotate": compensated_rotate_axis,
                "forward_rpm": vcmd.forward_rpm,
                "strafe_rpm": vcmd.strafe_rpm,
                "rotate_rpm": vcmd.rotate_rpm,
                "current_limit": vcmd.current_limit,
            }

    def _read_feedback_locked(self) -> dict[str, Any] | None:
        path = Path(self.args.feedback_json)
        if not path.exists():
            return None
        try:
            feedback = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(feedback, dict):
            return None
        file_time = feedback.get("time")
        try:
            file_age_s = max(0.0, time.time() - float(file_time))
        except (TypeError, ValueError):
            file_age_s = None
        feedback["file_age_s"] = file_age_s
        motors = feedback.get("motors")
        if file_age_s is not None and isinstance(motors, dict):
            for motor in motors.values():
                if not isinstance(motor, dict):
                    continue
                try:
                    age = motor.get("age_s")
                    motor["age_s"] = None if age is None else float(age) + file_age_s
                except (TypeError, ValueError):
                    motor["age_s"] = None
        return feedback

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self.client.stop(period_s=self.args.period)
            return {
                "ok": True,
                "mode": self.mode_name(),
                "enable_current": self.enable_current,
            }

    def set_current_enabled(self, enable: bool) -> dict[str, Any]:
        with self.lock:
            self.client.stop(period_s=self.args.period)
            self.enable_current = bool(enable)
            self._start_gateway_locked()
            self.client.stop(period_s=self.args.period)
            return self.status()

    def status(self) -> dict[str, Any]:
        with self.lock:
            gateway_alive = self.gateway_process is not None and self.gateway_process.poll() is None
            feedback = self._read_feedback_locked()
            return {
                "ok": gateway_alive or self.args.no_gateway,
                "mode": self.mode_name(),
                "enable_current": self.enable_current,
                "target": self.args.target,
                "vcmd_port": self.args.vcmd_port,
                "current_limit": self.args.current_limit,
                "max_speed_rpm": self.args.max_speed_rpm,
                "max_strafe_rpm": self.args.max_strafe_rpm,
                "max_rotate_rpm": self.args.max_rotate_rpm,
                "forward_left_turn_compensation": self.args.forward_left_turn_compensation,
                "straight_assist_enabled": self.args.straight_assist,
                "straight_assist_kp": self.args.straight_assist_kp,
                "straight_assist_trim_limit": self.args.straight_assist_trim_limit,
                "feedback_json": self.args.feedback_json,
                "feedback_available": feedback is not None,
                "feedback": feedback,
                "remote_priority_active": time.time() - self.last_manual_command_at < self.args.remote_priority_hold_s,
                "remote_priority_period_s": self.args.remote_priority_period_s,
                "gateway_pid": self.gateway_process.pid if self.gateway_process else None,
                "gateway_alive": gateway_alive,
                "gateway_started_at": self.gateway_started_at,
                "gateway_restart_count": self.gateway_restart_count,
            }

    def _ensure_gateway_alive_locked(self) -> None:
        if self.args.no_gateway:
            return
        if self.gateway_process is None:
            raise RuntimeError("CAN gateway is not running")
        if self.gateway_process.poll() is not None:
            raise RuntimeError(
                f"CAN gateway exited with status {self.gateway_process.returncode}; "
                "use the safety toggle or restart the service"
            )

    def close(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
        self.client.close()
        with self.lock:
            self._stop_gateway_locked()
        self._cleanup_can()

    def _cleanup_can(self) -> None:
        command = self._sudo_wrap(["ip", "link", "set", "can0", "down"])
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE if self._needs_sudo_password(command) else None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin is not None:
                process.stdin.write((os.environ.get("SUDO_PASSWORD", "") + "\n").encode())
                process.stdin.flush()
                process.stdin.close()
            process.wait(timeout=2.0)
        except Exception:
            pass


class RemoteRequestHandler(BaseHTTPRequestHandler):
    remote: WebRemote

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/index.html"):
            self._send_bytes(HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/status"):
            self._send_json(self.remote.status())
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            if self.path.startswith("/api/drive"):
                self._send_json(
                    self.remote.send_axis(
                        forward=float(payload.get("forward", 0.0)),
                        strafe=float(payload.get("strafe", 0.0)),
                        rotate=float(payload.get("rotate", 0.0)),
                    )
                )
                return
            if self.path.startswith("/api/stop"):
                self._send_json(self.remote.stop())
                return
            if self.path.startswith("/api/enable_current"):
                self._send_json(self.remote.set_current_enabled(True))
                return
            if self.path.startswith("/api/safe_lock"):
                self._send_json(self.remote.set_current_enabled(False))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0") or "0")
        if size <= 0:
            return {}
        raw = self.rfile.read(size)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a simple Road_Repair browser remote.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--web-port", type=int, default=DEFAULT_WEB_PORT)
    parser.add_argument("--target", default=DEFAULT_RT_IP)
    parser.add_argument("--vcmd-port", type=int, default=15551)
    parser.add_argument("--period", type=float, default=0.02)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CURRENT_LIMIT)
    parser.add_argument("--max-speed-rpm", type=int, default=DEFAULT_MAX_SPEED_RPM)
    parser.add_argument("--max-strafe-rpm", type=int, default=DEFAULT_MAX_STRAFE_RPM)
    parser.add_argument("--max-rotate-rpm", type=int, default=DEFAULT_MAX_ROTATE_RPM)
    parser.add_argument(
        "--forward-left-turn-compensation",
        type=float,
        default=DEFAULT_FORWARD_LEFT_TURN_COMPENSATION,
    )
    parser.add_argument("--feedback-json", default=DEFAULT_FEEDBACK_JSON)
    parser.add_argument("--feedback-json-period-s", type=float, default=DEFAULT_FEEDBACK_JSON_PERIOD_S)
    parser.add_argument(
        "--straight-assist",
        dest="straight_assist",
        action="store_true",
        default=DEFAULT_STRAIGHT_ASSIST_ENABLED,
    )
    parser.add_argument("--no-straight-assist", dest="straight_assist", action="store_false")
    parser.add_argument("--straight-assist-kp", type=float, default=DEFAULT_STRAIGHT_ASSIST_KP)
    parser.add_argument("--straight-assist-trim-limit", type=float, default=DEFAULT_STRAIGHT_ASSIST_TRIM_LIMIT)
    parser.add_argument(
        "--straight-assist-max-feedback-age-s",
        type=float,
        default=DEFAULT_STRAIGHT_ASSIST_MAX_FEEDBACK_AGE_S,
    )
    parser.add_argument("--straight-assist-min-axis", type=float, default=DEFAULT_STRAIGHT_ASSIST_MIN_AXIS)
    parser.add_argument("--straight-assist-min-rpm", type=float, default=DEFAULT_STRAIGHT_ASSIST_MIN_RPM)
    parser.add_argument("--straight-assist-idle-axis", type=float, default=DEFAULT_STRAIGHT_ASSIST_IDLE_AXIS)
    parser.add_argument("--remote-priority-period-s", type=float, default=DEFAULT_REMOTE_PRIORITY_PERIOD_S)
    parser.add_argument("--remote-priority-hold-s", type=float, default=DEFAULT_REMOTE_PRIORITY_HOLD_S)
    parser.add_argument("--rt-ip", default=DEFAULT_RT_IP)
    parser.add_argument("--rt-iface", default=DEFAULT_RT_IFACE)
    parser.add_argument("--rt-ping-timeout", type=float, default=20.0)
    parser.add_argument("--udp-peer-timeout", type=float, default=20.0)
    parser.add_argument("--gateway-warmup-s", type=float, default=3.0)
    parser.add_argument("--gateway-log", default="/tmp/road_repair_web_remote_gateway.log")
    parser.add_argument("--enable-current", action="store_true")
    parser.add_argument("--no-gateway", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def self_test() -> int:
    assert "Road Repair Remote" in HTML_PAGE
    assert "/api/drive" in HTML_PAGE
    assert "/api/enable_current" in HTML_PAGE
    assert "/api/safe_lock" in HTML_PAGE
    assert "straight assist" in HTML_PAGE
    assert "rotate_compensation" in HTML_PAGE
    axis = build_web_vcmd(
        forward=0.4,
        strafe=0.0,
        rotate=0.0,
        current_limit=DEFAULT_CURRENT_LIMIT,
        max_speed_rpm=DEFAULT_MAX_SPEED_RPM,
        max_strafe_rpm=DEFAULT_MAX_STRAFE_RPM,
        max_rotate_rpm=DEFAULT_MAX_ROTATE_RPM,
    )
    assert axis.forward_rpm == 800
    assert axis.current_limit == DEFAULT_CURRENT_LIMIT
    assert _forward_left_turn_compensation(0.4, DEFAULT_FORWARD_LEFT_TURN_COMPENSATION) == DEFAULT_FORWARD_LEFT_TURN_COMPENSATION
    assert _forward_left_turn_compensation(-0.4, DEFAULT_FORWARD_LEFT_TURN_COMPENSATION) == 0.0
    sample_feedback = {
        "motors": {
            "0x201": {"speed_rpm": 220, "count": 10, "age_s": 0.01},
            "0x202": {"speed_rpm": 200, "count": 10, "age_s": 0.01},
            "0x203": {"speed_rpm": -120, "count": 10, "age_s": 0.01},
            "0x204": {"speed_rpm": -140, "count": 10, "age_s": 0.01},
        }
    }
    assist = calculate_straight_assist(0.4, 0.0, 0.0, sample_feedback)
    assert assist["active"]
    assert assist["trim"] > 0.0
    assert assist["reason"] == "active"
    assert calculate_straight_assist(0.4, 0.2, 0.0, sample_feedback)["reason"] == "user_strafe_active"
    assert calculate_straight_assist(0.4, 0.0, 0.2, sample_feedback)["reason"] == "user_rotate_active"
    stale_feedback = {
        "motors": {
            "0x201": {"speed_rpm": 220, "count": 10, "age_s": 1.0},
            "0x202": {"speed_rpm": 200, "count": 10, "age_s": 1.0},
            "0x203": {"speed_rpm": -120, "count": 10, "age_s": 1.0},
            "0x204": {"speed_rpm": -140, "count": 10, "age_s": 1.0},
        }
    }
    assert calculate_straight_assist(0.4, 0.0, 0.0, stale_feedback)["reason"] == "feedback_stale"
    print("PASS road_repair_web_remote self-test")
    return 0


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.self_test:
        return self_test()

    remote = WebRemote(args)
    RemoteRequestHandler.remote = remote
    server = ThreadingHTTPServer((args.host, args.web_port), RemoteRequestHandler)

    def handle_signal(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        remote.start_gateway()
        print(
            f"road_repair_web_remote listening http://{args.host}:{args.web_port} "
            f"mode={remote.mode_name()} max_speed_rpm={args.max_speed_rpm} "
            f"max_strafe_rpm={args.max_strafe_rpm} "
            f"max_rotate_rpm={args.max_rotate_rpm} "
            f"forward_left_turn_compensation={args.forward_left_turn_compensation}",
            flush=True,
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        remote.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
