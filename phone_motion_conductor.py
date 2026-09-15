"""
===============================================================================
SMARTPHONE MOTION CONDUCTOR & AIR DRUM ENGINE (DUAL WEB + NATIVE OSC HUB)
===============================================================================
Description:
    Transforms your smartphone into a high-frequency physical air drumstick
    and orchestral motion controller with zero latency:

      - 💥 Forward Punch -> +G Forward Thrust -> Epic 808 Sub-Bass Boom (Ch 1/2/3)
      - 🥁 Downward Hammer -> Vertical Impact G-Force -> Heavy Snare / Low Tom
      - 🌟 Overhead Whip -> High-Speed Angular Gyro Spin -> Massive Crash Cymbal
      - 🎻 Pitch Tilt (Up/Down) -> Arm Altitude -> String Chords + BGM Swell (CC11 / OSC)
      - 🌊 Roll Tilt (Left/Right) -> Wingspan -> Reverb Depth & Width (CC91)

    Supports 2 Connection Modes:
      1. Web App Mode: Open http://<PC-IP>:8080 on your phone (Safari / Chrome).
      2. Native Sensor App Mode: Use free app (Phyphox, Sensors2OSC, ZIG SIM, TouchOSC)
         streaming UDP OSC directly to port 5005.

Usage:
    .venv\\Scripts\\python.exe phone_motion_conductor.py
===============================================================================
"""

import sys
import os
import time
import math
import socket
import struct
import json
import threading
import argparse
import random
import mido
from http.server import HTTPServer, BaseHTTPRequestHandler
import qrcode
import io

# Ensure UTF-8 output encoding for Windows terminal
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# =============================================================================
# MARKOV STATE DEFINITIONS & CHORD PROGRESSIONS
# =============================================================================
STATE_CALM    = "CALM_ATMOSPHERE"
STATE_TENSION = "BUILDING_TENSION"
STATE_CLIMAX  = "CLIMAX_DREAD"
STATE_RELEASE = "RELEASE_DECAY"

CHORD_PROGRESSIONS = {
    STATE_CALM: [
        [50, 57, 62, 65],        # Dm
        [46, 53, 58, 65],        # Bb
        [43, 50, 55, 62],        # Gm
        [45, 52, 57, 64],        # Am
    ],
    STATE_TENSION: [
        [50, 57, 62, 65, 69],    # Dm9
        [46, 53, 58, 62, 65],    # Bbmaj7
        [41, 48, 53, 60, 65],    # Fmaj
        [45, 52, 57, 61, 64],    # A7
    ],
    STATE_CLIMAX: [
        [38, 50, 57, 62, 65, 69, 74],  # Dm tutti
        [34, 46, 53, 58, 62, 65, 70],  # Bb full brass
        [36, 48, 55, 60, 64, 67, 72],  # C major
        [33, 45, 52, 57, 61, 64, 69],  # A7
    ],
    STATE_RELEASE: [
        [38, 50, 62, 65],        # Dm soft
        [46, 53, 62],            # Bb sparse
        [43, 55, 62],            # Gm sparse
    ]
}

# =============================================================================
# OSC ENCODING / DECODING
# =============================================================================
class OSCMessageBuilder:
    @staticmethod
    def build_float_msg(address, value):
        addr_bytes = address.encode('utf-8') + b'\x00'
        while len(addr_bytes) % 4 != 0:
            addr_bytes += b'\x00'
        type_tags = b',f\x00\x00'
        val_bytes = struct.pack('>f', float(value))
        return addr_bytes + type_tags + val_bytes

def parse_osc_packet(data):
    """Decodes OSC packet from native phone sensor apps."""
    try:
        null_idx = data.find(b'\x00')
        if null_idx == -1:
            return None, []
        address = data[:null_idx].decode('utf-8', errors='ignore')
        pad_offset = (null_idx + 4) & ~3
        if pad_offset >= len(data) or data[pad_offset:pad_offset+1] != b',':
            return address, []

        type_tag_end = data.find(b'\x00', pad_offset)
        if type_tag_end == -1:
            return address, []

        type_tags = data[pad_offset+1:type_tag_end].decode('ascii', errors='ignore')
        val_offset = (type_tag_end + 4) & ~3

        args = []
        for tag in type_tags:
            if tag == 'f':
                if val_offset + 4 <= len(data):
                    val = struct.unpack('>f', data[val_offset:val_offset+4])[0]
                    args.append(val)
                    val_offset += 4
            elif tag == 'i':
                if val_offset + 4 <= len(data):
                    val = struct.unpack('>i', data[val_offset:val_offset+4])[0]
                    args.append(val)
                    val_offset += 4
            elif tag == 'd':
                if val_offset + 8 <= len(data):
                    val = struct.unpack('>d', data[val_offset:val_offset+8])[0]
                    args.append(float(val))
                    val_offset += 8
        return address, args
    except Exception:
        return None, []

# =============================================================================
# HTML5 CYBERPUNK MOBILE WEB APP (HTTP DIRECT MODE)
# =============================================================================
HTML_MOBILE_APP = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Air Band Motion Drumstick</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; -webkit-user-select: none; }
    body {
      background: radial-gradient(circle at center, #181528 0%, #08070d 100%);
      color: #e0e6ed;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 14px;
    }
    .header { text-align: center; }
    h1 { font-size: 20px; font-weight: 800; letter-spacing: 1px; color: #00f0ff; text-shadow: 0 0 12px rgba(0,240,255,0.4); }
    .status-badge {
      display: inline-block;
      margin-top: 4px;
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
      background: #1e1b33;
      border: 1px solid #00ff88;
      color: #00ff88;
      box-shadow: 0 0 10px rgba(0,255,136,0.2);
    }
    
    .sensor-panel {
      background: rgba(22, 20, 38, 0.85);
      border: 1px solid #2f2a4f;
      border-radius: 16px;
      padding: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    }
    .metric-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; }
    .bar-bg { width: 50%; height: 10px; background: #121020; border-radius: 5px; overflow: hidden; border: 1px solid #2a2545; }
    .bar-fill { height: 100%; width: 0%; border-radius: 5px; transition: width 0.05s ease-out; }
    .fill-acc { background: linear-gradient(90deg, #00f0ff, #ff0055); }
    .fill-pitch { background: linear-gradient(90deg, #00ff88, #ffaa00); }
    .fill-roll { background: linear-gradient(90deg, #b000ff, #00f0ff); }
    .raw-debug { font-size: 11px; color: #00f0ff; text-align: center; margin-top: 4px; font-family: monospace; }
    
    .hit-display {
      height: 70px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 16px;
      font-size: 22px;
      font-weight: 900;
      letter-spacing: 1px;
      background: rgba(15, 12, 28, 0.9);
      border: 2px solid #2f2a4f;
      color: #ffffff;
      transition: background 0.1s, border-color 0.1s, transform 0.05s;
    }
    .hit-display.active {
      background: #ff0055 !important;
      border-color: #ffffff !important;
      color: #ffffff !important;
      box-shadow: 0 0 35px #ff0055;
      transform: scale(1.04);
    }

    .pads-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .pad-btn {
      background: #1b1730;
      border: 1px solid #3c3460;
      color: #fff;
      padding: 18px 8px;
      border-radius: 14px;
      font-size: 14px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      touch-action: manipulation;
    }
    .pad-btn:active { transform: scale(0.96); background: #ff0055; border-color: #fff; box-shadow: 0 0 20px #ff0055; }
    .pad-btn span { font-size: 20px; font-weight: 900; color: #00f0ff; }

    .start-btn {
      width: 100%;
      background: linear-gradient(135deg, #00f0ff 0%, #0088ff 100%);
      color: #000;
      border: none;
      padding: 16px;
      border-radius: 14px;
      font-size: 16px;
      font-weight: 900;
      letter-spacing: 0.5px;
      box-shadow: 0 4px 20px rgba(0,240,255,0.4);
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>AIR BAND DRUMSTICK</h1>
    <div id="statusBadge" class="status-badge">CONNECTED & ACTIVE</div>
  </div>

  <div class="sensor-panel">
    <div class="metric-row">
      <span>G-FORCE IMPULSE</span>
      <div class="bar-bg"><div id="barG" class="bar-fill fill-acc"></div></div>
      <span id="txtG">0.0G</span>
    </div>
    <div class="metric-row">
      <span>PITCH (ELEVATION)</span>
      <div class="bar-bg"><div id="barPitch" class="bar-fill fill-pitch"></div></div>
      <span id="txtPitch">0&deg;</span>
    </div>
    <div class="metric-row">
      <span>ROLL (REVERB)</span>
      <div class="bar-bg"><div id="barRoll" class="bar-fill fill-roll"></div></div>
      <span id="txtRoll">0&deg;</span>
    </div>
    <div id="rawDebug" class="raw-debug">Sensors: Initializing...</div>
  </div>

  <div id="hitBox" class="hit-display">TAP PADS OR SWING</div>

  <div class="pads-grid">
    <button class="pad-btn" onpointerdown="sendManualHit('punch', 1.0)"><span>[BOOM]</span>808 KICK</button>
    <button class="pad-btn" onpointerdown="sendManualHit('snare', 1.0)"><span>[SNARE]</span>SNARE DRUM</button>
    <button class="pad-btn" onpointerdown="sendManualHit('tom', 1.0)"><span>[TOM]</span>LOW TOM</button>
    <button class="pad-btn" onpointerdown="sendManualHit('crash', 1.0)"><span>[CRASH]</span>CYMBAL</button>
  </div>

  <button id="startBtn" class="start-btn" onclick="startMotionStream()">ACTIVATE MOTION SENSORS</button>

  <script>
    let lastPitch = 0, lastRoll = 0;
    let lastHttpSend = 0;
    let samplesCount = 0;

    function triggerHitUI(label) {
      const box = document.getElementById('hitBox');
      box.textContent = label;
      box.classList.add('active');
      setTimeout(() => box.classList.remove('active'), 140);
    }

    function sendManualHit(hitType, vel) {
      const payload = { type: 'manual_hit', hit: hitType, vel: vel };
      
      fetch('/api/hit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).catch(() => {});

      triggerHitUI(hitType.toUpperCase() + ' HIT');
      if (navigator.vibrate) navigator.vibrate(50);
    }

    function sendMotionData(data) {
      const now = Date.now();
      if (now - lastHttpSend > 35) { // 30Hz stream
        lastHttpSend = now;
        fetch('/api/motion', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }).catch(() => {});
      }
    }

    async function startMotionStream() {
      document.getElementById('startBtn').style.display = 'none';

      if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
        try { await DeviceOrientationEvent.requestPermission(); } catch (e) {}
      }
      if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
        try { await DeviceMotionEvent.requestPermission(); } catch (e) {}
      }

      window.addEventListener('deviceorientation', (e) => {
        lastPitch = e.beta || 0;
        lastRoll = e.gamma || 0;
        document.getElementById('txtPitch').textContent = Math.round(lastPitch) + '°';
        document.getElementById('txtRoll').textContent = Math.round(lastRoll) + '°';
        document.getElementById('barPitch').style.width = Math.min(Math.max((lastPitch + 45) / 90 * 100, 0), 100) + '%';
        document.getElementById('barRoll').style.width = Math.min(Math.max((lastRoll + 45) / 90 * 100, 0), 100) + '%';
      }, true);

      window.addEventListener('devicemotion', (e) => {
        samplesCount++;
        const acc = e.accelerationIncludingGravity || e.acceleration || {x:0, y:0, z:0};
        const rot = e.rotationRate || {alpha:0, beta:0, gamma:0};
        
        const ax = acc.x || 0;
        const ay = acc.y || 0;
        const az = acc.z || 0;
        const gMag = Math.sqrt(ax*ax + ay*ay + az*az) / 9.81;

        document.getElementById('txtG').textContent = gMag.toFixed(1) + 'G';
        document.getElementById('barG').style.width = Math.min((gMag / 4.0) * 100, 100) + '%';
        document.getElementById('rawDebug').textContent = `X:${ax.toFixed(1)} Y:${ay.toFixed(1)} Z:${az.toFixed(1)} (#${samplesCount})`;

        sendMotionData({
          type: 'motion',
          ax: ax,
          ay: ay,
          az: az,
          gx: rot.alpha || 0,
          gy: rot.beta || 0,
          gz: rot.gamma || 0,
          pitch: lastPitch,
          roll: lastRoll,
          gMag: gMag
        });
      }, true);
    }
  </script>
</body>
</html>
"""

# Global conductor reference
GLOBAL_CONDUCTOR = None

class MobileAppHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(HTML_MOBILE_APP.encode('utf-8'))

    def do_POST(self):
        global GLOBAL_CONDUCTOR
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        if GLOBAL_CONDUCTOR:
            try:
                data = json.loads(post_data.decode('utf-8'))
                if self.path == '/api/hit' or data.get('type') == 'manual_hit':
                    hit = data.get('hit')
                    vel = int(data.get('vel', 1.0) * 127)
                    if hit == 'punch':
                        GLOBAL_CONDUCTOR.trigger_epic_hit("808 PUNCH BOOM", kick_note=36, bass_note=48, chord_root=60, vel=vel)
                    elif hit == 'snare':
                        GLOBAL_CONDUCTOR.trigger_epic_hit("HAMMER SNARE", kick_note=38, bass_note=62, chord_root=65, vel=vel)
                    elif hit == 'tom':
                        GLOBAL_CONDUCTOR.trigger_epic_hit("HAMMER TOM", kick_note=45, bass_note=57, chord_root=60, vel=vel)
                    elif hit == 'crash':
                        GLOBAL_CONDUCTOR.trigger_epic_hit("CRASH CYMBAL", kick_note=49, bass_note=72, chord_root=76, vel=vel)

                elif self.path == '/api/motion' or data.get('type') == 'motion':
                    GLOBAL_CONDUCTOR.process_imu_sample(
                        ax=data.get('ax', 0),
                        ay=data.get('ay', 0),
                        az=data.get('az', 0),
                        gx=data.get('gx', 0),
                        gy=data.get('gy', 0),
                        gz=data.get('gz', 0),
                        pitch=data.get('pitch', 0),
                        roll=data.get('roll', 0),
                        g_mag=data.get('gMag', 1.0)
                    )
            except Exception:
                pass

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass

def start_http_server(host, port):
    server = HTTPServer((host, port), MobileAppHTTPHandler)
    server.serve_forever()

# =============================================================================
# SMARTPHONE IMU MOTION CONDUCTOR HUB
# =============================================================================
class PhoneMotionConductor:
    def __init__(self, reaper_ip, reaper_port, midi_port_name="GestureConductor", sensitivity=1.0):
        self.reaper_ip = reaper_ip
        self.reaper_port = reaper_port
        self.sensitivity = sensitivity
        self.osc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Smart MIDI resolution
        available = mido.get_output_names()
        print(f"[CONDUCTOR] Detected available MIDI ports: {available}")
        
        matched = next((p for p in available if midi_port_name.lower() in p.lower()), None)
        if not matched:
            matched = next((p for p in available if "loopmidi" in p.lower()), None)
        if not matched:
            non_ms = next((p for p in available if "wavetable" not in p.lower()), None)
            matched = non_ms if non_ms else (available[0] if available else None)

        if matched is None:
            raise OSError("No MIDI output ports available on this system!")

        self.midi_out = mido.open_output(matched)
        print(f"[CONDUCTOR] >>> MIDI output connected to: '{matched}' <<<")

        # MIDI channels (0-indexed)
        self.CH_STRINGS    = 0  # Track 1 (Ch 1)
        self.CH_BRASS      = 1  # Track 2 (Ch 2)
        self.CH_PERCUSSION = 2  # Track 3 (Ch 3 - Air Drums)

        self.active_notes = {
            self.CH_STRINGS:    set(),
            self.CH_BRASS:      set(),
            self.CH_PERCUSSION: set(),
        }
        self.midi_lock = threading.Lock()

        # Motion & G-Force Tracking State
        self.prev_time = time.time()
        self.last_punch_time = 0.0
        self.last_hammer_time = 0.0
        self.last_crash_time = 0.0
        self.punch_armed = True
        self.hammer_armed = True

        # Telemetry & Chord State
        self.current_state = STATE_CALM
        self.state_enter_time = time.time()
        self.last_chord_time = 0.0
        self.chord_index = 0
        self.hit_count = 0

    def send_osc(self, address, val):
        try:
            pkt = OSCMessageBuilder.build_float_msg(address, val)
            self.osc_sock.sendto(pkt, (self.reaper_ip, self.reaper_port))
        except Exception:
            pass

    def note_on(self, channel, note, velocity=110):
        with self.midi_lock:
            self.midi_out.send(mido.Message('note_on', channel=channel, note=note, velocity=min(max(int(velocity), 1), 127)))
            self.active_notes[channel].add(note)

    def note_off(self, channel, note):
        with self.midi_lock:
            self.midi_out.send(mido.Message('note_off', channel=channel, note=note, velocity=0))
            self.active_notes[channel].discard(note)

    def trigger_epic_hit(self, name, kick_note, bass_note, chord_root, vel=127, duration=0.18):
        """Multi-layer heavy impact hit: strikes Drum Track 3 + Heavy Bass Track 2 + Strings Track 1."""
        self.hit_count += 1
        print(f"[EPIC HIT #{self.hit_count}] {name} -> Drum:{kick_note}, Bass:{bass_note}, Strings:{chord_root} (vel={vel})")

        # 1. Fire on Track 3 (Air Drums)
        self.note_on(self.CH_PERCUSSION, kick_note, vel)
        # 2. Fire on Track 2 (Heavy Bass Drive)
        self.note_on(self.CH_BRASS, bass_note, min(vel, 125))
        # 3. Fire on Track 1 (Orchestral Strings Accent)
        self.note_on(self.CH_STRINGS, chord_root, min(vel, 120))

        # 4. Swell REAPER Track volumes
        self.send_osc("/track/3/volume", 1.0)
        self.send_osc("/track/2/volume", 0.95)

        def _release():
            self.note_off(self.CH_PERCUSSION, kick_note)
            self.note_off(self.CH_BRASS, bass_note)
            self.note_off(self.CH_STRINGS, chord_root)

        t = threading.Timer(duration, _release)
        t.daemon = True
        t.start()

    def silence_channel(self, channel):
        with self.midi_lock:
            for note in list(self.active_notes[channel]):
                self.midi_out.send(mido.Message('note_off', channel=channel, note=note, velocity=0))
            self.active_notes[channel].clear()

    def silence_all(self):
        for ch in self.active_notes:
            self.silence_channel(ch)

    def send_cc(self, channel, cc, value):
        with self.midi_lock:
            self.midi_out.send(mido.Message('control_change', channel=channel, control=cc, value=min(max(int(value), 0), 127)))

    # -------------------------------------------------------------------------
    # 100Hz HARDWARE IMU IMPULSE & MOTION PROCESSING
    # -------------------------------------------------------------------------
    def process_imu_sample(self, ax, ay, az, gx, gy, gz, pitch, roll, g_mag):
        now = time.time()
        dt = max(now - self.prev_time, 0.005)
        self.prev_time = now

        # Normalize altitude & wingspan
        norm_alt = min(max((pitch + 15) / 75.0, 0.0), 1.0)
        norm_dist = min(max((abs(roll)) / 45.0, 0.0), 1.0)

        # Send Continuous MIDI CC & OSC Swells
        cc11_val = int(norm_alt * 105 + 22)
        cc91_val = int(norm_dist * 120)
        self.send_cc(self.CH_STRINGS, 11, cc11_val)
        self.send_cc(self.CH_BRASS, 11, cc11_val)
        self.send_cc(self.CH_STRINGS, 91, cc91_val)
        self.send_cc(self.CH_BRASS, 91, cc91_val)

        # Swell Track 4 BGM Master Soundtrack Volume
        bgm_vol = min(max(0.65 + 0.35 * norm_alt, 0.40), 1.0)
        self.send_osc("/track/4/volume", bgm_vol)

        # Generative Harmonic Chords
        self._tick_chords(norm_alt, g_mag, now)

        # =====================================================================
        # PHYSICAL G-FORCE IMPULSE DETECTION
        # =====================================================================
        
        # 1. FORWARD PUNCH (+Z Acceleration Thrust & Spike)
        if g_mag < 1.3:
            self.punch_armed = True

        if self.punch_armed and (az > 1.5 * (1.0 / self.sensitivity) or g_mag > 1.9 * (1.0 / self.sensitivity)) and (now - self.last_punch_time > 0.22):
            if abs(pitch) < 50:
                self.punch_armed = False
                self.last_punch_time = now
                punch_vel = min(max(int(85 + (g_mag / 3.0) * 42), 95), 127)
                self.trigger_epic_hit("808 PUNCH BOOM", kick_note=36, bass_note=48, chord_root=60, vel=punch_vel)

        # 2. DOWNWARD HAMMER STRIKE (-Y Vertical G-Force Impact)
        if ay > -0.8:
            self.hammer_armed = True

        if self.hammer_armed and (ay < -1.3 * (1.0 / self.sensitivity) or (g_mag > 1.9 and pitch < 30)) and (now - self.last_hammer_time > 0.20):
            self.hammer_armed = False
            self.last_hammer_time = now
            hammer_vel = min(max(int(85 + (g_mag / 3.0) * 42), 95), 127)

            if roll < 15:
                self.trigger_epic_hit("HAMMER SNARE", kick_note=38, bass_note=62, chord_root=65, vel=hammer_vel)
            else:
                self.trigger_epic_hit("HAMMER TOM", kick_note=45, bass_note=57, chord_root=60, vel=hammer_vel)

        # 3. OVERHEAD WHIP / CRASH CYMBAL
        angular_speed = math.hypot(gx, gy, gz)
        if (pitch > 30) and (angular_speed > 200 or g_mag > 2.4) and (now - self.last_crash_time > 0.38):
            self.last_crash_time = now
            crash_vel = min(max(int(90 + (g_mag / 3.5) * 37), 105), 127)
            self.trigger_epic_hit("OVERHEAD CRASH", kick_note=49, bass_note=72, chord_root=76, vel=crash_vel, duration=0.30)

    def _tick_chords(self, alt, g_mag, now):
        if now - self.last_chord_time < 2.8:
            return
        self.last_chord_time = now

        note_vel = int(min(max(75 + alt * 35, 55), 120))
        transpose = int((alt - 0.5) * 12)

        chords = CHORD_PROGRESSIONS[self.current_state]
        base = chords[self.chord_index % len(chords)]
        self.chord_index += 1

        target = [min(max(n + transpose, 36), 84) for n in base]

        # Strings Pad (Ch 0)
        self.silence_channel(self.CH_STRINGS)
        for note in target:
            self.note_on(self.CH_STRINGS, note, note_vel)

        # Bass (Ch 1)
        self.silence_channel(self.CH_BRASS)
        self.note_on(self.CH_BRASS, target[0] - 12, min(note_vel + 10, 127))

# =============================================================================
# NATIVE UDP OSC SENSOR LISTENER (Phyphox / Sensors2OSC / ZIG SIM / TouchOSC)
# =============================================================================
def start_udp_osc_listener(conductor, udp_port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', udp_port))
    print(f"[NATIVE OSC HUB] UDP listener active on port {udp_port} (Phyphox/Sensors2OSC ready)...")

    while True:
        try:
            data, _ = sock.recvfrom(2048)
            addr, args = parse_osc_packet(data)
            if not addr:
                continue

            # Standard native app OSC patterns
            if addr in ['/acc', '/accelerometer', '/motion/acc', '/sensors/acc']:
                if len(args) >= 3:
                    ax, ay, az = float(args[0]), float(args[1]), float(args[2])
                    g_mag = math.sqrt(ax*ax + ay*ay + az*az) / 9.81
                    conductor.process_imu_sample(ax, ay, az, 0, 0, 0, 0, 0, g_mag)
            elif addr in ['/gyro', '/gyroscope', '/motion/gyro']:
                if len(args) >= 3:
                    gx, gy, gz = float(args[0]), float(args[1]), float(args[2])
                    conductor.process_imu_sample(0, 0, 0, gx, gy, gz, 0, 0, 1.0)
            elif addr in ['/orientation', '/motion/orientation']:
                if len(args) >= 2:
                    pitch, roll = float(args[0]), float(args[1])
                    conductor.process_imu_sample(0, 0, 0, 0, 0, 0, pitch, roll, 1.0)
        except Exception:
            pass

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def print_ascii_qr(url):
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    f = io.StringIO()
    qr.print_ascii(out=f)
    f.seek(0)
    print(f.read())

def run_app():
    global GLOBAL_CONDUCTOR
    parser = argparse.ArgumentParser(description="Smartphone IMU Motion Conductor Hub")
    parser.add_argument("--http-port",   type=int, default=8080, help="HTTP server port for phone web app")
    parser.add_argument("--udp-port",    type=int, default=5005, help="Native OSC UDP port")
    parser.add_argument("--reaper-ip",   default="127.0.0.1",   help="REAPER host IP")
    parser.add_argument("--reaper-port", type=int, default=8000, help="REAPER OSC port")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="G-Force strike sensitivity multiplier")
    args = parser.parse_args()

    local_ip = get_local_ip()
    phone_url = f"http://{local_ip}:{args.http_port}"

    conductor = PhoneMotionConductor(args.reaper_ip, args.reaper_port, sensitivity=args.sensitivity)
    GLOBAL_CONDUCTOR = conductor

    # Start Native UDP OSC Listener Thread (for Phyphox, Sensors2OSC, ZIG SIM)
    udp_thread = threading.Thread(target=start_udp_osc_listener, args=(conductor, args.udp_port), daemon=True)
    udp_thread.start()

    # Start HTTP Server thread (Pure direct HTTP - zero SSL headaches)
    http_thread = threading.Thread(target=start_http_server, args=('0.0.0.0', args.http_port), daemon=True)
    http_thread.start()

    print("==================================================================")
    print("SMARTPHONE AIR BAND MOTION CONTROLLER IS ACTIVE!")
    print("==================================================================")
    print("📱 OPTION A (NO APP - Web Browser):")
    print(f"   Open: {phone_url}")
    try:
        print_ascii_qr(phone_url)
    except Exception:
        pass
    print("📱 OPTION B (NATIVE SENSOR APP - Phyphox / Sensors2OSC / ZIG SIM):")
    print(f"   Stream UDP to -> IP: {local_ip} | Port: {args.udp_port}")
    print("==================================================================")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[CONDUCTOR] Shutting down...")

if __name__ == "__main__":
    run_app()
