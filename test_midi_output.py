"""
===============================================================================
AIR BAND & GESTURE MUSIC ENGINE - MIDI INTEGRATION TEST
===============================================================================
Tests all 3 channels on 'GestureConductor' (or fallback MIDI port):
  - Channel 1 (Ch 0 in mido): Strings Chord
  - Channel 2 (Ch 1 in mido): Brass Note
  - Channel 3 (Ch 2 in mido): Air Drum Kit (Punch Boom, Hammer Snare/Tom, Crash, Clap)
===============================================================================
"""
import sys
import time
import argparse
import mido

# Ensure UTF-8 output encoding for Windows terminal
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def run_midi_test(port_name=None):
    ports = mido.get_output_names()
    print(f"Available MIDI output ports: {ports}")

    if not ports:
        print("[ERROR] No MIDI output ports available on this system!")
        print("Please install loopMIDI and create a virtual port named 'GestureConductor'.")
        return False

    matched = None
    if port_name:
        matched = next((p for p in ports if port_name.lower() in p.lower()), None)

    if not matched:
        matched = next((p for p in ports if "gestureconductor" in p.lower()), None)
    if not matched:
        matched = next((p for p in ports if "loopmidi" in p.lower()), None)
    if not matched:
        # Fall back to any available non-synth or first port
        non_ms = next((p for p in ports if "wavetable" not in p.lower()), None)
        matched = non_ms if non_ms else ports[0]
        print(f"[NOTICE] 'GestureConductor' port not found. Falling back to '{matched}'.")
        print("For REAPER routing, install loopMIDI and create a port named 'GestureConductor'.\n")

    print(f"Opening port: '{matched}'")
    try:
        out = mido.open_output(matched)
    except Exception as e:
        print(f"[ERROR] Failed to open MIDI port '{matched}': {e}")
        return False

    def trigger_drum(name, note, channel=2, duration=0.15, vel=110):
        print(f"  [DRUM HIT] Triggering {name} -> Note {note} on Channel {channel+1} (vel={vel})...")
        out.send(mido.Message('note_on', channel=channel, note=note, velocity=vel))
        time.sleep(duration)
        out.send(mido.Message('note_off', channel=channel, note=note, velocity=0))
        time.sleep(0.1)

    try:
        print("\n--- 1. Testing Track 1: Strings Chord (Ch 1) ---")
        chord = [50, 57, 62, 65]  # Dm
        for n in chord:
            out.send(mido.Message('note_on', channel=0, note=n, velocity=90))
        time.sleep(1.0)
        for n in chord:
            out.send(mido.Message('note_off', channel=0, note=n, velocity=0))

        print("\n--- 2. Testing Track 2: Brass Bass (Ch 2) ---")
        out.send(mido.Message('note_on', channel=1, note=38, velocity=100))
        time.sleep(0.8)
        out.send(mido.Message('note_off', channel=1, note=38, velocity=0))

        print("\n--- 3. Testing Track 3: Air Drum Kit (Ch 3) ---")
        trigger_drum("PUNCH BOOM (Sub-Bass Kick)", note=36, vel=120)
        trigger_drum("HAMMER DROP (Snare Drum)", note=38, vel=115)
        trigger_drum("HAMMER DROP (Low Tom)", note=45, vel=110)
        trigger_drum("AIR CLAP (Handclap Accent)", note=39, vel=105)
        trigger_drum("OVERHEAD CRASH (Crash Cymbal)", note=49, vel=125)

        print("\n--- 4. Mini Groove Demo (Punch + Hammer + Chords) ---")
        for i in range(2):
            # Kick on 1
            trigger_drum("Punch Boom", 36, duration=0.1)
            # Snare on 2
            trigger_drum("Hammer Snare", 38, duration=0.1)
            # Kick on 3
            trigger_drum("Punch Boom", 36, duration=0.1)
            # Tom on 4
            trigger_drum("Hammer Tom", 45, duration=0.1)

        print("\n=== ALL TESTS SENT SUCCESSFULLY ===")
        return True
    finally:
        out.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MIDI Output Integration Test for Gesture Music Reaper")
    parser.add_argument("--port", default=None, help="Specific MIDI output port name to target")
    args = parser.parse_args()
    success = run_midi_test(args.port)
    if not success:
        sys.exit(1)
