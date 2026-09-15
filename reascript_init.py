"""
===============================================================================
REASCRIPT INITIALIZATION SCRIPT (REAPER Python API)
===============================================================================
Description:
    Programmatically creates and initializes a 4-track Air Band & Cinematic scoring
    environment in REAPER:
      - Track 1: 01_Strings_Atmosphere (MIDI Ch 1 -> Spitfire LABS / ReaSynth)
      - Track 2: 02_Brass_Tension (MIDI Ch 2 -> BBC Symphony / ReaSynth)
      - Track 3: 03_Air_Drums_and_Percussion (MIDI Ch 3 -> Air Drum Kit)
      - Track 4: 00_Soundtrack_BGM (Audio Track -> Drag & Drop MP3 / Backing Track)
    
Execution:
    Inside REAPER: Actions -> Show action list -> New action -> Load ReaScript...
    Select this script and click Run.
===============================================================================
"""

import sys
import os

# Import REAPER Python API bindings
try:
    from reaper_python import *
    IN_REAPER = True
except ImportError:
    IN_REAPER = False
    print("[WARNING] reaper_python module not found. Run this script within REAPER's ReaScript environment.")

def msg(text):
    """Outputs messages to the REAPER ReaScript console."""
    if IN_REAPER:
        RPR_ShowConsoleMsg(str(text) + "\n")
    else:
        print(text)

def setup_cinematic_session():
    if not IN_REAPER:
        msg("[ERROR] Cannot execute ReaScript calls outside REAPER DAW environment.")
        return

    RPR_Undo_BeginBlock()
    msg("==================================================")
    msg("INITIALIZING AIR BAND & BGM MUSIC ENGINE (4-TRACK)")
    msg("==================================================")

    # Track Configuration Matrix
    track_configs = [
        {
            "name": "01_Strings_Atmosphere",
            "vst": "VST3: LABS (Spitfire Audio)",
            "fallback": "VST: ReaSynth (Cockos)",
            "color": 0x334488,  # Deep Blue
            "vol": 0.85,
            "is_midi": True
        },
        {
            "name": "02_Brass_Tension",
            "vst": "VST3: BBC Symphony Orchestra (Spitfire Audio)",
            "fallback": "VST: ReaSynth (Cockos)",
            "color": 0x884433,  # Crimson Rust
            "vol": 0.75,
            "is_midi": True
        },
        {
            "name": "03_Air_Drums_and_Percussion",
            "vst": "VST3: LABS (Spitfire Audio)",
            "fallback": "VST: ReaSynth (Cockos)",
            "color": 0x338844,  # Vivid Emerald
            "vol": 0.95,
            "is_midi": True
        },
        {
            "name": "00_Soundtrack_BGM",
            "vst": None,        # Audio backing track (Drag & Drop MP3)
            "fallback": None,
            "color": 0x0088AA,  # Electric Cyan
            "vol": 0.85,
            "is_midi": False
        }
    ]

    existing_track_count = RPR_CountTracks(0)
    msg(f"Existing tracks in session: {existing_track_count}")

    created_tracks = []

    for i, cfg in enumerate(track_configs):
        track_idx = existing_track_count + i
        RPR_InsertTrackAtIndex(track_idx, True)
        track = RPR_GetTrack(0, track_idx)
        
        if not track:
            msg(f"[ERROR] Failed to create track at index {track_idx}")
            continue

        # 1. Set Track Name
        RPR_GetSetMediaTrackInfo_String(track, "P_NAME", cfg["name"], True)

        # 2. Set Track Volume
        RPR_SetMediaTrackInfo_Value(track, "D_VOL", cfg["vol"])

        # 3. Configure Input & Arming
        if cfg["is_midi"]:
            # Enable Record Arming (I_RECARM = 1)
            RPR_SetMediaTrackInfo_Value(track, "I_RECARM", 1)
            # Set Input to All MIDI Inputs, All Channels (4096 = MIDI flag)
            RPR_SetMediaTrackInfo_Value(track, "I_RECINPUT", 4096)
            # Enable Monitoring (I_RECMON = 1)
            RPR_SetMediaTrackInfo_Value(track, "I_RECMON", 1)
        else:
            # Audio BGM Track: No record arm needed
            RPR_SetMediaTrackInfo_Value(track, "I_RECARM", 0)

        # 4. Apply Track Color
        if cfg["color"]:
            RPR_SetMediaTrackInfo_Value(track, "I_CUSTOMCOLOR", cfg["color"] | 0x1000000)

        # 5. Instantiate VST Instrument (if applicable)
        if cfg["vst"]:
            fx_index = RPR_TrackFX_AddByName(track, cfg["vst"], False, -1)
            if fx_index < 0 and cfg["fallback"]:
                msg(f"[NOTICE] Preferred plugin '{cfg['vst']}' not found. Loading fallback '{cfg['fallback']}'...")
                fx_index = RPR_TrackFX_AddByName(track, cfg["fallback"], False, -1)

            if fx_index >= 0:
                fx_name_buf = RPR_TrackFX_GetFXName(track, fx_index, "", 256)[2]
                msg(f"[SUCCESS] Track '{cfg['name']}' -> FX [{fx_index}]: {fx_name_buf}")
            else:
                msg(f"[WARNING] Could not load VST on Track '{cfg['name']}'")
        else:
            msg(f"[SUCCESS] Audio Track '{cfg['name']}' ready for MP3/WAV Drag & Drop.")

        created_tracks.append(track)

    # Select all newly created tracks
    RPR_Main_OnCommand(40297, 0) # Unselect all
    for tr in created_tracks:
        RPR_SetTrackSelected(tr, True)

    RPR_Undo_EndBlock("Air Band & BGM Session Initialization", -1)
    RPR_UpdateArrange()
    msg("==================================================")
    msg("SETUP COMPLETE: 4 Tracks Ready in REAPER.")
    msg("  - Drag & Drop your MP3 onto '00_Soundtrack_BGM'")
    msg("==================================================")

if __name__ == "__main__":
    setup_cinematic_session()
