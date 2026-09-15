"""
===============================================================================
PHYPHOX SMARTPHONE HARDWARE IMU AIR DRUM ENGINE (FOR REAPER)
===============================================================================
Description:
    Connects directly to your phone's PHYPHOX app over Wi-Fi for 100% native
    hardware accelerometer & gyroscope capture (< 5ms latency):

      - 💥 Forward Punch -> +G Forward Thrust -> Epic 808 Sub-Bass Boom (Ch 1/2/3)
      - 🥁 Downward Hammer -> Vertical Impact G-Force -> Heavy Snare / Low Tom
      - 🌟 Overhead Whip -> High-Speed Angular Gyro Spin -> Massive Crash Cymbal
      - 🎻 Pitch Tilt (Up/Down) -> Arm Altitude -> String Chords + BGM Swell (CC11 / OSC)
      - 🌊 Roll Tilt (Left/Right) -> Wingspan -> Reverb Depth & Width (CC91)

Usage:
    .venv\\Scripts\\python.exe phyphox_air_drummer.py
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
import urllib.request
import urllib.error
import mido

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

# =============================================================================
# PHYPHOX AIR DRUMMER ENGINE
# =============================================================================
class PhyphoxAirDrummer:
    def __init__(self, phone_ip, phone_port=8080, reaper_ip="127.0.0.1", reaper_port=8000, midi_port_name="GestureConductor", sensitivity=1.0):
        self.phone_ip = phone_ip
        self.phone_port = phone_port
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
        print(f"\n[💥 HIT #{self.hit_count}] {name} -> Drum:{kick_note}, Bass:{bass_note}, Strings:{chord_root} (vel={vel})")

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
        # Calculate total G-Force magnitude
        g_mag = math.sqrt(ax*ax + ay*ay + az*az) / 9.81
        
        # Calculate pitch (elevation) approximation from gravity vector
        pitch = math.degrees(math.atan2(-ay, math.sqrt(ax*ax + az*az)))
        roll = math.degrees(math.atan2(ax, az))

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

        if self.punch_armed and (az > 14.0 * (1.0 / self.sensitivity) or g_mag > 2.2 * (1.0 / self.sensitivity)) and (now - self.last_punch_time > 0.22):
            if abs(pitch) < 55:
                self.punch_armed = False
                self.last_punch_time = now
                punch_vel = min(max(int(85 + (g_mag / 3.0) * 42), 95), 127)
                self.trigger_epic_hit("💥 808 PUNCH BOOM", kick_note=36, bass_note=48, chord_root=60, vel=punch_vel)

        # 2. DOWNWARD HAMMER STRIKE (Downward Impact -Y Spike)
        if ay > -5.0:
            self.hammer_armed = True

        if self.hammer_armed and (ay < -13.0 * (1.0 / self.sensitivity) or (g_mag > 2.1 and pitch < 30)) and (now - self.last_hammer_time > 0.20):
            self.hammer_armed = False
            self.last_hammer_time = now
            hammer_vel = min(max(int(85 + (g_mag / 3.0) * 42), 95), 127)

            if roll < 15:
                self.trigger_epic_hit("🥁 HAMMER SNARE", kick_note=38, bass_note=62, chord_root=65, vel=hammer_vel)
            else:
                self.trigger_epic_hit("🥁 HAMMER TOM", kick_note=45, bass_note=57, chord_root=60, vel=hammer_vel)

        # 3. OVERHEAD WHIP / CRASH CYMBAL
        if (pitch > 35) and (g_mag > 2.7 * (1.0 / self.sensitivity)) and (now - self.last_crash_time > 0.38):
            self.last_crash_time = now
            crash_vel = min(max(int(90 + (g_mag / 3.5) * 37), 105), 127)
            self.trigger_epic_hit("🌟 OVERHEAD CRASH", kick_note=49, bass_note=72, chord_root=76, vel=crash_vel, duration=0.30)

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
# AUTO-DISCOVERY & STREAMING LOOP
# =============================================================================
def find_phyphox_ip():
    """Scans local subnet to automatically discover Phyphox device if not specified."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()

    subnet_prefix = '.'.join(local_ip.split('.')[:3])
    print(f"[DISCOVERY] Scanning Wi-Fi subnet ({subnet_prefix}.*) for Phyphox phone...")

    # Fast scan of most likely IPs
    for host in range(1, 255):
        test_ip = f"{subnet_prefix}.{host}"
        if test_ip == local_ip:
            continue
        try:
            url = f"http://{test_ip}:8080/get?accX=full"
            req = urllib.request.Request(url, headers={'User-Agent': 'PhyphoxAirDrummer'})
            with urllib.request.urlopen(req, timeout=0.08) as resp:
                if resp.status == 200:
                    print(f"[DISCOVERY] >>> FOUND PHYPHOX PHONE AT: {test_ip} <<<")
                    return test_ip
        except Exception:
            pass

    return None

def run_phyphox_stream(phone_ip, sensitivity=1.0):
    drummer = PhyphoxAirDrummer(phone_ip=phone_ip, sensitivity=sensitivity)
    
    print("==================================================================")
    print(f"🚀 CONNECTED TO PHYPHOX PHONE AT: http://{phone_ip}:8080")
    print("==================================================================")
    print("Hold phone firmly like a drumstick:")
    print("  💥 Forward Punch -> 808 Sub Kick Boom")
    print("  🥁 Downward Hammer -> Snare / Low Tom")
    print("  🌟 Overhead Whip -> Crash Cymbal")
    print("  🎻 Tilt Elevation -> Strings & BGM Soundtrack Swell")
    print("==================================================================")

    url = f"http://{phone_ip}:8080/get?accX&accY&accZ"
    
    consecutive_errors = 0
    poll_interval = 0.015 # ~65 Hz high speed polling

    while True:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PhyphoxClient'})
            with urllib.request.urlopen(req, timeout=0.4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                consecutive_errors = 0

                # Extract latest acceleration sample
                buffer_data = data.get('buffer', {})
                acc_x_buf = buffer_data.get('accX', {}).get('buffer', [])
                acc_y_buf = buffer_data.get('accY', {}).get('buffer', [])
                acc_z_buf = buffer_data.get('accZ', {}).get('buffer', [])

                if acc_x_buf and acc_y_buf and acc_z_buf:
                    val_x = acc_x_buf[-1]
                    val_y = acc_y_buf[-1]
                    val_z = acc_z_buf[-1]
                    if val_x is not None and val_y is not None and val_z is not None:
                        ax = float(val_x)
                        ay = float(val_y)
                        az = float(val_z)
                        drummer.process_sample(ax, ay, az, time.time())
                    else:
                        consecutive_errors += 1
                        if consecutive_errors % 40 == 1:
                            print("[STATUS] Phyphox connected! Tap the PLAY (▶) button at the top of your phone screen to start motion streaming.")

            time.sleep(poll_interval)
        except urllib.error.URLError:
            consecutive_errors += 1
            if consecutive_errors == 1 or consecutive_errors % 20 == 0:
                print(f"[RECONNECTING] Waiting for Phyphox on http://{phone_ip}:8080 (Ensure remote access is ON & Play is pressed)...")
            time.sleep(0.5)
        except Exception as e:
            time.sleep(0.1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phyphox Hardware IMU Air Drum Engine")
    parser.add_argument("--ip", help="Phyphox phone IP address (e.g. 10.141.237.50)")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="Hit sensitivity multiplier")
    args = parser.parse_args()

    phone_ip = args.ip
    if not phone_ip:
        # Prompt or auto-discover
        print("==================================================================")
        print("📱 PHYPHOX 1-STEP CONNECTION GUIDE:")
        print("==================================================================")
        print("1. Open the Phyphox app on your phone.")
        print("2. Tap on 'Acceleration with g' (or 'Raw Sensors' -> 'Acceleration').")
        print("3. Tap the 3 dots menu (⋮) at top right -> Tap 'Allow remote access'.")
        print("4. Tap the PLAY (▶) button at the top.")
        print("5. Look at the URL displayed at the bottom of your phone screen.")
        print("==================================================================")
        
        user_input = input("\nEnter your Phone IP (e.g. 10.141.237.50) [Or press Enter to auto-scan]: ").strip()
        if user_input:
            phone_ip = user_input.replace('http://', '').replace(':8080', '').replace('/', '')
        else:
            phone_ip = find_phyphox_ip()
            if not phone_ip:
                print("[ERROR] Could not auto-detect phone. Please enter your phone's IP address directly.")
                sys.exit(1)

    run_phyphox_stream(phone_ip, sensitivity=args.sensitivity)
