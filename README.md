# FL Studio Script
Currenly the script has mixer, fxs and plugin control, and some channel rack functions. I would still like to add playlist functions and use for real time arrangement. TODO Also I need to figure out how api loop clone and other functions work.
The workbench - diagnostic program is for helping with mapping and may serve as a virtual midi device in the future for some reasons like "sharing" the hardware device virtually to pass midi data /controls across mutliple applications, not yet implemented.
# APC40 Workbench (v0.2)

The LED colour layout is still not final: green/red/orange may read more like green/red/yellow in the current code, and the first physical LED may look more yellow/green than expected. If the colours look off, it is likely the current layout rather than the hardware; the LED colours still need to be corrected.

Standalone JUCE 8.0.12 app: draws the APC40 MkI from `apc40_layout.json`, lights controls from incoming MIDI,
sends LED test patterns, and walks you through a Learn wizard that exports `apc40_map.json`.

## Build (Windows / Visual Studio)
    cmake -B build -DJUCE_DIR=C:/path/to/JUCE-8.0.12
    cmake --build build --config Release
(or open the folder in Visual Studio and set the JUCE_DIR cache variable).

## Use
1. Close FL Studio (Windows lets only one app hold the APC40 MIDI port).
2. Pick MIDI In / Out (auto-selects ports containing "APC40"). Press things: they light on screen.
3. "Send Mode SysEx" with Generic selected, then "LED Test" or click any pad/button on screen to cycle its LED state (0-6). On the real unit state 1/2 is green, 3/4 red, 5/6 orange (odd states steady, even states blink). Bright room light washes the hardware LEDs toward pale yellow/peach.
4. "Start Learn": follow the cyan frame. Green dot = matches the reference map, orange = differs. "Export Map..." saves the result.
Edit `apc40_layout.json` (or rerun `make_layout.py`); a copy next to the .exe overrides the embedded one.

MIDI addresses are reconstructed from manual/protocol.
The mode SysEx version bytes are a best guess.

This is early development of an FL Studio MIDI script for APC40/FL integration, similar to the Novation FLPads workflow and other intended purposes. The current layout is mainly a diagnostic tool to confirm MIDI CC and SysEx data and mappings, and to validate a reusable layout. The LED colour layout still needs correction.

## v0.2 changes
- Learn now **resumes** (only unlearned controls); "Reset Learn" starts over. Finishing auto-saves `Documents\APC40Workbench\apc40_map.json`.
- CC/note-off spam is hidden unless "Verbose log" is ticked. Everything is also written, untrimmed, to `Documents\APC40Workbench\workbench.log`.
- "Copy Summary" puts a compact per-control report (address, ok/differs, CC range seen) on the clipboard; "Copy Log" copies the log box.
- "Probe" row: send any Note On / Note Off / CC to the APC40 (for ring LEDs, mode experiments).

## fl_script/APC40Diag
Stage 0 FL Studio script. Install path and setup are in the header of `device_APC40Diag.py`.
