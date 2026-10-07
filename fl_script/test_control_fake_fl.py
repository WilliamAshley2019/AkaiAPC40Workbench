import sys, types, importlib
sent, calls = [], []
def mod(name, **kw):
    m = types.ModuleType(name); m.__dict__.update(kw); sys.modules[name] = m; return m

# ---- fake FL state ----
class P:  # plugin
    def __init__(s, name, n): s.name, s.vals, s.preset = name, [i/ n for i in range(n)], 0
PLUG = {(2, 2): P("Fruity Parametric EQ 2", 40), (3, 0): P("Fruity Reeverb 2", 10), (4, 1): P("Fruity Limiter", 12)}
T = {t: dict(vol=0.8, pan=0.0, mute=False, solo=False, arm=False) for t in range(0, 30)}
state = dict(track=1)
def pset(v, p, i, s=-1): PLUG[(i, s)].vals[p] = v; calls.append(("set", p, round(v, 3), i, s))
mod("device", midiOutMsg=lambda m: sent.append(("msg", m)), midiOutSysex=lambda b: sent.append(("sysex", bytes(b))))
mod("plugins", isValid=lambda i, s=-1: (i, s) in PLUG, getPluginName=lambda i, s=-1: PLUG[(i, s)].name,
    getParamCount=lambda i, s=-1: len(PLUG[(i, s)].vals), getParamName=lambda p, i, s=-1: "P%d" % p,
    getParamValue=lambda p, i, s=-1: PLUG[(i, s)].vals[p], setParamValue=pset,
    getParamValueString=lambda p, i, s=-1: "%d%%" % (PLUG[(i, s)].vals[p] * 100),
    nextPreset=lambda i, s=-1: calls.append(("next", i, s)), prevPreset=lambda i, s=-1: calls.append(("prev", i, s)))
def tog(key): return lambda t, v=-1: (calls.append((key, t)), T[t].__setitem__(key, not T[t][key]))
mod("mixer", trackNumber=lambda: state["track"], setActiveTrack=lambda t: (state.__setitem__("track", t), calls.append(("active", t))),
    getTrackVolume=lambda t, m=0: T[t]["vol"], setTrackVolume=lambda t, v, p=0: (T[t].__setitem__("vol", v), calls.append(("vol", t, round(v, 3)))),
    getTrackPan=lambda t: T[t]["pan"], setTrackPan=lambda t, v, p=0: (T[t].__setitem__("pan", v), calls.append(("pan", t, round(v, 3)))),
    isTrackMuted=lambda t: T[t]["mute"], isTrackSolo=lambda t: T[t]["solo"], isTrackArmed=lambda t: T[t]["arm"],
    focusEditor=lambda t, s: calls.append(("focus", t, s)), muteTrack=tog("mute"), soloTrack=tog("solo"), armTrack=tog("arm"))
mod("ui", setHintMsg=lambda s: calls.append(("hint", s)))
import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fl_script", "APC40Control"))
import device_APC40Control as d

class Ev:
    def __init__(s, st, d1, d2): s.status, s.data1, s.data2, s.handled = st, d1, d2, False
def press(ch, note):
    e = Ev(0x90 | ch, note, 127); d.OnMidiMsg(e); assert e.handled; d.OnMidiMsg(Ev(0x80 | ch, note, 127))
def cc(ch, num, val): e = Ev(0xB0 | ch, num, val); d.OnMidiMsg(e); assert e.handled
def led(ch, note):  # last LED state sent
    return d._app.led_sent.get((ch, note))
def clear(): sent.clear(); calls.clear()

# 1 init: sysex mode 0x42, mixer mode, Pan LED on
d.OnInit(); assert sent[0][0] == "sysex" and sent[0][1][7] == 0x42
assert led(0, 87) == 1 and led(0, 88) == 0, "mode LEDs"
print("1 init ok; messages on init:", len(sent))

# 2 FX mode via Send A: matrix shows presence; selected default (track1 slot0, empty) = red cursor
press(0, 88); a = d._app
assert a.mode == "fx"
assert led(1, 55) == 1, "EQ -> tone -> green"                # col1=track2, row2 -> note 55
assert led(0, 53) == 4, "selected empty slot -> red blink"
assert led(2, 53) == 5 and led(2, 54) == 0, "Reeverb -> time/space -> orange; empty slot off"
assert led(3, 54) == 3, "Limiter (track4 slot2) -> dynamics -> red"
print("2 fx matrix LEDs ok")

# 3 press matrix pad: select track2 slot3
clear(); press(1, 55)
assert (a.sel_track, a.sel_slot, a.pcount) == (2, 2, 40) and ("active", 2) in calls
assert led(1, 55) == 2, "selected EQ -> green BLINK (colour kept, blink = selected)"
assert ("focus", 2, 2) in calls, "plugin window focus attempted"
assert d._app.cc_sent[48] == 0 and abs(d._app.cc_sent[49] - round(1/40*127)) <= 1, "track knob rings follow params 0,1"
assert any(c[0] == "hint" and "Fruity Parametric" in c[1] for c in calls)
print("3 select + ring sync ok")

# 4 knobs write params (track knob 3 -> param 2; device knob 1 -> param 8), absolute
clear(); cc(0, 50, 64); cc(0, 16, 127)
assert ("set", 2, round(64/127, 3), 2, 2) in calls and ("set", 8, 1.0, 2, 2) in calls
print("4 knobs ok")

# 5 fader pickup: fader 1 -> param 16 (value .4). Far position must not jump it; arriving near target engages
clear(); PLUG[(2, 2)].vals[16] = 0.4
cc(0, 7, 10); assert not any(c[0] == "set" for c in calls), "no jump"
cc(0, 7, 50); assert any(c[0] == "set" and c[1] == 16 for c in calls), "engaged near target (0.39 vs 0.4)"
clear(); cc(0, 7, 100); assert any(c[0] == "set" and c[1] == 16 for c in calls), "stays engaged"
print("5 fader pickup ok")

# 6 banks: scene2 = bank+ (40 params -> 2 pages); ring now follows param 24..; scene1 = bank-
press(0, 83); assert a.bank == 1 and abs(a.cc_sent[48] - round(PLUG[(2, 2)].vals[24] * 127)) <= 1
press(0, 83); assert a.bank == 1, "clamped at last page"
press(0, 82); assert a.bank == 0
print("6 param banks ok")

# 7 relative cue level: +4 ticks = bank+1, -4 = bank-1 (two's-complement negatives)
cc(0, 47, 1); cc(0, 47, 2); cc(0, 47, 1); assert a.bank == 1
cc(0, 47, 127); cc(0, 47, 126); cc(0, 47, 127); assert a.bank == 0, "-4 ticks = bank-1"
cc(0, 47, 127); assert a.bank == 0, "single tick does nothing"
cc(0, 47, 63); assert a.bank == 1, "+63 ticks clamps at the last page"
cc(0, 47, 65); assert a.bank == 0, "-63 ticks clamps at page 0"
print("7 relative cue ok")

# 8 presets + dump
clear(); press(0, 85); press(0, 84); assert ("next", 2, 2) in calls and ("prev", 2, 2) in calls
press(0, 86)
print("8 presets/dump ok")

# 9 software blink on single-colour rows: select slot 7 (row 6 = activator note 50) of track 2
press(1, 50); assert a.sel_slot == 6
t0 = 1000.0; a.t_blink = a.t_scan = a.t_poll = t0
first = led(1, 50)
d._app.tick(t0 + 0.5); second = led(1, 50)
assert first != second, (first, second)
assert led(1, 52) in (0, 1, 2)
print("9 blink ok", first, "->", second)

# 10 bank up/down moves slot; shift tracking
press(0, 95); assert a.sel_slot == 7
press(0, 94); press(0, 94); assert a.sel_slot == 5
print("10 slot nav ok")

# 11 track window: RIGHT shifts to tracks 9-16 and re-scans; selected moves into window
press(0, 96); assert a.base == 9 and a.sel_track == 9
press(0, 97); assert a.base == 1
print("11 track banking ok")

# 12 Shift+Master toggles mode; Mixer mode controls
e = Ev(0x90, 98, 127); d.OnMidiMsg(e)
press(0, 80); assert a.mode == "mixer"
d.OnMidiMsg(Ev(0x80, 98, 0))
clear(); press(2, 49); press(2, 50); press(2, 48); press(2, 51)
assert ("solo", 3) in calls and ("mute", 3) in calls and ("arm", 3) in calls and ("active", 3) in calls
assert led(2, 49) == 1 and led(2, 50) == 0 and led(2, 48) == 1, "solo lit, muted -> activator off, armed lit"
clear(); T[1]["vol"] = 0.8; cc(0, 7, 102); assert any(c[0] == "vol" and c[1] == 1 for c in calls), "fader near 0.8 engages"
clear(); cc(0, 48, 127); assert ("pan", 1, 1.0) in calls
clear(); cc(0, 14, 102); assert any(c[0] == "vol" and c[1] == 0 for c in calls), "master fader -> master track"
print("12 mixer mode ok")

# 12b effect colours legend + fine mode + touch guard
a.mode = "fx"; a.led_sent.clear(); press(1, 55)
clear(); a.shift = True; cc(0, 48, 40); cc(0, 48, 80)         # fine: knob travelled 40/127 -> param moves 40/127*0.25
p0 = PLUG[(2, 2)].vals[0]
assert abs(PLUG[(2, 2)].vals[0] - (0 + 40 / 127 * 0.25)) < 1e-6 and a.fine, "fine adjust relative to anchor"
d.OnMidiMsg(Ev(0x80, 98, 0)); a.shift = False
assert not a.fine and 48 not in [k for k in a.cc_sent if k == 48 and a.cc_sent[k] == 80], "rings resynced on SHIFT release"
t = 5000.0; a.clock = lambda: t
cc(0, 49, 90); PLUG[(2, 2)].vals[1] = 0.1                      # param changes behind the user's back while the knob is held
sent.clear(); a.sync_rings(); assert not any(m for k, m in sent if k == "msg" and ((m >> 8) & 0xFF) == 49), "touch guard: no ring write while turning"
t += 1.0; a.sync_rings(); assert a.cc_sent[49] == round(0.1 * 127), "ring catches up after the knob is released"
print("12b colours/fine/touch ok")

# 12c no focus function in this FL build: must not crash, must report what exists (once)
import io, contextlib
del sys.modules["mixer"].focusEditor
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    press(1, 55); press(2, 53)
out = buf.getvalue()
assert "no working plugin-window function found" in out and out.count("no working plugin-window function found") == 1, out
assert a.sel_track == 3 and a.sel_slot == 0, "selection still works without focus support"
print("12c focus fallback ok")

# 13 diffing: re-render with nothing changed sends nothing
clear(); a.render(); assert not sent, "diffed output"
# 14 shutdown clears LEDs
d.OnDeInit(); assert sent
print("13/14 diff + shutdown ok")
print("ALL CONTROL-SCRIPT TESTS PASSED")
