#!/usr/bin/env python3
"""Generates apc40_layout.json (design space 1000 x 620). v2 - corrected from the owner's description of the real unit."""
import json, sys
W, H = 1000, 620
C = []
def add(**k): C.append(k)
def cx(c): return 40 + c * 62            # 9 columns: 0..7 tracks, 8 = scene/master column
def rx(i): return 650 + i * 85           # right-hand 4-column grid

def panel(label, x, y, w, h, fill="ff23262b", stroke="ff343841"):
    add(id=f"panel_{len(C)}", kind="panel", label=label, x=x, y=y, w=w, h=h, group="panel", fill=fill, stroke=stroke)
def text(t, x, y, w=60, h=10, size=7, align="center"):
    add(id=f"text_{len(C)}", kind="text", label=t, x=x, y=y, w=w, h=h, size=size, align=align, group="text")
def note(id, kind, label, desc, group, x, y, w, h, ch, num, size=7, **extra):
    add(id=id, kind=kind, label=label, desc=desc, group=group, x=x, y=y, w=w, h=h, msg="note", ch=ch, num=num, led=True, size=size, **extra)
def cc(id, kind, desc, group, x, y, w, h, ch, num, **extra):
    add(id=id, kind=kind, label="", desc=desc, group=group, x=x, y=y, w=w, h=h, msg="cc", ch=ch, num=num, size=7, **extra)

# ---- panels (drawn first) ----
panel("CLIP LAUNCH / MIXER", 6, 6, 566, 608)
panel("", 614, 378, 344, 74, fill="ff050506", stroke="ff3a3a3a")                 # black box behind device buttons 1-8
panel("TRACK CONTROL", 606, 10, 360, 176, fill="00000000", stroke="ffe6e6e6")   # white outline
panel("DEVICE CONTROL", 606, 270, 360, 144, fill="00000000", stroke="ffe6e6e6") # white line cuts through the black box

# ---- left: 9 columns ----
for r in range(5):
    for c in range(8):
        note(f"clip_r{r+1}_c{c+1}", "pad", "", f"Clip launch pad - row {r+1}, column {c+1}", "clip_grid", cx(c)-25, 18+r*42, 50, 32, c+1, 53+r)
for r in range(5):
    note(f"scene_{r+1}", "button", "", f"Scene launch {r+1} (column 9, row {r+1})", "scene", cx(8)-25, 18+r*42, 50, 32, 1, 82+r)
for c in range(8):
    note(f"clip_stop_{c+1}", "button", "STOP", f"Clip stop - track {c+1} (row 6)", "clip_stop", cx(c)-25, 228, 50, 32, c+1, 52)
note("stop_all", "button", "ALL", "Stop all clips (row 6, column 9)", "clip_stop", cx(8)-25, 228, 50, 32, 1, 81)
for c in range(8):
    note(f"track_select_{c+1}", "button", "SEL", f"Track selection - track {c+1} (row 7)", "track_select", cx(c)-25, 270, 50, 32, c+1, 51)
note("master_select", "button", "MASTER", "Master track selection (row 7, column 9)", "track_select", cx(8)-25, 270, 50, 32, 1, 80)
for gid, lab, nm, y, n in [("activator","ACT","Activator",312,50),("solo_cue","SOLO","Solo/Cue",334,49),("rec_arm","REC","Record/Trim",356,48)]:
    for c in range(8):
        note(f"{gid}_{c+1}", "button", lab, f"{nm} - track {c+1}", gid, cx(c)-22, y, 44, 16, c+1, n, 6)
cc("cue_level", "knob", "Cue level knob (column 9, beside solo/cue row)", "cue", cx(8)-18, 322, 36, 36, 1, 47)
text("CUE LEVEL", cx(8)-30, 361, 60, 9, 6)
for c in range(9):
    if c < 8: cc(f"fader_{c+1}", "fader", f"Track fader {c+1}", "faders", cx(c)-11, 388, 22, 204, c+1, 7)
    else:     cc("master_fader", "fader", "Master fader (9th slider)", "master", cx(c)-11, 388, 22, 204, 1, 14, color="ffff9500")

# ---- right: track control (2 x 4 knobs + Pan / Send A-C) ----
for i in range(8):
    cc(f"track_knob_{i+1}", "knob", f"Track control knob {i+1}", "track_knobs", rx(i % 4)-18, 26 + (i // 4) * 56, 36, 36, 1, 48+i)
for i, (lab, n) in enumerate([("PAN",87),("SEND A",88),("SEND B",89),("SEND C",90)]):
    note(f"tc_{lab.lower().replace(' ','_')}", "button", lab, f"Track control button '{lab}'", "track_mode", rx(i)-32, 138, 64, 26, 1, n)

# ---- movement: shift, bank select (odd-shaped cluster), tap tempo, nudge ----
note("shift", "button", "SHIFT", "Shift", "movement", 618, 214, 70, 26, 1, 98)
note("bank_up",    "button", "", "Bank select UP (centre top)",     "bank", 744, 196, 24, 24, 1, 94, arrow="up")
note("bank_down",  "button", "", "Bank select DOWN (centre bottom)","bank", 744, 230, 24, 24, 1, 95, arrow="down")
note("bank_left",  "button", "", "Bank select LEFT (left side)",    "bank", 716, 202, 26, 46, 1, 97, arrow="left")
note("bank_right", "button", "", "Bank select RIGHT (right side)",  "bank", 770, 202, 26, 46, 1, 96, arrow="right")
note("tap_tempo",  "button", "TAP", "Tap tempo",     "movement", 850, 196, 76, 24, 1, 99)
note("nudge_minus","button", "NUDGE -", "Nudge minus (below tap, left)",  "movement", 812, 230, 70, 24, 1, 101)
note("nudge_plus", "button", "NUDGE +", "Nudge plus (below tap, right)", "movement", 894, 230, 70, 24, 1, 100)

# ---- device control (2 x 4 knobs, buttons 1-4 inside the white line, 5-8 in the black box below it) ----
for i in range(8):
    cc(f"device_knob_{i+1}", "knob", f"Device control knob {i+1}", "device_knobs", rx(i % 4)-18, 286 + (i // 4) * 56, 36, 36, 1, 16+i)
rowA = ["CLIP/TRACK","DEVICE ON/OFF","DEVICE <","DEVICE >"]
rowB = ["DETAIL VIEW","REC QUANT","MIDI OVERDUB","METRONOME"]
for i in range(4):
    note(f"device_btn_{i+1}", "button", rowA[i], f"Device button {i+1} '{rowA[i]}' (under knobs {i+1} and {i+5})", "device_buttons", rx(i)-36, 384, 72, 24, 1, 58+i, 6, tag=str(i+1))
for i in range(4):
    note(f"device_btn_{i+5}", "button", rowB[i], f"Device button {i+5} '{rowB[i]}'", "device_buttons", rx(i)-36, 420, 72, 24, 1, 62+i, 6, tag=str(i+5))

# ---- transport: Play/Stop/Rec sit in the gaps between buttons 5-8, one row lower; crossfader centre-right ----
for i, (lab, n) in enumerate([("PLAY",91),("STOP",92),("REC",93)]):
    note(f"transport_{lab.lower()}", "button", lab, f"Transport {lab}", "transport", (rx(i)+rx(i+1))/2-24, 458, 48, 26, 1, n)
cc("crossfader", "hfader", "Crossfader", "crossfader", 700, 520, 200, 26, 1, 15)
text("CROSSFADER", 700, 549, 200, 9, 6)

for k in C: k["x"], k["y"], k["w"], k["h"] = float(k["x"]), float(k["y"]), float(k["w"]), float(k["h"])
json.dump(dict(name="Akai APC40 MkI", width=W, height=H, controls=C), open(sys.argv[1] if len(sys.argv) > 1 else "apc40_layout.json", "w"), indent=1)
print(len(C), "entries,", sum(1 for k in C if k.get("msg")), "MIDI controls")
