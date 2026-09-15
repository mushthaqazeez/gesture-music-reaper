"""
===============================================================================
HYBRID DENSE OPTICAL FLOW + 3D POSE AIR BAND ENGINE (OPTION B: KINETIC IMPULSE)
===============================================================================
Description:
    Combines MediaPipe Full 3D Pose AI with OpenCV DISOpticalFlow (Dense Inverse
    Search Optical Flow) for ultra-fast, blur-proof physical gesture air drumming:
      - 💥 Forward Punch -> Radial Optical Flow Divergence + Thrust -> 808 Sub Boom (/gesture/punch)
      - 🥁 Downward Hammer -> Vertical Optical Flow Momentum ($M_y$) -> Snare [L] / Tom [R] (/gesture/hammer)
      - 🌟 Overhead Crash -> High-Zone Optical Velocity Whip -> Crash Cymbal (/gesture/crash)
      - 👏 Air Clap -> Inward Opposing Optical Flow -> Handclap Accent (/gesture/clap)
      - 🎻 Arm Altitude & Wingspan -> Continuous Chords & BGM Soundtrack Swell (/kinematics/*)

    Features automatic camera device discovery and live 'c' key camera switching.

Usage:
    .venv\\Scripts\\python.exe webcam_gesture_conductor.py --camera 1 --port 5005
===============================================================================
"""

import cv2
import numpy as np
import time
import math
import socket
import struct
import argparse
import os
import urllib.request
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Full 3D Pose Model
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
POSE_MODEL_FILE = os.path.join(SCRIPT_DIR, "pose_landmarker_full.task")

# MediaPipe Upper Body Skeleton Connections
UPPER_BODY_CONNECTIONS = [
    (11, 12),          # Shoulder line
    (11, 23), (12, 24), # Torso sides
    (23, 24),          # Hip line
    (11, 13), (13, 15), # Left Arm (shoulder -> elbow -> wrist)
    (12, 14), (14, 16), # Right Arm
    (15, 17), (15, 19), (15, 21), # Left Hand
    (16, 18), (16, 20), (16, 22), # Right Hand
    (0, 11), (0, 12)   # Head to shoulders
]

# =============================================================================
# CAMERA UTILITIES (Auto-detection & Device Discovery)
# =============================================================================
def get_available_cameras(max_tested=6):
    """Scans and returns list of accessible camera device indices."""
    available = []
    for i in range(max_tested):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
            cap.release()
    return available

def open_best_camera(preferred_idx=0):
    """Opens preferred camera index or auto-discovers first functional webcam."""
    cap = cv2.VideoCapture(preferred_idx)
    if cap.isOpened():
        ret, _ = cap.read()
        if ret:
            return cap, preferred_idx
        cap.release()

    # Auto-scan alternatives
    print(f"[CAMERA SETUP] Camera index {preferred_idx} not capturing. Scanning connected cameras...")
    for idx in range(6):
        if idx == preferred_idx:
            continue
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[CAMERA SETUP] >>> Found functional webcam at Camera Index [{idx}]! Connecting... <<<")
                return cap, idx
            cap.release()

    return None, -1

# =============================================================================
# OSC PACKET BUILDER
# =============================================================================
class OSCMessageBuilder:
    @staticmethod
    def build_msg(address, *args):
        addr_bytes = address.encode('utf-8') + b'\x00'
        while len(addr_bytes) % 4 != 0:
            addr_bytes += b'\x00'

        type_tag = ','
        val_bytes = b''

        for arg in args:
            if isinstance(arg, float):
                type_tag += 'f'
                val_bytes += struct.pack('>f', float(arg))
            elif isinstance(arg, int):
                type_tag += 'i'
                val_bytes += struct.pack('>i', int(arg))
            elif isinstance(arg, str):
                type_tag += 's'
                s_bytes = arg.encode('utf-8') + b'\x00'
                while len(s_bytes) % 4 != 0:
                    s_bytes += b'\x00'
                val_bytes += s_bytes

        tag_bytes = type_tag.encode('ascii') + b'\x00'
        while len(tag_bytes) % 4 != 0:
            tag_bytes += b'\x00'

        return addr_bytes + tag_bytes + val_bytes


def ensure_pose_model():
    """Ensures high-accuracy pose model is present locally."""
    if not os.path.exists(POSE_MODEL_FILE):
        print(f"[SETUP] Downloading MediaPipe Full Pose model '{POSE_MODEL_FILE}'...")
        try:
            urllib.request.urlretrieve(POSE_MODEL_URL, POSE_MODEL_FILE)
            print(f"[SETUP] Downloaded '{POSE_MODEL_FILE}' ({os.path.getsize(POSE_MODEL_FILE)} bytes).")
        except Exception as e:
            print(f"[ERROR] Failed to download pose model: {e}")
            raise e


# =============================================================================
# VISUAL SHOCKWAVE EFFECT
# =============================================================================
class ShockwaveFX:
    def __init__(self, x, y, max_radius=75, color=(0, 255, 255), label="HIT", duration=0.32):
        self.x = int(x)
        self.y = int(y)
        self.max_radius = max_radius
        self.color = color
        self.label = label
        self.duration = duration
        self.start_time = time.time()
        self.alive = True

    def draw(self, frame):
        elapsed = time.time() - self.start_time
        progress = elapsed / self.duration
        if progress >= 1.0:
            self.alive = False
            return

        radius = int(10 + progress * (self.max_radius - 10))
        thickness = max(int(4 * (1.0 - progress)), 1)

        # Expanding Shockwave Rings
        cv2.circle(frame, (self.x, self.y), radius, self.color, thickness, cv2.LINE_AA)
        cv2.circle(frame, (self.x, self.y), max(radius // 2, 4), (255, 255, 255), 1, cv2.LINE_AA)

        # Floating Hit Label
        label_y = self.y - radius - 10
        if label_y > 20:
            cv2.putText(frame, self.label, (self.x - 50, label_y),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, self.label, (self.x - 50, label_y),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, self.color, 1, cv2.LINE_AA)


# =============================================================================
# HYBRID OPTICAL FLOW + SKELETAL AIR BAND CONDUCTOR
# =============================================================================
class HybridAirBandConductor:
    def __init__(self, target_ip, target_port, camera_idx=0, mirror=True, sensitivity=1.0):
        self.target_ip = target_ip
        self.target_port = target_port
        self.camera_idx = camera_idx
        self.mirror = mirror
        self.sensitivity = sensitivity

        # OSC Socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Ensure Model
        ensure_pose_model()

        # MediaPipe Pose Detector (Full Model)
        base_options = python.BaseOptions(model_asset_path=POSE_MODEL_FILE)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            min_pose_detection_confidence=0.55,
            min_pose_presence_confidence=0.55,
            min_tracking_confidence=0.55
        )
        self.pose_detector = vision.PoseLandmarker.create_from_options(options)

        # OpenCV DISOpticalFlow Engine (Fast Preset)
        self.dis_flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        self.dis_flow.setUseSpatialPropagation(True)
        self.prev_gray_half = None

        # Continuous kinematics smoothing
        self.prev_time = time.time()
        self.prev_body_points = []
        self.smooth_vel = 0.0
        self.smooth_alt = 0.5
        self.smooth_dist = 0.5
        self.smooth_open = 1.0

        # Impulse State Machines
        self.punch_armed = {0: True, 1: True}
        self.hammer_armed = {0: False, 1: False}
        self.hammer_peak_flow = {0: 0.0, 1: 0.0}
        self.last_punch_time = {0: 0.0, 1: 0.0}
        self.last_hammer_time = {0: 0.0, 1: 0.0}
        self.last_crash_time = 0.0
        self.last_clap_time = 0.0
        self.clap_armed = True
        self.prev_wrist_dist = 0.5

        # Visual Effects & Combo State
        self.fx_list = []
        self.combo_count = 0
        self.last_hit_label = "READY"
        self.last_hit_time = 0.0

        # Flow vectors for visual display
        self.hand_flow_vectors = {0: (0.0, 0.0), 1: (0.0, 0.0)}
        self.hand_flow_magnitudes = {0: 0.0, 1: 0.0}

        print(f"[HYBRID ENGINE] DISOpticalFlow + MediaPipe 3D Pose AI online.")
        print(f"[HYBRID ENGINE] Broadcasting OSC telemetry to {target_ip}:{target_port}")

    def send_osc(self, address, *args):
        try:
            pkt = OSCMessageBuilder.build_msg(address, *args)
            self.sock.sendto(pkt, (self.target_ip, self.target_port))
        except Exception:
            pass

    def add_hit_fx(self, x, y, max_radius=80, color=(0, 255, 255), label="HIT"):
        self.fx_list.append(ShockwaveFX(x, y, max_radius, color, label))
        self.combo_count += 1
        self.last_hit_label = label
        self.last_hit_time = time.time()

    def run(self):
        cap, active_cam_idx = open_best_camera(self.camera_idx)
        if cap is None:
            print("[ERROR] No functional webcam devices found on this PC!")
            return
        self.camera_idx = active_cam_idx

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 60)

        print("==================================================================")
        print(f"HYBRID OPTICAL FLOW AIR BAND RUNNING ON CAMERA [{self.camera_idx}]:")
        print("  - Press 'c' to cycle to next connected webcam")
        print("  💥 Forward Punch -> Radial Flow Divergence -> 808 Sub Kick Boom")
        print("  🥁 Downward Hammer -> Downward Momentum (My) -> Snare / Tom")
        print("  🌟 Overhead Whip -> Upper Radial Flow -> Crash Cymbal")
        print("  👏 Air Clap -> Inward Opposing Flow -> Handclap Accent")
        print("  🎻 Posture Swell -> Strings, Brass & Master BGM Soundtrack")
        print("==================================================================")

        fps_counter = 0
        fps_start = time.time()
        current_fps = 60.0

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("[WARNING] Frame grab failed. Attempting reconnect...")
                    time.sleep(0.1)
                    continue

                now = time.time()
                dt = max(now - self.prev_time, 0.001)
                self.prev_time = now

                if self.mirror:
                    frame = cv2.flip(frame, 1)

                h, w, _ = frame.shape

                # 1. Optical Flow on Half-Resolution Frame (< 3ms CPU)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray_half = cv2.resize(gray, (320, 240), interpolation=cv2.INTER_LINEAR)

                flow_field = None
                if self.prev_gray_half is not None:
                    flow_half = self.dis_flow.calc(self.prev_gray_half, gray_half, None)
                    flow_field = cv2.resize(flow_half, (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
                self.prev_gray_half = gray_half

                # 2. MediaPipe Full 3D Pose Detection
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                pose_result = self.pose_detector.detect(mp_image)
                pose_landmarks_list = pose_result.pose_landmarks
                body_detected = len(pose_landmarks_list) > 0

                raw_vel = 0.0
                raw_alt = self.smooth_alt
                raw_dist = self.smooth_dist
                raw_open = 1.0

                if body_detected and flow_field is not None:
                    pose = pose_landmarks_list[0]

                    # Key Landmarks
                    l_sh, r_sh = pose[11], pose[12]
                    l_el, r_el = pose[13], pose[14]
                    l_wr, r_wr = pose[15], pose[16]
                    l_idx, r_idx = pose[19], pose[20]

                    shoulder_w = max(math.hypot(l_sh.x - r_sh.x, l_sh.y - r_sh.y), 0.12)
                    shoulder_y = (l_sh.y + r_sh.y) / 2.0
                    wrist_avg_y = (l_wr.y + r_wr.y) / 2.0

                    # Continuous Altitude & Wingspan
                    alt_norm = (shoulder_y + 0.30 - wrist_avg_y) / 0.60
                    raw_alt = min(max(alt_norm, 0.0), 1.0)

                    wrist_dist = math.hypot(l_wr.x - r_wr.x, l_wr.y - r_wr.y)
                    dist_norm = (wrist_dist / shoulder_w - 0.6) / 1.8
                    raw_dist = min(max(dist_norm, 0.0), 1.0)

                    # Continuous Upper Body Velocity
                    curr_body_points = [
                        (l_wr.x, l_wr.y), (r_wr.x, r_wr.y),
                        (l_el.x, l_el.y), (r_el.x, r_el.y),
                        (l_sh.x, l_sh.y), (r_sh.x, r_sh.y)
                    ]
                    if len(self.prev_body_points) == len(curr_body_points):
                        dists = [math.hypot(c[0] - p[0], c[1] - p[1]) for c, p in zip(curr_body_points, self.prev_body_points)]
                        raw_vel = (sum(dists) / len(dists)) / dt * 0.50
                    self.prev_body_points = curr_body_points

                    # Palm Openness Approximation
                    l_hand_len = math.hypot(l_idx.x - l_wr.x, l_idx.y - l_wr.y)
                    r_hand_len = math.hypot(r_idx.x - r_wr.x, r_idx.y - r_wr.y)
                    raw_open = min(max(((l_hand_len + r_hand_len) / (2.0 * shoulder_w) - 0.15) / 0.25, 0.0), 1.0)

                    # =========================================================
                    # KINETIC OPTICAL FLOW IMPULSE EXTRACTION
                    # =========================================================
                    wrists = {
                        0: (l_wr.x, l_wr.y, l_wr.z, l_sh.x, l_sh.y), # Left Hand
                        1: (r_wr.x, r_wr.y, r_wr.z, r_sh.x, r_sh.y)  # Right Hand
                    }

                    roi_rad = int(max(shoulder_w * w * 0.35, 30))

                    for hand_idx, (wx, wy, wz, sx, sy) in wrists.items():
                        cx, cy = int(wx * w), int(wy * h)
                        x1, x2 = max(cx - roi_rad, 0), min(cx + roi_rad, w)
                        y1, y2 = max(cy - roi_rad, 0), min(cy + roi_rad, h)

                        if x2 > x1 and y2 > y1:
                            roi_flow = flow_field[y1:y2, x1:x2]
                            flow_u = roi_flow[:, :, 0]
                            flow_v = roi_flow[:, :, 1]

                            # Mean Optical Flow Vectors
                            mean_u = float(np.mean(flow_u))
                            mean_v = float(np.mean(flow_v)) # Downward is positive
                            flow_mag = math.hypot(mean_u, mean_v)
                            self.hand_flow_vectors[hand_idx] = (mean_u, mean_v)
                            self.hand_flow_magnitudes[hand_idx] = flow_mag

                            # Radial Divergence (Forward Punch Expansion metric)
                            grid_y, grid_x = np.ogrid[y1-cy:y2-cy, x1-cx:x2-cx]
                            dist_sq = grid_x**2 + grid_y**2 + 1.0
                            rad_div = float(np.mean((grid_x * flow_u + grid_y * flow_v) / np.sqrt(dist_sq)))

                            # Arm Extension Ratio
                            arm_ext = math.hypot(wx - sx, wy - sy) / shoulder_w

                            # -------------------------------------------------
                            # A. FORWARD PUNCH DETECTION (Boom / 808 Kick)
                            # -------------------------------------------------
                            if arm_ext < 0.60:
                                self.punch_armed[hand_idx] = True

                            punch_metric = rad_div * 1.5 + flow_mag * 0.5
                            punch_thresh = 6.0 * (1.0 / self.sensitivity)

                            if self.punch_armed[hand_idx] and (punch_metric > punch_thresh) and (arm_ext > 0.68) and (now - self.last_punch_time[hand_idx] > 0.22):
                                self.punch_armed[hand_idx] = False
                                self.last_punch_time[hand_idx] = now
                                punch_vel = min(max(punch_metric / 15.0, 0.5), 1.0)
                                self.send_osc("/gesture/punch", float(punch_vel), int(hand_idx))
                                self.add_hit_fx(cx, cy, max_radius=90,
                                                color=(50, 80, 255), # Vivid Red-Orange
                                                label="💥 PUNCH BOOM!")

                            # -------------------------------------------------
                            # B. HAMMER DROP DETECTION (Snare / Tom)
                            # -------------------------------------------------
                            downward_flow = max(mean_v, 0.0)

                            if wy < shoulder_y + 0.08:
                                self.hammer_armed[hand_idx] = True
                                self.hammer_peak_flow[hand_idx] = 0.0

                            if self.hammer_armed[hand_idx]:
                                if downward_flow > self.hammer_peak_flow[hand_idx]:
                                    self.hammer_peak_flow[hand_idx] = downward_flow

                                hammer_thresh = 7.5 * (1.0 / self.sensitivity)
                                if (self.hammer_peak_flow[hand_idx] > hammer_thresh) and (downward_flow < self.hammer_peak_flow[hand_idx] * 0.45) and (now - self.last_hammer_time[hand_idx] > 0.20):
                                    self.hammer_armed[hand_idx] = False
                                    self.last_hammer_time[hand_idx] = now
                                    strike_vel = min(max(self.hammer_peak_flow[hand_idx] / 18.0, 0.5), 1.0)
                                    self.send_osc("/gesture/hammer", float(strike_vel), int(hand_idx))

                                    if hand_idx == 0:
                                        self.add_hit_fx(cx, cy, max_radius=75,
                                                        color=(0, 240, 255), # Cyan Snare
                                                        label="🥁 SNARE HIT!")
                                    else:
                                        self.add_hit_fx(cx, cy, max_radius=80,
                                                        color=(0, 220, 100), # Green Tom
                                                        label="🥁 TOM HIT!")

                            # -------------------------------------------------
                            # C. OVERHEAD CRASH CYMBAL
                            # -------------------------------------------------
                            if (wy < shoulder_y - 0.20) and (flow_mag > 10.0 * (1.0 / self.sensitivity)) and (now - self.last_crash_time > 0.38):
                                self.last_crash_time = now
                                crash_vel = min(max(flow_mag / 20.0, 0.6), 1.0)
                                self.send_osc("/gesture/crash", float(crash_vel))
                                self.add_hit_fx(cx, cy, max_radius=110,
                                                color=(0, 215, 255), # Gold
                                                label="🌟 CRASH CYMBAL!")

                    # ---------------------------------------------------------
                    # D. AIR CLAP / INWARD CONVERGING FLOW
                    # ---------------------------------------------------------
                    curr_dist = math.hypot(l_wr.x - r_wr.x, l_wr.y - r_wr.y)
                    if curr_dist > 0.38 * shoulder_w:
                        self.clap_armed = True

                    u_left = self.hand_flow_vectors[0][0]
                    u_right = self.hand_flow_vectors[1][0]
                    converge_flow = (u_left - u_right)

                    if self.clap_armed and (converge_flow > 9.0 * (1.0 / self.sensitivity)) and (curr_dist < 0.16 * shoulder_w) and (now - self.last_clap_time > 0.28):
                        self.clap_armed = False
                        self.last_clap_time = now
                        clap_vel = min(max(converge_flow / 20.0, 0.5), 1.0)
                        self.send_osc("/gesture/clap", float(clap_vel))
                        mid_x = int((l_wr.x + r_wr.x) / 2.0 * w)
                        mid_y = int((l_wr.y + r_wr.y) / 2.0 * h)
                        self.add_hit_fx(mid_x, mid_y, max_radius=95,
                                        color=(255, 100, 220), # Magenta
                                        label="👏 AIR CLAP!")
                    self.prev_wrist_dist = curr_dist

                # Smooth Continuous Parameters
                alpha_vel = 0.35
                alpha_pos = 0.25
                self.smooth_vel = min(max(alpha_vel * raw_vel + (1 - alpha_vel) * self.smooth_vel, 0.0), 1.0)
                self.smooth_alt = min(max(alpha_pos * raw_alt + (1 - alpha_pos) * self.smooth_alt, 0.0), 1.0)
                self.smooth_dist = min(max(alpha_pos * raw_dist + (1 - alpha_pos) * self.smooth_dist, 0.0), 1.0)
                self.smooth_open = min(max(alpha_pos * raw_open + (1 - alpha_pos) * self.smooth_open, 0.0), 1.0)

                # Continuous Stream to Conductor Server
                self.send_osc("/kinematics", self.smooth_vel)
                self.send_osc("/kinematics/velocity", self.smooth_vel)
                self.send_osc("/kinematics/altitude", self.smooth_alt)
                self.send_osc("/kinematics/distance", self.smooth_dist)
                self.send_osc("/kinematics/openness", self.smooth_open)

                # RENDER SKELETON & OPTICAL FLOW NEEDLES
                if body_detected:
                    self._draw_pose_skeleton(frame, pose_landmarks_list[0])
                    self._draw_flow_vectors(frame, pose_landmarks_list[0])

                # RENDER SHOCKWAVE FX
                self.fx_list = [fx for fx in self.fx_list if fx.alive]
                for fx in self.fx_list:
                    fx.draw(frame)

                if now - self.last_hit_time > 4.0:
                    self.combo_count = 0

                # FPS Calculation
                fps_counter += 1
                if now - fps_start >= 1.0:
                    current_fps = fps_counter / (now - fps_start)
                    fps_counter = 0
                    fps_start = now

                # RENDER HUD
                self._draw_hud(frame, current_fps, body_detected)

                cv2.imshow("Hybrid Optical Flow Air Band Engine", frame)

                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    print("\n[HYBRID ENGINE] Stopping webcam capture...")
                    break
                elif key == ord('c'):
                    # Live switch to next camera index
                    next_idx = (self.camera_idx + 1) % 4
                    print(f"\n[CAMERA] 'c' key pressed -> Switching to Camera Index [{next_idx}]...")
                    cap.release()
                    new_cap, actual_idx = open_best_camera(next_idx)
                    if new_cap:
                        cap = new_cap
                        self.camera_idx = actual_idx
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_FPS, 60)
                        print(f"[CAMERA] Successfully switched to Camera [{self.camera_idx}]!")

        except KeyboardInterrupt:
            print("\n[HYBRID ENGINE] Keyboard interrupt.")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.sock.close()

    def _draw_pose_skeleton(self, frame, landmarks):
        h, w, _ = frame.shape
        pts = {}
        indices = [0, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
        for idx in indices:
            lm = landmarks[idx]
            pts[idx] = (int(lm.x * w), int(lm.y * h))

        for p1_idx, p2_idx in UPPER_BODY_CONNECTIONS:
            if p1_idx in pts and p2_idx in pts:
                cv2.line(frame, pts[p1_idx], pts[p2_idx], (0, 220, 255), 2, cv2.LINE_AA)

        for idx, pt in pts.items():
            if idx in [15, 16]: # Wrists
                cv2.circle(frame, pt, 9, (255, 0, 255), -1)
                cv2.circle(frame, pt, 12, (255, 255, 255), 2)
            elif idx in [13, 14]: # Elbows
                cv2.circle(frame, pt, 6, (0, 255, 100), -1)
            elif idx in [11, 12]: # Shoulders
                cv2.circle(frame, pt, 6, (255, 180, 0), -1)

    def _draw_flow_vectors(self, frame, landmarks):
        h, w, _ = frame.shape
        wrists = {0: landmarks[15], 1: landmarks[16]}
        for hand_idx, lm in wrists.items():
            cx, cy = int(lm.x * w), int(lm.y * h)
            u, v = self.hand_flow_vectors[hand_idx]
            mag = self.hand_flow_magnitudes[hand_idx]

            end_x = int(cx + u * 3.5)
            end_y = int(cy + v * 3.5)
            arrow_color = (0, 255, 255) if mag > 6.0 else (100, 100, 200)
            cv2.arrowedLine(frame, (cx, cy), (end_x, end_y), arrow_color, 2, tipLength=0.3)

            ring_r = int(min(mag * 3.0 + 14, 50))
            cv2.circle(frame, (cx, cy), ring_r, arrow_color, 1, cv2.LINE_AA)

    def _draw_hud(self, frame, fps, body_detected):
        h, w, _ = frame.shape

        # Main Box Overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (370, 210), (15, 15, 25), -1)
        # Combo Box (Top Right)
        cv2.rectangle(overlay, (w - 240, 10), (w - 10, 90), (20, 15, 30), -1)
        cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)

        # Border Outlines
        cv2.rectangle(frame, (10, 10), (370, 210), (70, 70, 110), 1)
        cv2.rectangle(frame, (w - 240, 10), (w - 10, 90), (140, 60, 200), 1)

        # Titles
        cv2.putText(frame, "HYBRID OPTICAL FLOW AIR BAND", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)
        status_text = f"FPS: {fps:.1f}  |  Cam: [{self.camera_idx}] ('c' to switch)  |  DIS-Flow: ON"
        cv2.putText(frame, status_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(frame, f"OSC: {self.target_ip}:{self.target_port}  |  REAPER 4-Track", (20, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 200, 255), 1, cv2.LINE_AA)

        # Continuous Meters
        self._draw_bar(frame, 20, 88,  "BAND VELOCITY", self.smooth_vel, (50, 220, 255))
        self._draw_bar(frame, 20, 118, "PAD ALTITUDE",  self.smooth_alt, (50, 255, 120))
        self._draw_bar(frame, 20, 148, "WINGSPAN WIDTH", self.smooth_dist, (220, 100, 255))
        self._draw_bar(frame, 20, 178, "BGM MASTER SWELL", self.smooth_alt, (0, 200, 255))

        # Guide Legend (Bottom Left)
        cv2.putText(frame, "💥 Punch=Boom  🥁 Hammer=Snare/Tom  🌟 High=Crash  👏 Clap=Accent  'c'=Switch Cam",
                    (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)

        # Combo Badge
        combo_color = (0, 230, 255) if self.combo_count > 5 else (180, 180, 180)
        cv2.putText(frame, f"STREAK: x{self.combo_count}", (w - 225, 35),
                    cv2.FONT_HERSHEY_DUPLEX, 0.65, combo_color, 1, cv2.LINE_AA)
        cv2.putText(frame, f"LAST: {self.last_hit_label}", (w - 225, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"KINETIC FLOW: {max(self.hand_flow_magnitudes.values()):.1f} px/f", (w - 225, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 220, 140), 1, cv2.LINE_AA)

    def _draw_bar(self, frame, x, y, label, val, color):
        cv2.putText(frame, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (220, 220, 220), 1, cv2.LINE_AA)
        bar_x = x + 180
        bar_y = y - 10
        bar_w = 150
        bar_h = 10
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (30, 30, 45), -1)
        fill_w = int(val * bar_w)
        if fill_w > 0:
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), color, -1)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (70, 70, 90), 1)


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid Optical Flow + 3D Pose Air Band Engine")
    parser.add_argument("--ip",          default="127.0.0.1", help="Target OSC IP")
    parser.add_argument("--port",        type=int, default=5005, help="Target OSC Port")
    parser.add_argument("--camera",      type=int, default=1, help="Webcam device index (default: 1)")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="Hit sensitivity multiplier (default: 1.0)")
    parser.add_argument("--no-mirror",   action="store_true", help="Disable mirror mode")
    args = parser.parse_args()

    conductor = HybridAirBandConductor(
        target_ip=args.ip,
        target_port=args.port,
        camera_idx=args.camera,
        mirror=not args.no_mirror,
        sensitivity=args.sensitivity
    )
    conductor.run()
