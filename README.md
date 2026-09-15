# Gesture Music REAPER: Physical Air Band & Generative Orchestral Conductor

A low-latency, multi-modal gesture music engine connecting physical movements, computer vision, and smartphone kinematics directly to **REAPER DAW** via MIDI and Open Sound Control (OSC).

---

## 🌟 Overview & Features

- **Multi-Modal Input Support**:
  - **Smartphone Hardware IMU**: Real-time 100 Hz accelerometer & gyroscope tracking via phone browser or the free Phyphox sensor app (<5ms latency, true G-force impulse detection).
  - **Hybrid Optical Flow + 3D Pose AI**: MediaPipe Full 3D Pose AI coupled with OpenCV DISOpticalFlow (Dense Inverse Search) for fast, blur-proof computer vision air drumming and conducting.
  - **Kinematics Simulation**: Built-in mock telemetry emitter for algorithmic testing and DAW modulation without physical hardware connected.
- **Dynamic Musical Intelligence**:
  - **Markov State Machine**: Automatically transitions between musical moods (`CALM_ATMOSPHERE`, `BUILDING_TENSION`, `CLIMAX_DREAD`, `RELEASE_DECAY`).
  - **Harmonic Voice-Leading Engine**: Adaptive cinematic D-minor chord progressions and bass lines triggered by physical movement altitude and wingspan.
  - **Expressive DAW Modulation**: Real-time MIDI CC11 (Expression Swell), CC91 (Reverb & Stereo Width), CC1 (Modulation Dynamics), and automated master track volume sweeps.
- **Automated REAPER Integration**:
  - 1-click Python ReaScript (`reascript_init.py`) to build and color-code the 4-track cinematic session with monitoring and VST fallbacks.
  - Custom OSC profile (`custom_gestures.ReaperOSC`) for native bi-directional REAPER control surface communication.

---

## 🥁 Physical Gesture & Sensor Mapping

| Physical Gesture | Sensor Metric / Detection | REAPER Voice & Routing | MIDI / OSC Output |
| :--- | :--- | :--- | :--- |
| 💥 **Forward Punch** | $+Z$ Forward Thrust Spike ($>2.8G$) / Optical Radial Divergence | **808 Sub-Drop Kick / Boom** | Note 36 (`C1`) on Ch 3 |
| 🥁 **Downward Hammer** | $-Y$ Impact Deceleration ($<-2.4G$) / Optical Downward Momentum | **Snare Drum** (Flat) / **Low Tom** (Tilted) | Note 38 (`D1`) / Note 45 (`A1`) on Ch 3 |
| 🌟 **Overhead Whip / Crash** | Gyro Velocity ($\omega > 350^\circ/\text{s}$) / High-Zone Optical Velocity | **Crash Cymbal** | Note 49 (`C#2`) on Ch 3 |
| 👏 **Air Clap** | Inward Opposing Optical Flow Vectors | **Handclap / Impact Accent** | Note 39 (`D#1`) on Ch 3 |
| 🎻 **Pitch Angle / Arm Altitude** | Elevation Angle ($0^\circ \rightarrow 75^\circ$) | **MIDI CC11 Expression Swell** + Harmonic Pad Chords + BGM Volume | CC11 on Ch 1 & 2 + OSC `/track/4/volume` |
| 🌊 **Roll Angle / Wingspan** | Roll Angle ($-45^\circ \rightarrow +45^\circ$) / Wrist Span | **MIDI CC91 Reverb Depth & Stereo Width** | CC91 on Ch 1 & 2 |

---

## 📐 4-Track REAPER Architecture

| Track # | Track Name | Channel | Instrument / Sound Source |
| :--- | :--- | :--- | :--- |
| **Track 1** | `01_Strings_Atmosphere` | MIDI Channel 1 (mido 0) | Spitfire LABS Strings / ReaSynth |
| **Track 2** | `02_Brass_Tension` | MIDI Channel 2 (mido 1) | BBC Symphony Orchestra Brass / ReaSynth |
| **Track 3** | `03_Air_Drums_and_Percussion` | MIDI Channel 3 (mido 2) | Air Drum Kit (Sub Kick, Snare, Toms, Crash, Clap) |
| **Track 4** | `00_Soundtrack_BGM` | Audio / Media Track | Drag & Drop MP3 Backing Track (Dynamic Swell) |

---

## 🚀 Quick Setup Guide

### 1. Prerequisites & Virtual MIDI Port
1. Install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html).
2. Open loopMIDI and create a new virtual port named: `GestureConductor`.
3. In REAPER:
   - Go to **Options $\rightarrow$ Preferences $\rightarrow$ Audio $\rightarrow$ MIDI Devices**.
   - Right-click `GestureConductor` under MIDI inputs $\rightarrow$ **Enable input** and **Enable input for control messages**.

### 2. Configure REAPER Session & OSC
1. **Initialize Tracks**:
   - In REAPER, open the Actions List (`?`).
   - Click **New action $\rightarrow$ Load ReaScript...** and select `reascript_init.py`.
   - Click **Run**. The 4-track session will be automatically generated and armed.
2. **(Optional) Install OSC Profile**:
   - Copy `custom_gestures.ReaperOSC` to `%APPDATA%\REAPER\OSC\`.
   - In REAPER: **Preferences $\rightarrow$ Control/OSC/web $\rightarrow$ Add**.
   - Select `OSC (Open Sound Control)`, choose `custom_gestures.ReaperOSC`, and set Listen Port to `8000`.

### 3. Python Environment Setup
```bash
# Clone the repository
git clone https://github.com/mushthaqazeez/gesture-music-reaper.git
cd gesture-music-reaper

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Verify MIDI Connectivity
Test your virtual MIDI port communication across all tracks:
```bash
python test_midi_output.py
```

---

## 🎮 Running the Music Engines

### Option A: Smartphone Web App Mode (No App Installation Needed)
Launches a local high-performance HTML5 mobile web app with live G-force meters:
```bash
python phone_motion_conductor.py
```
1. Connect your smartphone to the same Wi-Fi network as your PC.
2. Scan the terminal ASCII QR code or open `http://<your-pc-ip>:8080` in Safari (iOS) or Chrome (Android).
3. Tap **"CONNECT & START SENSORS"** and jam!

### Option B: Smartphone Phyphox Hardware Hub
Connects directly to the free open-source [Phyphox](https://phyphox.org/) app:
```bash
python smart_phone_hub.py
```
1. Open Phyphox on your phone $\rightarrow$ tap `+` $\rightarrow$ **"Add experiment from QR code"**.
2. Scan the on-screen QR code and press the **Play (▶)** button.

### Option C: Hybrid Optical Flow + 3D Pose Webcam Conductor
Uses your webcam with MediaPipe 3D Pose + DISOpticalFlow to conduct with your hands and body:
```bash
python webcam_gesture_conductor.py --camera 0
```
- Press `c` while running to switch between available cameras.
- Press `m` to toggle video mirror mode.
- Press `q` to quit.

### Option D: External Algorithmic Conductor & Simulation
Run the standalone Markov algorithmic conductor paired with the synthetic kinematics emitter:
```bash
# Terminal 1: Launch Algorithmic Conductor
python osc_conductor.py --listen-port 5005 --reaper-port 8000

# Terminal 2: Broadcast simulated motion dynamics
python mock_kinematics_emitter.py --port 5005
```

---

## 📁 Repository Structure

```
├── .gitignore                   # Ignores virtual envs, bytecode, local certificates & keys
├── README.md                    # Comprehensive documentation and setup guide
├── requirements.txt             # Python dependencies
├── custom_gestures.ReaperOSC    # Custom REAPER OSC surface definitions
├── reascript_init.py            # REAPER ReaScript automated 4-track template builder
├── test_midi_output.py          # Diagnostic MIDI channel and trigger validation utility
├── phone_motion_conductor.py    # Dual Web App + Native UDP OSC smartphone engine
├── smart_phone_hub.py           # Universal Phyphox HTTP/XML experiment server & IMU hub
├── phyphox_air_drummer.py       # Wi-Fi polling Phyphox IMU motion client
├── webcam_gesture_conductor.py  # Computer vision air conductor (MediaPipe + DISOpticalFlow)
├── osc_conductor.py             # Algorithmic Markov chain and cinematic chord generator
├── mock_kinematics_emitter.py   # Synthesizer for mock motion streams and parameter modulation
├── reaper_air_band.phyphox      # Phyphox experiment configuration file
├── pose_landmarker_full.task    # MediaPipe high-accuracy 3D pose model
└── pose_landmarker.task         # MediaPipe standard 3D pose model
```

---

## 📜 License
MIT License. Open for musicians, developers, and researchers.
