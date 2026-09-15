"""
===============================================================================
EXTERNAL ALGORITHMIC CONDUCTOR & AIR BAND MIDI ENGINE (4-TRACK REAPER SETUP)
===============================================================================
Description:
    Monitors incoming kinematic gesture streams & physical impulse gestures on UDP Port 5005:
      - /gesture/punch   -> Boom / 808 Sub-Drop / Kick (Note 36 / C1)
      - /gesture/hammer  -> Snare (Note 38 / D1) [L] or Low Tom (Note 45 / A1) [R]
      - /gesture/crash   -> Crash Cymbal (Note 49 / C#2)
      - /gesture/clap    -> Handclap / Impact Accent (Note 39 / D#1)
      - /kinematics/*    -> Continuous Cinematic Strings & Brass Pad Chords

    Outputs:
      - Real MIDI notes & CCs -> loopMIDI "GestureConductor" (or fallback)
          * Channel 1 (mido 0): Track 1 - Strings Pad & Atmosphere
          * Channel 2 (mido 1): Track 2 - Brass & Low Bass Tension
          * Channel 3 (mido 2): Track 3 - Air Drum Kit (Kick Boom, Snare, Toms, Cymbal, Clap)
      - OSC commands -> REAPER port 8000 for mixer sweeps:
          * Track 1 (Strings), Track 2 (Brass), Track 3 (Drums), Track 4 (00_Soundtrack_BGM)

Usage:
    .venv\\Scripts\\python.exe osc_conductor.py --listen-port 5005 --reaper-port 8000
===============================================================================
"""

import sys
import socket
import struct
import time
import math
import collections
import argparse
import random
import threading
import mido

# Ensure UTF-8 output encoding for Windows terminal
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# =============================================================================
# MARKOV STATE DEFINITIONS
# =============================================================================
STATE_CALM    = "CALM_ATMOSPHERE"
STATE_TENSION = "BUILDING_TENSION"
STATE_CLIMAX  = "CLIMAX_DREAD"
STATE_RELEASE = "RELEASE_DECAY"

STATES = [STATE_CALM, STATE_TENSION, STATE_CLIMAX, STATE_RELEASE]

BASE_TRANSITION_MATRIX = {
    STATE_CALM: {
        STATE_CALM:    0.70,
        STATE_TENSION: 0.25,
        STATE_CLIMAX:  0.05,
        STATE_RELEASE: 0.00
    },
    STATE_TENSION: {
        STATE_CALM:    0.15,
        STATE_TENSION: 0.50,
        STATE_CLIMAX:  0.30,
        STATE_RELEASE: 0.05
    },
    STATE_CLIMAX: {
        STATE_CALM:    0.05,
        STATE_TENSION: 0.20,
        STATE_CLIMAX:  0.55,
        STATE_RELEASE: 0.20
    },
    STATE_RELEASE: {
        STATE_CALM:    0.60,
        STATE_TENSION: 0.20,
        STATE_CLIMAX:  0.00,
        STATE_RELEASE: 0.20
    }
}

# =============================================================================
# CINEMATIC D-MINOR CHORD PROGRESSIONS
# =============================================================================
CHORD_PROGRESSIONS = {
    STATE_CALM: [
        [50, 57, 62, 65],        # Dm  (D3 A3 D4 F4)
        [46, 53, 58, 65],        # Bb  (Bb2 F3 Bb3 F4)
        [43, 50, 55, 62],        # Gm  (G2 D3 G3 D4)
        [45, 52, 57, 64],        # Am  (A2 E3 A3 E4)
    ],
    STATE_TENSION: [
        [50, 57, 62, 65, 69],    # Dm9
        [46, 53, 58, 62, 65],    # Bbmaj7
        [41, 48, 53, 60, 65],    # Fmaj
        [45, 52, 57, 61, 64],    # A7 (dominant tension)
    ],
    STATE_CLIMAX: [
        [38, 50, 57, 62, 65, 69, 74],  # Dm full tutti
        [34, 46, 53, 58, 62, 65, 70],  # Bb full brass+strings
        [36, 48, 55, 60, 64, 67, 72],  # C major (epic resolution attempt)
        [33, 45, 52, 57, 61, 64, 69],  # A dominant 7th
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

    @staticmethod
    def build_int_msg(address, value):
        addr_bytes = address.encode('utf-8') + b'\x00'
        while len(addr_bytes) % 4 != 0:
            addr_bytes += b'\x00'
        type_tags = b',i\x00\x00'
        val_bytes = struct.pack('>i', int(value))
        return addr_bytes + type_tags + val_bytes


def parse_osc_packet(data):
    """Decodes OSC packet into (address, list_of_args)."""
    try:
        null_idx = data.find(b'\x00')
        if null_idx == -1:
            return None, []
        address = data[:null_idx].decode('utf-8', errors='ignore')
        pad_offset = (null_idx + 4) & ~3
        if pad_offset >= len(data):
            return address, []

        if data[pad_offset:pad_offset+1] != b',':
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
            elif tag == 's':
                s_null = data.find(b'\x00', val_offset)
                if s_null != -1:
                    s_val = data[val_offset:s_null].decode('utf-8', errors='ignore')
                    args.append(s_val)
                    val_offset = (s_null + 4) & ~3
        return address, args
    except Exception:
        return None, []

# =============================================================================
# KINEMATIC FEATURE EXTRACTOR
# =============================================================================
class KinematicFeatureExtractor:
    """Computes velocity and kinetic energy from a sliding window of position values."""
    def __init__(self, window_size=20):
        self.buffer = collections.deque(maxlen=window_size)
        self.last_val = 0.0
        self.last_time = time.time()

    def update(self, raw_value):
        now = time.time()
        dt = max(now - self.last_time, 0.001)
        velocity = abs(raw_value - self.last_val) / dt
        self.buffer.append(raw_value)
        self.last_val = raw_value
        self.last_time = now

        if len(self.buffer) > 1:
            diffs = [abs(self.buffer[i] - self.buffer[i-1]) for i in range(1, len(self.buffer))]
            energy = sum(diffs) / len(diffs)
        else:
            energy = 0.0

        return {"position": raw_value, "velocity": velocity, "energy": energy}

# =============================================================================
# ALGORITHMIC CONDUCTOR & AIR BAND ENGINE
# =============================================================================
class AlgorithmicConductor:
    def __init__(self, reaper_ip, reaper_port, midi_port_name="GestureConductor"):
        self.reaper_ip = reaper_ip
        self.reaper_port = reaper_port
        self.osc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Smart MIDI output resolution
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
        print(f"[CONDUCTOR] >>> MIDI output successfully connected to: '{matched}' <<<")

        # MIDI channel assignments (0-indexed for mido)
        self.CH_STRINGS    = 0  # REAPER Track 1 (Channel 1)
        self.CH_BRASS      = 1  # REAPER Track 2 (Channel 2)
        self.CH_PERCUSSION = 2  # REAPER Track 3 (Channel 3 - Air Drum Kit)

        # Active note tracking
        self.active_notes = {
            self.CH_STRINGS:    set(),
            self.CH_BRASS:      set(),
            self.CH_PERCUSSION: set(),
        }
        self.midi_lock = threading.Lock()

        # Kinematic state
        self.extractor = KinematicFeatureExtractor()
        self.latest_velocity = 0.0
        self.latest_altitude = 0.5
        self.latest_distance = 0.5
        self.latest_openness = 1.0

        # Markov state machine
        self.current_state    = STATE_CALM
        self.state_enter_time = time.time()
        self.MIN_STATE_DURATION = 2.5

        # Thresholds
        self.ENERGY_TENSION_THRESH = 0.12
        self.ENERGY_CLIMAX_THRESH  = 0.35

        # Chord engine
        self.last_chord_time  = 0.0
        self.chord_index      = 0

        # Impulse hit stats
        self.hit_count = 0

        print(f"[CONDUCTOR] OSC output target: {reaper_ip}:{reaper_port}")
        print(f"[CONDUCTOR] Initial Harmonic State: {self.current_state}")
        print("==================================================================")
        print("AIR BAND & BGM CONDUCTOR READY: Standing by for gestures & hits...")
        print("==================================================================")

    # -------------------------------------------------------------------------
    # OSC SEND
    # -------------------------------------------------------------------------
    def send_osc(self, address, val, val_type='float'):
        try:
            if val_type == 'float':
                packet = OSCMessageBuilder.build_float_msg(address, val)
            else:
                packet = OSCMessageBuilder.build_int_msg(address, val)
            self.osc_sock.sendto(packet, (self.reaper_ip, self.reaper_port))
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # THREAD-SAFE MIDI OUTPUT
    # -------------------------------------------------------------------------
    def note_on(self, channel, note, velocity=90):
        with self.midi_lock:
            self.midi_out.send(mido.Message('note_on', channel=channel, note=note, velocity=min(max(int(velocity), 1), 127)))
            self.active_notes[channel].add(note)

    def note_off(self, channel, note):
        with self.midi_lock:
            self.midi_out.send(mido.Message('note_off', channel=channel, note=note, velocity=0))
            self.active_notes[channel].discard(note)

    def trigger_drum_hit(self, note, velocity=100, duration=0.14, name="DRUM"):
        """Instant zero-latency drum hit with non-blocking auto note-off."""
        vel = min(max(int(velocity), 50), 127)
        self.hit_count += 1
        print(f"[HIT #{self.hit_count}] {name} -> Note {note} (vel={vel})")
        
        self.note_on(self.CH_PERCUSSION, note, vel)
        
        def _release():
            self.note_off(self.CH_PERCUSSION, note)
            
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
    # DISPATCH OSC INPUTS
    # -------------------------------------------------------------------------
    def handle_osc_packet(self, address, args):
        if not address:
            return

        # --- 1. PHYSICAL IMPULSE DRUM GESTURES ---
        if address == "/gesture/punch":
            # Forward Punch -> Sub Boom / Kick (Note 36)
            vel_val = args[0] if len(args) > 0 else 0.8
            vel_midi = int(70 + float(vel_val) * 57)
            hand_str = "Left" if (len(args) > 1 and args[1] == 0) else "Right"
            self.trigger_drum_hit(note=36, velocity=vel_midi, duration=0.16, name=f"PUNCH BOOM [{hand_str}]")
            self.send_osc("/track/3/volume", 0.95, 'float')

        elif address == "/gesture/hammer":
            # Downward Hammer Strike -> Left Hand: Snare (38), Right Hand: Low Tom (45)
            vel_val = args[0] if len(args) > 0 else 0.8
            hand_idx = int(args[1]) if len(args) > 1 else 0
            vel_midi = int(70 + float(vel_val) * 57)

            if hand_idx == 0:
                self.trigger_drum_hit(note=38, velocity=vel_midi, duration=0.12, name="HAMMER SNARE [Left]")
            else:
                self.trigger_drum_hit(note=45, velocity=vel_midi, duration=0.15, name="HAMMER TOM [Right]")
            self.send_osc("/track/3/volume", 0.90, 'float')

        elif address == "/gesture/crash":
            # Overhead Crash Cymbal (Note 49)
            vel_val = args[0] if len(args) > 0 else 0.9
            vel_midi = int(80 + float(vel_val) * 47)
            self.trigger_drum_hit(note=49, velocity=vel_midi, duration=0.30, name="OVERHEAD CRASH")
            self.send_osc("/track/3/volume", 1.0, 'float')

        elif address == "/gesture/clap":
            # Air Clap / Fist Collision (Note 39)
            vel_val = args[0] if len(args) > 0 else 0.8
            vel_midi = int(75 + float(vel_val) * 52)
            self.trigger_drum_hit(note=39, velocity=vel_midi, duration=0.10, name="AIR CLAP")
            self.send_osc("/track/3/volume", 0.85, 'float')

        # --- 2. CONTINUOUS KINEMATIC TELEMETRY ---
        elif address in ["/kinematics", "/kinematics/velocity"]:
            if args:
                self.latest_velocity = float(args[0])
                self.process_kinematics(self.latest_velocity)
        elif address == "/kinematics/altitude":
            if args:
                self.latest_altitude = float(args[0])
        elif address == "/kinematics/distance":
            if args:
                self.latest_distance = float(args[0])
        elif address == "/kinematics/openness":
            if args:
                self.latest_openness = float(args[0])

    # -------------------------------------------------------------------------
    # MAIN CONTINUOUS KINEMATIC PROCESSING
    # -------------------------------------------------------------------------
    def process_kinematics(self, raw_float):
        features = self.extractor.update(raw_float)
        energy   = features["energy"]
        velocity = features["velocity"]
        now      = time.time()

        # Markov state evaluation
        if now - self.state_enter_time >= self.MIN_STATE_DURATION:
            next_state = self._evaluate_markov_transition(energy, velocity)
            if next_state != self.current_state:
                print(f"[STATE SHIFT] {self.current_state} --> {next_state}  "
                      f"(Energy:{energy:.3f} Vel:{velocity:.3f} Alt:{self.latest_altitude:.2f})")
                self.current_state    = next_state
                self.state_enter_time = now
                self.chord_index      = 0

        # Continuous MIDI expression (CC1 Dynamics, CC11 Expression, CC91 Reverb)
        self._send_expression_ccs()

        # Generative Harmonic Chords
        self._tick_chord_engine(raw_float, now)

        # Smooth OSC mixer sweeps to REAPER (including BGM track 4)
        self._send_osc_volumes()

    # -------------------------------------------------------------------------
    # MARKOV TRANSITION
    # -------------------------------------------------------------------------
    def _evaluate_markov_transition(self, energy, velocity):
        probs = dict(BASE_TRANSITION_MATRIX[self.current_state])

        if energy > self.ENERGY_CLIMAX_THRESH:
            probs[STATE_CLIMAX]  += 0.60
            probs[STATE_CALM]     = 0.0
        elif energy > self.ENERGY_TENSION_THRESH:
            probs[STATE_TENSION] += 0.40
            probs[STATE_CALM]    *= 0.2
        else:
            probs[STATE_CALM]    += 0.30
            probs[STATE_RELEASE] += 0.20

        total = sum(probs.values())
        norm  = {k: v / total for k, v in probs.items()}
        r     = random.random()
        cumul = 0.0
        for state, p in norm.items():
            cumul += p
            if r <= cumul:
                return state
        return self.current_state

    # -------------------------------------------------------------------------
    # MIDI EXPRESSION (CC1 Dynamics, CC11 Expression, CC91 Reverb)
    # -------------------------------------------------------------------------
    def _send_expression_ccs(self):
        alt  = self.latest_altitude
        vel  = self.latest_velocity
        dist = self.latest_distance

        cc1_val  = int(min(max(vel * 85 + 25, 20), 127))
        cc11_val = int(min(max(alt * 110 + 17, 20), 127))
        cc91_val = int(min(max(dist * 127, 0), 127))

        for ch in [self.CH_STRINGS, self.CH_BRASS, self.CH_PERCUSSION]:
            self.send_cc(ch, 1,  cc1_val)
            self.send_cc(ch, 11, cc11_val)
            self.send_cc(ch, 91, cc91_val)

    # -------------------------------------------------------------------------
    # GENERATIVE CHORD ENGINE
    # -------------------------------------------------------------------------
    def _tick_chord_engine(self, raw_val, now):
        durations = {
            STATE_CALM:    3.2,
            STATE_TENSION: 2.2,
            STATE_CLIMAX:  1.4,
            STATE_RELEASE: 4.0,
        }
        interval = durations.get(self.current_state, 2.5)

        if now - self.last_chord_time < interval:
            return

        self.last_chord_time = now

        note_vel  = int(min(max(70 + raw_val * 50, 50), 127))
        alt       = self.latest_altitude
        transpose = int((alt - 0.5) * 12)

        chords    = CHORD_PROGRESSIONS[self.current_state]
        base      = chords[self.chord_index % len(chords)]
        self.chord_index += 1

        target = [min(max(n + transpose, 36), 84) for n in base]

        # STRINGS (Channel 0): Play full chord progression
        self.silence_channel(self.CH_STRINGS)
        for note in target:
            self.note_on(self.CH_STRINGS, note, note_vel)

        # BRASS (Channel 1): Play low root + fifth in Tension and Climax
        self.silence_channel(self.CH_BRASS)
        if self.current_state in [STATE_TENSION, STATE_CLIMAX]:
            brass_notes = [target[0] - 12, target[0] - 5]
            for note in brass_notes:
                if 24 <= note <= 84:
                    self.note_on(self.CH_BRASS, note, min(note_vel + 10, 127))

    # -------------------------------------------------------------------------
    # OSC VOLUME SWELLS (Tracks 1, 2, 4 BGM)
    # -------------------------------------------------------------------------
    def _send_osc_volumes(self):
        alt  = self.latest_altitude
        dist = self.latest_distance
        vel  = self.latest_velocity

        # Track 4 (BGM Master Soundtrack volume swell with conducting height)
        bgm_vol = min(max(0.70 + 0.30 * alt, 0.40), 1.0)
        self.send_osc("/track/4/volume", bgm_vol, 'float')

        if self.current_state == STATE_CALM:
            self.send_osc("/track/1/volume", min(max(0.60 + 0.35 * alt, 0.2), 1.0), 'float')
            self.send_osc("/track/2/volume", min(max(0.10 + 0.20 * dist, 0.05), 0.35), 'float')
        elif self.current_state == STATE_TENSION:
            self.send_osc("/track/1/volume", min(max(0.70 + 0.30 * alt, 0.4), 1.0), 'float')
            self.send_osc("/track/2/volume", min(max(0.40 + 0.45 * dist, 0.2), 0.85), 'float')
        elif self.current_state == STATE_CLIMAX:
            self.send_osc("/track/1/volume", min(max(0.85 + 0.15 * alt, 0.6), 1.0), 'float')
            self.send_osc("/track/2/volume", min(max(0.80 + 0.20 * vel, 0.6), 1.0), 'float')
        elif self.current_state == STATE_RELEASE:
            self.send_osc("/track/1/volume", min(max(0.50 + 0.30 * alt, 0.15), 0.75), 'float')
            self.send_osc("/track/2/volume", min(max(0.15 + 0.20 * dist, 0.05), 0.40), 'float')

    # -------------------------------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------------------------------
    def shutdown(self):
        print("[CONDUCTOR] Silencing all notes and closing MIDI port...")
        self.silence_all()
        time.sleep(0.1)
        self.midi_out.close()
        self.osc_sock.close()

# =============================================================================
# SERVER LOOP
# =============================================================================
def run_server(listen_ip, listen_port, reaper_ip, reaper_port, midi_port_name):
    conductor = AlgorithmicConductor(reaper_ip, reaper_port, midi_port_name)
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind((listen_ip, listen_port))
    print(f"[CONDUCTOR] Server active. Listening on UDP {listen_ip}:{listen_port}...")

    try:
        while True:
            data, _ = srv.recvfrom(1024)
            address, args = parse_osc_packet(data)
            if address:
                conductor.handle_osc_packet(address, args)
    except KeyboardInterrupt:
        print("\n[CONDUCTOR] Shutting down on user interrupt...")
    finally:
        conductor.shutdown()
        srv.close()

# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Algorithmic Air Band Conductor for REAPER")
    parser.add_argument("--listen-ip",   default="0.0.0.0",         help="IP to listen for gesture stream")
    parser.add_argument("--listen-port", type=int, default=5005,     help="UDP port for incoming kinematics & gestures")
    parser.add_argument("--reaper-ip",   default="127.0.0.1",        help="REAPER host IP")
    parser.add_argument("--reaper-port", type=int, default=8000,     help="REAPER OSC receive port")
    parser.add_argument("--midi-port",   default="GestureConductor", help="loopMIDI virtual port name")
    args = parser.parse_args()

    run_server(args.listen_ip, args.listen_port, args.reaper_ip, args.reaper_port, args.midi_port)
