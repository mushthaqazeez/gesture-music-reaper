"""
===============================================================================
UNIVERSAL SMARTPHONE HARDWARE IMU AIR DRUMMER HUB (FOR REAPER)
===============================================================================
Description:
    Universal ultra-low latency motion hub compatible with Phyphox:
      - Scan QR code inside Phyphox app (Add experiment from QR code)
      - Direct 100Hz hardware accelerometer stream to REAPER DAW

    Physics Mapping:
      - 💥 Forward Punch -> +G Forward Thrust -> Epic 808 Sub-Bass Boom (Ch 1/2/3)
      - 🥁 Downward Hammer -> Vertical Impact G-Force -> Heavy Snare / Low Tom
      - 🌟 Overhead Whip -> High-Speed Angular Gyro Spin -> Massive Crash Cymbal
      - 🎻 Pitch Tilt (Up/Down) -> Arm Altitude -> String Chords + BGM Swell (CC11 / OSC)
      - 🌊 Roll Tilt (Left/Right) -> Wingspan -> Reverb Depth & Width (CC91)

Usage:
    .venv\\Scripts\\python.exe smart_phone_hub.py
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
import urllib.parse
import mido
from http.server import HTTPServer, BaseHTTPRequestHandler
import qrcode
import io

# Script directory and resource paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PHYPHOX_FILE = os.path.join(SCRIPT_DIR, "reaper_air_band.phyphox")
QR_FILE = os.path.join(SCRIPT_DIR, "phyphox_qr_code.png")

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
# OSC PACKET BUILDER
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

# Global engine reference for HTTP Handler
GLOBAL_ENGINE = None

# =============================================================================
# AIR DRUMMER MIDI & OSC ENGINE
# =============================================================================
class AirDrummerEngine:
    def __init__(self, reaper_ip="127.0.0.1", reaper_port=8000, midi_port_name="GestureConductor", sensitivity=1.0):
        self.reaper_ip = reaper_ip
        self.reaper_port = reaper_port
        self.sensitivity = sensitivity
        self.osc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Connect MIDI
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
        self.CH_STRINGS    = 0  # Track 1
        self.CH_BRASS      = 1  # Track 2
        self.CH_PERCUSSION = 2  # Track 3

        self.active_notes = {
            self.CH_STRINGS:    set(),
            self.CH_BRASS:      set(),
            self.CH_PERCUSSION: set(),
        }
        self.midi_lock = threading.Lock()

        # Motion State
        self.prev_time = time.time()
        self.last_punch_time = 0.0
        self.last_hammer_time = 0.0
        self.last_crash_time = 0.0
        self.punch_armed = True
        self.hammer_armed = True

        # Telemetry & Chord State
        self.current_state = STATE_CALM
        self.last_chord_time = 0.0
        self.chord_index = 0
        self.hit_count = 0
        self.packet_count = 0

    def send_osc(self, address, val):
        try:
            pkt = OSCMessageBuilder.build_float_msg(address, val)
            self.osc_sock.sendto(pkt, (self.reaper_ip, self.reaper_port))
        except Exception:
            pass

    def note_on(self, channel, note, velocity=115):
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
        print(f"\n💥 [HIT #{self.hit_count}] {name} -> Kick:{kick_note}, Bass:{bass_note}, Strings:{chord_root} (vel={vel})")

        # 1. Fire on Track 3 (Air Drums)
        self.note_on(self.CH_PERCUSSION, kick_note, vel)
        # 2. Fire on Track 2 (Heavy Bass Drive)
        self.note_on(self.CH_BRASS, bass_note, min(vel, 125))
        # 3. Fire on Track 1 (Orchestral Strings Accent)
        self.note_on(self.CH_STRINGS, chord_root, min(vel, 120))

        # 4. Boost REAPER Track volumes
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

    def send_cc(self, channel, cc, value):
        with self.midi_lock:
            self.midi_out.send(mido.Message('control_change', channel=channel, control=cc, value=min(max(int(value), 0), 127)))

    def process_sample(self, ax, ay, az, now):
        self.packet_count += 1
        g_mag = math.sqrt(ax*ax + ay*ay + az*az) / 9.81
        
        # Calculate pitch & roll
        pitch = math.degrees(math.atan2(-ay, max(math.sqrt(ax*ax + az*az), 0.001)))
        roll = math.degrees(math.atan2(ax, max(abs(az), 0.001)))

        if self.packet_count % 25 == 0:
            print(f"  [STREAMING 100Hz] G:{g_mag:.1f}G | X:{ax:5.1f} Y:{ay:5.1f} Z:{az:5.1f} | Elevation:{pitch:3.0f}°", end='\r')

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
        self._tick_chords(norm_alt, now)

        # =====================================================================
        # PHYSICAL G-FORCE IMPULSE DETECTION
        # =====================================================================
        
        # 1. FORWARD PUNCH (Forward Thrust +Z Spike)
        if g_mag < 1.3:
            self.punch_armed = True

        if self.punch_armed and (az > 12.0 * (1.0 / self.sensitivity) or g_mag > 2.0 * (1.0 / self.sensitivity)) and (now - self.last_punch_time > 0.22):
            if abs(pitch) < 55:
                self.punch_armed = False
                self.last_punch_time = now
                punch_vel = min(max(int(85 + (g_mag / 3.0) * 42), 95), 127)
                self.trigger_epic_hit("808 PUNCH BOOM", kick_note=36, bass_note=48, chord_root=60, vel=punch_vel)

        # 2. DOWNWARD HAMMER STRIKE (Downward Impact -Y Spike)
        if ay > -4.0:
            self.hammer_armed = True

        if self.hammer_armed and (ay < -11.0 * (1.0 / self.sensitivity) or (g_mag > 1.9 and pitch < 30)) and (now - self.last_hammer_time > 0.20):
            self.hammer_armed = False
            self.last_hammer_time = now
            hammer_vel = min(max(int(85 + (g_mag / 3.0) * 42), 95), 127)

            if roll < 15:
                self.trigger_epic_hit("HAMMER SNARE", kick_note=38, bass_note=62, chord_root=65, vel=hammer_vel)
            else:
                self.trigger_epic_hit("HAMMER TOM", kick_note=45, bass_note=57, chord_root=60, vel=hammer_vel)

        # 3. OVERHEAD WHIP / CRASH CYMBAL
        if (pitch > 35) and (g_mag > 2.5 * (1.0 / self.sensitivity)) and (now - self.last_crash_time > 0.38):
            self.last_crash_time = now
            crash_vel = min(max(int(90 + (g_mag / 3.5) * 37), 105), 127)
            self.trigger_epic_hit("OVERHEAD CRASH", kick_note=49, bass_note=72, chord_root=76, vel=crash_vel, duration=0.30)

    def _tick_chords(self, alt, now):
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
# HTTP SERVER FOR PHYPHOX EXPERIMENT & DATA INGESTION
# =============================================================================
class PhyphoxHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith('.phyphox') or self.path == '/reaper_air_band.phyphox' or self.path == '/':
            if os.path.exists(PHYPHOX_FILE):
                with open(PHYPHOX_FILE, "rb") as f:
                    xml_data = f.read()
            else:
                xml_data = b"<phyphox version='1.17'><title>Air Band</title></phyphox>"

            self.send_response(200)
            self.send_header('Content-Type', 'application/phyphox; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="reaper_air_band.phyphox"')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(xml_data)
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Phyphox Air Drummer Hub Active")

    def do_POST(self):
        global GLOBAL_ENGINE
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        if GLOBAL_ENGINE:
            try:
                # 1. Try URL-encoded form data (x=...&y=...&z=...)
                parsed = urllib.parse.parse_qs(post_data.decode('utf-8', errors='ignore'))
                if 'x' in parsed and 'y' in parsed and 'z' in parsed:
                    ax = float(parsed['x'][-1])
                    ay = float(parsed['y'][-1])
                    az = float(parsed['z'][-1])
                    GLOBAL_ENGINE.process_sample(ax, ay, az, time.time())
                else:
                    # 2. Try JSON
                    data = json.loads(post_data.decode('utf-8'))
                    if 'x' in data and 'y' in data and 'z' in data:
                        GLOBAL_ENGINE.process_sample(float(data['x']), float(data['y']), float(data['z']), time.time())
            except Exception:
                pass

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass

def start_http_server(host, port):
    server = HTTPServer((host, port), PhyphoxHTTPHandler)
    server.serve_forever()

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

def run_hub():
    global GLOBAL_ENGINE
    parser = argparse.ArgumentParser(description="Universal Phyphox Air Drummer Hub")
    parser.add_argument("--http-port",   type=int, default=8080, help="HTTP server port for Phyphox experiment")
    parser.add_argument("--reaper-ip",   default="127.0.0.1",   help="REAPER host IP")
    parser.add_argument("--reaper-port", type=int, default=8000, help="REAPER OSC port")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="Hit sensitivity multiplier")
    args = parser.parse_args()

    local_ip = get_local_ip()
    phyphox_url = f"http://{local_ip}:{args.http_port}/reaper_air_band.phyphox"

    engine = AirDrummerEngine(reaper_ip=args.reaper_ip, reaper_port=args.reaper_port, sensitivity=args.sensitivity)
    GLOBAL_ENGINE = engine

    # Update XML file with local IP
    xml_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<phyphox version="1.17">
    <title>REAPER Air Band Drummer</title>
    <category>Audio Music</category>
    <description>Streams 100Hz hardware accelerometer directly to REAPER DAW</description>
    <data-containers>
        <data-container size="1">accX</data-container>
        <data-container size="1">accY</data-container>
        <data-container size="1">accZ</data-container>
        <data-container size="1">t</data-container>
    </data-containers>
    <input>
        <sensor type="accelerometer">
            <output component="x">accX</output>
            <output component="y">accY</output>
            <output component="z">accZ</output>
            <output component="t">t</output>
        </sensor>
    </input>
    <views>
        <view label="Air Drummer">
            <value label="Forward Thrust Z">
                <input>accZ</input>
            </value>
            <value label="Vertical Impact Y">
                <input>accY</input>
            </value>
            <value label="Lateral Tilt X">
                <input>accX</input>
            </value>
        </view>
    </views>
    <network>
        <connection id="reaper_stream" address="http://{local_ip}:{args.http_port}/data" auto="true" interval="0.02">
            <send id="x">accX</send>
            <send id="y">accY</send>
            <send id="z">accZ</send>
        </connection>
    </network>
</phyphox>
"""
    with open(PHYPHOX_FILE, "w", encoding="utf-8") as f:
        f.write(xml_content)

    # Generate PNG image
    img = qrcode.make(phyphox_url)
    img.save(QR_FILE)

    # Start HTTP Server thread
    http_thread = threading.Thread(target=start_http_server, args=('0.0.0.0', args.http_port), daemon=True)
    http_thread.start()

    print("==================================================================")
    print("🚀 PHYPHOX AIR DRUMMER HUB ACTIVE!")
    print("==================================================================")
    print("📲 IN PHYPHOX APP ON YOUR PHONE:")
    print("   1. Tap '+' -> 'Add experiment from QR code'.")
    print("   2. Scan this QR Code on your screen:")
    try:
        print_ascii_qr(phyphox_url)
    except Exception:
        pass
    print(f"\n   (Or on phone browser, open: {phyphox_url})")
    print("   3. Tap the PLAY (▶) button at the top of Phyphox!")
    print("==================================================================")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[HUB] Shutting down...")

if __name__ == "__main__":
    run_hub()
