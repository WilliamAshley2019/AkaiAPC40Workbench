# APC40 Workbench (v0.1)

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

## Honest caveats
Layout v2 was corrected from the owner's description of the real unit. MIDI addresses are reconstructed from memory of the manual/protocol, not from a photo. The Learn wizard exists to catch what's wrong.
The mode SysEx version bytes are a best guess.
