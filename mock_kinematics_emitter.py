"""
===============================================================================
MOCK KINEMATICS OSC EMITTER (SIMULATION SCRIPT)
===============================================================================
Description:
    Synthesizes continuous float gesture stream data (/kinematics on UDP Port 5005)
    to test REAPER OSC modulation and the Algorithmic Conductor state machine
    without requiring physical gesture tracking hardware online.

Usage:
    python mock_kinematics_emitter.py --port 5005 --interval 0.02
===============================================================================
"""

import socket
import struct
import time
import math
import argparse
import random

def build_osc_float(address, val):
    addr_bytes = address.encode('utf-8') + b'\x00'
    while len(addr_bytes) % 4 != 0:
        addr_bytes += b'\x00'
    type_tags = b',f\x00\x00'
    val_bytes = struct.pack('>f', float(val))
    return addr_bytes + type_tags + val_bytes

def run_simulation(target_ip, target_port, interval):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[SIMULATOR] Broadcasting mock /kinematics stream to {target_ip}:{target_port} every {interval}s")
    print("[SIMULATOR] Cycle: Calm Sine -> Tremor Swell -> Rapid Velocity Burst -> Silence")

    t = 0.0
    phase = 0
    phase_start_time = time.time()

    try:
        while True:
            now = time.time()
            elapsed_in_phase = now - phase_start_time

            if phase == 0:
                # PHASE 0: Low-Energy Calm Waveform [0.0 - 0.25]
                val = 0.12 + 0.08 * math.sin(t * 1.5)
                if elapsed_in_phase > 8.0:
                    phase = 1
                    phase_start_time = now
                    print("\n[SIMULATOR] Transitioning to Phase 1: Swell & Tremor")

            elif phase == 1:
                # PHASE 1: Moderate Swell with Tremor [0.25 - 0.65]
                noise = random.uniform(-0.05, 0.05)
                val = 0.40 + 0.20 * math.sin(t * 3.0) + noise
                if elapsed_in_phase > 8.0:
                    phase = 2
                    phase_start_time = now
                    print("\n[SIMULATOR] Transitioning to Phase 2: RAPID CLIMAX BURST")

            elif phase == 2:
                # PHASE 2: High Velocity Kinetic Burst [0.65 - 1.0]
                val = 0.50 + 0.45 * abs(math.sin(t * 8.0)) + random.uniform(-0.1, 0.1)
                if elapsed_in_phase > 6.0:
                    phase = 3
                    phase_start_time = now
                    print("\n[SIMULATOR] Transitioning to Phase 3: Release & Drop")

            elif phase == 3:
                # PHASE 3: Exponential Decay to Zero
                val = max(0.0, 0.80 * math.exp(-elapsed_in_phase * 0.8))
                if elapsed_in_phase > 5.0:
                    phase = 0
                    phase_start_time = now
                    print("\n[SIMULATOR] Transitioning to Phase 0: Baseline Calm")

            val = max(0.0, min(1.0, val)) # Clamp [0.0, 1.0]

            # Send packet
            packet = build_osc_float("/kinematics", val)
            sock.sendto(packet, (target_ip, target_port))

            # Console status meter
            bar_len = int(val * 40)
            bar = "█" * bar_len + "-" * (40 - bar_len)
            print(f"\r[SIMULATION] /kinematics: [{bar}] {val:.3f}", end="", flush=True)

            t += interval
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[SIMULATOR] Stopped simulation.")
    finally:
        sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock Kinematics OSC Emitter")
    parser.add_argument("--ip", default="127.0.0.1", help="Target UDP IP")
    parser.add_argument("--port", type=int, default=5005, help="Target UDP Port")
    parser.add_argument("--interval", type=float, default=0.02, help="Packet interval in seconds (0.02s = 50Hz)")
    
    args = parser.parse_args()
    run_simulation(args.ip, args.port, args.interval)
