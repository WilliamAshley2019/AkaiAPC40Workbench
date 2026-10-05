# APC40 Workbench (v0.1)
The LED colour layouts are currently wrong, but the LED function works, just not the right colour layout so if they don't match its not your unit its the code.

Standalone JUCE 8.0.12 app: draws the APC40 MkI from `apc40_layout.json`, lights controls from incoming MIDI,
sends LED test patterns, and walks you through a Learn wizard that exports `apc40_map.json`.

## Build (Windows / Visual Studio)
    cmake -B build -DJUCE_DIR=C:/path/to/JUCE-8.0.12
    cmake --build build --config Release
(or open the folder in Visual Studio and set the JUCE_DIR cache variable).

## Use
1. Close FL Studio (Windows lets only one app hold the APC40 MIDI port).
2. Pick MIDI In / Out (auto-selects ports containing "APC40"). Press things: they light on screen.
3. "Send Mode SysEx" with Generic selected, then "LED Test" or click any pad/button on screen to cycle its LED colour (0-6).
4. "Start Learn": follow the cyan frame. Green dot = matches the reference map, orange = differs. "Export Map..." saves the result.
Edit `apc40_layout.json` (or rerun `make_layout.py`); a copy next to the .exe overrides the embedded one.

MIDI addresses are reconstructed from manual/protocol
The mode SysEx version bytes are a best guess.



This is "early" development of a project to get a fl midi script working well between the apc40 and fl studio similar to the novation flpads function and some other intended peruposes. The current provided layout is for insuring midi cc and sysex data are correct and mapped properly. Since I thought it may be useful as a general diagnostic tool   and the layout might be reusable I thought I would upload it to github on the offchance the layout work and mappings being confirmed are useful.
