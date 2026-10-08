# name=APC40 MkI Control (Mixer + FX + Channel Rack)
# supportedDevices=APC40
#
# Akai APC40 MkI (original) control script for FL Studio 2026.1.7+.   v0.7
# Addresses come from the Workbench Learn run (137/137 matched) - see docs/APC40_PROTOCOL_NOTES.md.
# Only FL API calls verified in the IL-Group API stubs are used (plugins.*, mixer track functions, mixer.setActiveTrack).
#
# MODES  (PAN = Mixer, SEND A = FX, SEND B = Channel Rack; SHIFT + MASTER SELECT cycles modes)
#   MIXER: faders = track volume, ACTIVATOR = mute, SOLO/CUE = solo, REC = arm, TRACK SELECT = select,
#          track knobs = pan (rings follow), master fader = master volume, bank LEFT/RIGHT = +/- 8 tracks
#   FX:    the 8x10 matrix = 8 mixer tracks x 10 effect slots (rows: 5 clip rows, clip stop, activator, solo, rec, track select)
#          press = select that slot.  Track knobs = params 1-8, device knobs = params 9-16, faders 1-8 = params 17-24 (24 per bank)
#          SCENE 1/2 = param bank -/+,  SCENE 3/4 = prev/next preset,  SCENE 5 = dump params to Script output
#          bank UP/DOWN = previous/next slot, bank LEFT/RIGHT = +/- 8 tracks, CUE LEVEL (relative) = scroll param bank
#          LEDs (grid rows 1-5): colour = effect type  GREEN tone/EQ/filter/stereo, RED dynamics/distortion, ORANGE time/space/modulation
#               selected slot BLINKS in its colour (red blink = selected empty slot); rows 6-10 are single colour: on = plugin, blink = selected
#          SHIFT held while turning a knob = fine adjust (quarter speed).  Pressing a pad also tries to open/focus that plugin's window.
#          knob rings follow plugin parameters (no jump); faders use pickup (they have no feedback)
#
#   CHANNEL RACK (Send B) - three levels, MASTER SELECT steps through them (or press a Track Select pad 1/2/3):
#     L1 CHANNELS: grid = 40 channels per bank (green = active, red = muted, blinking = selected). Pad = select, SHIFT+pad = mute.
#        Cue Level scrolls the selection, bank LEFT/RIGHT = +/-8 channels, bank UP/DOWN = previous/next channel,
#        Scene 1-5 = pattern length 8/16/32/64/128, Activator pad 1 = mute, Solo pad 1 = solo, SHIFT+Stop All = clear everything
#     L2 STEP SEQUENCER: grid = 40 steps of the selected channel (green = on, orange blink = focused). Pad = toggle step + focus it,
#        SHIFT+pad = focus it and open L3. Cue Level scrolls the focus. Clip Stop pad 1 = clear this channel's steps
#     L3 NOTE PROPERTIES of the FOCUSED step (the graph-editor values):
#        faders 1-8 = Pitch, Velocity, Release, Fine pitch, Pan, Mod X, Mod Y, Shift     master fader = Repeat
#        track knobs 1-8 = the same 8 properties (rings show the real values), device knob 1 = Repeat
#        NUDGE -/+ = Shift -/+ 1 tick (SHIFT held: 6).  Record/Arm pads 1-8 = reset that property to its default
#        grid pad = focus that step (SHIFT+pad = toggle it on/off), Cue Level scrolls the focus
#
# Install: Documents\Image-Line\FL Studio\Settings\Hardware\APC40Control\device_APC40Control.py
# Then Options > MIDI settings: Input APC40 -> controller type "APC40 MkI Control (Mixer + FX)", set the same port number on the
# matching Output, enable both. Disable FL's built-in APC40 script and close the Workbench first.

import time

import channels
import device
import mixer
import patterns
import plugins
import ui

# ---------------------------------------------------------------- configuration
MODE_BYTE = 0x42            # Alt Ableton: every LED host-controlled, nothing banked (needs FL 2026.1.7+ for script SysEx)
SEND_MODE_SYSEX = True
NUM_COLS = 8
NUM_SLOTS = 10
BANK_SIZE = 24              # params per page: 8 track knobs + 8 device knobs + 8 faders
PICKUP_TOLERANCE = 0.04
CUE_TICKS_PER_BANK = 4
FOCUS_ON_SELECT = True      # try to bring the plugin window to the front when a slot is selected
FINE_SCALE = 0.25           # SHIFT + knob moves the parameter at this fraction of normal range
TOUCH_HOLD_SECONDS = 0.6    # while a knob is being turned, do not write ring positions back to it (stops fighting/jitter)
RING_MIN_DELTA = 2          # background ring sync ignores differences smaller than this (0-127 counts)
BLINK_SECONDS = 0.4
SCAN_SECONDS = 0.25
POLL_SECONDS = 0.10
CUE_TICKS_PER_CHANNEL = 2
AUTO_ACTIVATE_STEP = True   # writing a note property turns the step on first (FL needs an active step)

MODE_MIXER, MODE_FX, MODE_CHANNELS = "mixer", "fx", "channels"
CR_LEVEL_SELECT, CR_LEVEL_SEQ, CR_LEVEL_PROPS = 1, 2, 3
CR_PATTERN_LENGTHS = [8, 16, 32, 64, 128]

# FL step parameters (channels.setStepParameterByIndex / getCurrentStepParam), indices from the FL scripting manual.
PROP_PITCH, PROP_VELOCITY, PROP_RELEASE, PROP_FINE, PROP_PAN, PROP_MODX, PROP_MODY, PROP_SHIFT, PROP_REPEAT = range(9)
PROP_NAMES = ["Pitch", "Velocity", "Release", "Fine pitch", "Pan", "Mod X", "Mod Y", "Shift", "Repeat"]
# (min, max, default).  Pitch/velocity/release/fine pitch/pan ranges are documented; Mod X/Y, Shift and Repeat are
# UNVERIFIED guesses - entering Level 3 prints the real raw values of the focused step so they can be corrected here.
PROP_RANGES = [(0, 127, 60), (0, 127, 100), (0, 127, 64), (0, 240, 120), (0, 127, 64),
               (0, 255, 128), (0, 255, 128), (0, 127, 0), (0, 15, 0)]

# ---------------------------------------------------------------- verified APC40 MkI map
N_REC, N_SOLO, N_ACT, N_SEL, N_STOP = 48, 49, 50, 51, 52
GRID_NOTES = [53, 54, 55, 56, 57]
FX_ROW_NOTES = GRID_NOTES + [N_STOP, N_ACT, N_SOLO, N_REC, N_SEL]       # matrix row 0..9 -> note
NOTE_TO_FX_ROW = dict((n, i) for i, n in enumerate(FX_ROW_NOTES))
SCENE_NOTES = [82, 83, 84, 85, 86]
N_MASTER_SEL, N_STOP_ALL = 80, 81
N_PAN, N_SEND_A, N_SEND_B, N_SEND_C = 87, 88, 89, 90
N_BANK_UP, N_BANK_DOWN, N_BANK_RIGHT, N_BANK_LEFT = 94, 95, 96, 97
N_SHIFT = 98
N_NUDGE_PLUS, N_NUDGE_MINUS = 100, 101
TRACK_KNOB_CC = list(range(48, 56))
DEVICE_KNOB_CC = list(range(16, 24))
CC_FADER, CC_MASTER, CC_CUE = 7, 14, 47
RING_TYPE_TRACK = list(range(56, 64))
RING_TYPE_DEVICE = list(range(24, 32))

# Effect-type colours for the grid. First matching keyword wins; anything unmatched is 0 (green, tone shaping).
# 0 = green (tone: EQ, filters, stereo, balance)   1 = red (dynamics, distortion)   2 = orange (time, space, modulation)
CATEGORY_KEYWORDS = [
    (1, ("limiter", "compress", "maximus", "gate", "transient", "clipper", "squeeze", "multiband", "expander", "dynamics",
         "de-ess", "deess", "leveler", "levelling", "distort", "overdrive", "saturat", "waveshap", "bitcrush", "crusher",
         "fuzz", "tube", "blood", "soundgoodizer", "tape")),
    (2, ("reverb", "reeverb", "delay", "echo", "convolv", "luxeverb", "chorus", "flang", "phaser", "tremolo", "vibrato",
         "vocoder", "gross beat", "granul", "pitcher", "emphasis", "wobble", "autopan", "spatial", "hall", "plate", "space")),
]
CATEGORY_VEL = {0: 1, 1: 3, 2: 5}       # steady LED state per category (blink = +1)

LED_OFF, LED_GREEN, LED_GREEN_BLINK, LED_RED, LED_RED_BLINK, LED_ORANGE, LED_ORANGE_BLINK = 0, 1, 2, 3, 4, 5, 6
RING_OFF, RING_SINGLE, RING_VOLUME, RING_PAN = 0, 1, 2, 3

ALL_LED_KEYS = ([(c, n) for c in range(NUM_COLS) for n in (N_REC, N_SOLO, N_ACT, N_SEL, N_STOP) + tuple(GRID_NOTES)]
                + [(0, n) for n in SCENE_NOTES + [N_MASTER_SEL, N_PAN, N_SEND_A, N_SEND_B, N_SEND_C]])


def send_midi(status, d1, d2):
    device.midiOutMsg(status | (d1 << 8) | (d2 << 16))


class App:
    def __init__(self):
        self.mode = MODE_MIXER
        self.cr_level = CR_LEVEL_SELECT
        self.cr_channel_base = 0
        self.cr_sel_channel = 0
        self.cr_focused_step = 0
        self.cr_pattern_length = 32
        self.cr_last_fl_channel = None
        self.warned = set()
        self.base = 1                       # first FL mixer track shown in column 1 (track 0 is Master)
        self.sel_track, self.sel_slot = 1, 0
        self.bank = 0
        self.shift = False
        self.blink_on = True
        self.t_blink = self.t_scan = self.t_poll = 0.0
        self.present = {}
        self.pname, self.pcount = "", 0
        self.led_sent, self.cc_sent = {}, {}
        self.fader_pos = [None] * 9
        self.fader_armed = [False] * 9
        self.cue_accum = 0
        self.last_fl_track = None
        self.clock = time.time
        self.touched = {}                   # knob cc -> last time it moved
        self.fine = {}                      # knob cc -> (knob value at start, parameter value at start) while SHIFT is held
        self.cat = {}                       # (track, slot) -> effect category 0/1/2
        self.focus_fn = None                # which FL call worked for opening a plugin window
        self.focus_warned = False

    # ------------------------------------------------------------ output (diffed: only changes hit the USB port)
    def led(self, ch, note, vel):
        if self.led_sent.get((ch, note)) == vel:
            return
        self.led_sent[(ch, note)] = vel
        send_midi((0x90 if vel else 0x80) | ch, note, vel)

    def ring(self, cc, value):
        value = max(0, min(127, int(value)))
        if self.cc_sent.get(cc) == value:
            return
        self.cc_sent[cc] = value
        send_midi(0xB0, cc, value)

    def hint(self, text):
        try:
            ui.setHintMsg(text)
        except Exception:                                   # noqa: BLE001 - optional nicety
            pass

    # ------------------------------------------------------------ FL state helpers
    def track_of(self, col):
        return self.base + col

    def slot_present(self, track, slot):
        try:
            return bool(plugins.isValid(track, slot))
        except Exception:                                   # noqa: BLE001
            return False

    def scan_present(self):
        changed = False
        for col in range(NUM_COLS):
            for slot in range(NUM_SLOTS):
                key = (self.track_of(col), slot)
                now = self.slot_present(*key)
                if self.present.get(key) != now:
                    self.present[key] = now
                    changed = True
                if now and key not in self.cat:
                    self.cat[key] = self.category(*key)
                elif not now:
                    self.cat.pop(key, None)
        return changed

    @staticmethod
    def category(track, slot):
        try:
            name = plugins.getPluginName(track, slot).lower()
        except Exception:                                   # noqa: BLE001
            return 0
        for cat, words in CATEGORY_KEYWORDS:
            if any(w in name for w in words):
                return cat
        return 0

    def focus_plugin(self):
        if not (FOCUS_ON_SELECT and self.sel_present()):
            return
        candidates = [("mixer", mixer, "focusEditor"), ("mixer", mixer, "showEditor"), ("plugins", plugins, "showEditor"),
                      ("plugins", plugins, "focusEditor")]
        if self.focus_fn:
            candidates = [c for c in candidates if c[0] + "." + c[2] == self.focus_fn]
        for modname, module, attr in candidates:
            fn = getattr(module, attr, None)
            if fn is None:
                continue
            try:
                fn(self.sel_track, self.sel_slot)
                if not self.focus_fn:
                    self.focus_fn = modname + "." + attr
                    print("APC40: plugin window focus via", self.focus_fn)
                return
            except Exception as e:                          # noqa: BLE001
                print("APC40: %s.%s failed: %s" % (modname, attr, e))
        if not self.focus_warned:
            self.focus_warned = True
            names = []
            for mod in (mixer, plugins, ui):
                names += [mod.__name__ + "." + n for n in dir(mod) if any(k in n.lower() for k in ("editor", "focus", "window"))]
            print("APC40: no working plugin-window function found. Candidates in this FL build:", ", ".join(sorted(names)))

    def sel_present(self):
        return self.slot_present(self.sel_track, self.sel_slot)

    def refresh_selected(self):
        if self.sel_present():
            try:
                self.pname = plugins.getPluginName(self.sel_track, self.sel_slot)
                self.pcount = plugins.getParamCount(self.sel_track, self.sel_slot)
            except Exception:                               # noqa: BLE001
                self.pname, self.pcount = "?", 0
        else:
            self.pname, self.pcount = "", 0
        self.bank = max(0, min(self.bank, self.max_bank()))

    def max_bank(self):
        return max(0, (self.pcount - 1) // BANK_SIZE) if self.pcount else 0

    def param_value(self, p):
        try:
            return float(plugins.getParamValue(p, self.sel_track, self.sel_slot))
        except Exception:                                   # noqa: BLE001
            return None

    def set_param(self, p, v):
        try:
            plugins.setParamValue(float(v), p, self.sel_track, self.sel_slot)
        except Exception as e:                              # noqa: BLE001
            print("APC40: param write error:", e)

    def select_track(self, track):
        self.sel_track = track
        self.last_fl_track = track
        try:
            mixer.setActiveTrack(track)
        except Exception:                                   # noqa: BLE001
            try:
                mixer.setTrackNumber(track)
            except Exception as e:                          # noqa: BLE001
                print("APC40: select track error:", e)

    # ------------------------------------------------------------ rendering
    def render(self, force_rings=False):
        want = {}
        want[(0, N_PAN)] = 1 if self.mode == MODE_MIXER else 0
        want[(0, N_SEND_A)] = 1 if self.mode == MODE_FX else 0
        want[(0, N_SEND_B)] = 1 if self.mode == MODE_CHANNELS else 0
        if self.mode == MODE_CHANNELS:
            self.render_channels(want)
        elif self.mode == MODE_FX:
            self.render_fx(want)
        else:
            self.render_mixer(want)
        for ch, note in ALL_LED_KEYS:
            self.led(ch, note, want.get((ch, note), 0))
        self.render_ring_types()
        self.sync_rings(force_rings)

    def render_fx(self, want):
        for col in range(NUM_COLS):
            track = self.track_of(col)
            for row in range(NUM_SLOTS):
                note = FX_ROW_NOTES[row]
                present = self.present.get((track, row), False)
                selected = (track == self.sel_track and row == self.sel_slot)
                if row < 5:                                   # three-colour rows: colour = effect type, blink = selected
                    steady = CATEGORY_VEL[self.cat.get((track, row), 0)]
                    vel = (steady + 1 if present else LED_RED_BLINK) if selected else (steady if present else LED_OFF)
                elif selected:                                # single-colour rows: blink the cursor
                    vel = 2 if row == 5 else (1 if self.blink_on else 0)
                else:
                    vel = 1 if present else 0
                want[(col, note)] = vel
        want[(0, SCENE_NOTES[0])] = 1 if self.bank > 0 else 0
        want[(0, SCENE_NOTES[1])] = 1 if self.bank < self.max_bank() else 0
        want[(0, SCENE_NOTES[2])] = want[(0, SCENE_NOTES[3])] = 1 if self.pcount else 0
        want[(0, SCENE_NOTES[4])] = 1

    def render_mixer(self, want):
        for col in range(NUM_COLS):
            t = self.track_of(col)
            try:
                want[(col, N_ACT)] = 0 if mixer.isTrackMuted(t) else 1
                want[(col, N_SOLO)] = 1 if mixer.isTrackSolo(t) else 0
                want[(col, N_REC)] = 1 if mixer.isTrackArmed(t) else 0
            except Exception:                               # noqa: BLE001
                pass
            want[(col, N_SEL)] = 1 if t == self.sel_track else 0

    def render_ring_types(self):
        fx = self.mode == MODE_FX
        cr = self.mode == MODE_CHANNELS
        for i in range(8):
            self.ring_type(RING_TYPE_TRACK[i], RING_VOLUME if (fx or cr) else RING_PAN)
            self.ring_type(RING_TYPE_DEVICE[i], RING_VOLUME if (fx or cr) else RING_OFF)

    def ring_type(self, cc, value):
        key = ("type", cc)
        if self.cc_sent.get(key) != value:
            self.cc_sent[key] = value
            send_midi(0xB0, cc, value)

    def sync_rings(self, force=False):
        now = self.clock()
        if self.mode == "fx":
            for k in range(16):
                cc = TRACK_KNOB_CC[k] if k < 8 else DEVICE_KNOB_CC[k - 8]
                if not force and now - self.touched.get(cc, -99.0) < TOUCH_HOLD_SECONDS:
                    continue                                # the user is turning this knob: do not fight them
                p = self.bank * BANK_SIZE + k
                v = self.param_value(p) if (self.sel_present() and p < self.pcount) else 0.0
                target = int(round(max(0.0, min(1.0, v or 0.0)) * 127))
                if not force and abs(target - self.cc_sent.get(cc, -99)) < RING_MIN_DELTA:
                    continue
                self.ring(cc, target)
        elif self.mode == MODE_CHANNELS:
            props = self.cr_level == CR_LEVEL_PROPS
            for i in range(8):                              # track knob rings = the 8 properties of the focused note
                v = self.step_norm(self.cr_sel_channel, self.cr_focused_step, i) if props else 0.0
                self.ring_to(TRACK_KNOB_CC[i], v, force, now)
            for i in range(8):                              # device knob 1 ring = Repeat, the rest are unused
                v = self.step_norm(self.cr_sel_channel, self.cr_focused_step, PROP_REPEAT) if (props and i == 0) else 0.0
                self.ring_to(DEVICE_KNOB_CC[i], v, force, now)
        else:
            for i in range(8):
                if not force and now - self.touched.get(TRACK_KNOB_CC[i], -99.0) < TOUCH_HOLD_SECONDS:
                    continue
                try:
                    pan = mixer.getTrackPan(self.track_of(i))
                except Exception:                           # noqa: BLE001
                    pan = 0.0
                self.ring(TRACK_KNOB_CC[i], (pan + 1.0) * 63.5)
                self.ring(DEVICE_KNOB_CC[i], 0)

    def rearm_faders(self):
        self.fader_armed = [False] * 9

    # ------------------------------------------------------------ input
    def on_midi(self, status, d1, d2):
        kind, ch = status & 0xF0, status & 0x0F
        if kind == 0x90 and d2 > 0:
            self.on_button(ch, d1, True)
        elif kind == 0x80 or (kind == 0x90 and d2 == 0):
            self.on_button(ch, d1, False)
        elif kind == 0xB0:
            self.on_cc(ch, d1, d2)

    def on_button(self, ch, note, down):
        if note == N_SHIFT:
            self.shift = down
            if not down and self.fine:
                self.fine.clear()
                self.sync_rings(True)                       # knobs go back to showing the true parameter values
            return
        if not down:
            return
        if note == N_PAN:
            return self.set_mode(MODE_MIXER)
        if note == N_SEND_A:
            return self.set_mode(MODE_FX)
        if note == N_SEND_B:
            return self.set_mode(MODE_CHANNELS)
        if note == N_MASTER_SEL:
            if self.shift:
                return self.set_mode({MODE_MIXER: MODE_FX, MODE_FX: MODE_CHANNELS, MODE_CHANNELS: MODE_MIXER}[self.mode])
            if self.mode == MODE_CHANNELS:
                return self.cr_next_level()
            return None
        if note in (N_BANK_LEFT, N_BANK_RIGHT):
            return self.shift_tracks(-NUM_COLS if note == N_BANK_LEFT else NUM_COLS)
        if self.mode == MODE_CHANNELS:
            self.channels_button(ch, note)
        elif self.mode == MODE_FX:
            self.fx_button(ch, note)
        else:
            self.mixer_button(ch, note)

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        self.cue_accum = 0                                  # leftover Cue Level ticks must not leak into the new mode
        self.rearm_faders()
        self.led_sent.clear()                               # force a full, clean repaint of the surface
        self.scan_present()
        self.refresh_selected()
        if mode == MODE_CHANNELS:
            self.cr_sel_channel = self.selected_channel()
            self.cr_last_fl_channel = self.cr_sel_channel
            self.cr_channel_base = (self.cr_sel_channel // 40) * 40
            self.cr_level = CR_LEVEL_SELECT
            self.cr_focused_step = 0
        self.render(True)

    def shift_tracks(self, delta):
        if self.mode == MODE_CHANNELS:
            if self.cr_level == CR_LEVEL_SELECT:
                self.cr_channel_base = max(0, min(max(0, self.channel_count() - 1), self.cr_channel_base + delta))
            else:
                self.cr_focus(self.cr_focused_step + delta // 2)
            self.render(True)
            return
        self.base = max(1, self.base + delta)
        self.rearm_faders()
        self.scan_present()
        if not (self.base <= self.sel_track < self.base + NUM_COLS):
            self.select_track(self.base)
            self.refresh_selected()
        self.render(True)

    def fx_button(self, ch, note):
        if note in NOTE_TO_FX_ROW and ch < NUM_COLS:
            self.sel_track, self.sel_slot = self.track_of(ch), NOTE_TO_FX_ROW[note]
            self.select_track(self.sel_track)
            self.bank = 0
            self.refresh_selected()
            self.rearm_faders()
            self.hint("Track %d  Slot %d: %s" % (self.sel_track, self.sel_slot + 1, self.pname or "(empty)"))
            self.focus_plugin()
        elif note == SCENE_NOTES[0]:
            self.change_bank(-1)
        elif note == SCENE_NOTES[1]:
            self.change_bank(+1)
        elif note == SCENE_NOTES[2] and self.sel_present():
            plugins.prevPreset(self.sel_track, self.sel_slot)
        elif note == SCENE_NOTES[3] and self.sel_present():
            plugins.nextPreset(self.sel_track, self.sel_slot)
        elif note == SCENE_NOTES[4]:
            self.dump_params()
        elif note in (N_BANK_UP, N_BANK_DOWN):
            self.sel_slot = max(0, min(NUM_SLOTS - 1, self.sel_slot + (-1 if note == N_BANK_UP else 1)))
            self.bank = 0
            self.refresh_selected()
            self.rearm_faders()
            self.focus_plugin()
        else:
            return
        self.render(True)

    def change_bank(self, delta):
        nb = max(0, min(self.max_bank(), self.bank + delta))
        if nb != self.bank:
            self.bank = nb
            self.rearm_faders()
            self.hint("%s: parameter page %d/%d" % (self.pname, self.bank + 1, self.max_bank() + 1))
            self.sync_rings(True)

    def dump_params(self):
        if not self.sel_present():
            print("APC40: no plugin in the selected slot")
            return
        print("PLUGIN %r  track %d slot %d  params %d" % (self.pname, self.sel_track, self.sel_slot + 1, self.pcount))
        for p in range(min(self.pcount, 200)):
            try:
                print("  %03d  %-36s %.4f" % (p, plugins.getParamName(p, self.sel_track, self.sel_slot), self.param_value(p) or 0.0))
            except Exception:                               # noqa: BLE001
                break

    def mixer_button(self, ch, note):
        if ch >= NUM_COLS:
            return
        t = self.track_of(ch)
        try:
            if note == N_ACT:
                mixer.muteTrack(t)
            elif note == N_SOLO:
                mixer.soloTrack(t)
            elif note == N_REC:
                mixer.armTrack(t)
            elif note == N_SEL:
                self.select_track(t)
            else:
                return
        except Exception as e:                              # noqa: BLE001
            print("APC40: mixer button error:", e)
        self.render()

    def on_cc(self, ch, cc, value):
        if cc == CC_FADER and ch < NUM_COLS:
            self.fader(ch, value / 127.0)
        elif cc == CC_MASTER:
            self.fader(8, value / 127.0)
        elif cc == CC_CUE:
            self.cue(value if value < 64 else value - 128)
        elif cc in TRACK_KNOB_CC:
            self.knob(TRACK_KNOB_CC.index(cc), value, cc)
        elif cc in DEVICE_KNOB_CC:
            self.knob(8 + DEVICE_KNOB_CC.index(cc), value, cc)

    def cue(self, delta):
        if self.mode == MODE_CHANNELS:
            return self.cr_cue(delta)
        if self.mode != "fx":
            return
        self.cue_accum += delta
        while abs(self.cue_accum) >= CUE_TICKS_PER_BANK:
            step = 1 if self.cue_accum > 0 else -1
            self.cue_accum -= step * CUE_TICKS_PER_BANK
            self.change_bank(step)
        self.render()

    def knob(self, k, value, cc):                          # k 0-7 track knobs, 8-15 device knobs
        self.touched[cc] = self.clock()
        if self.mode == "fx":
            p = self.bank * BANK_SIZE + k
            if self.sel_present() and p < self.pcount:
                if self.shift:                             # fine adjust: move relative to where the knob/param were when SHIFT engaged
                    if cc not in self.fine:
                        self.fine[cc] = (value, self.param_value(p) or 0.0)
                    k0, p0 = self.fine[cc]
                    self.set_param(p, max(0.0, min(1.0, p0 + (value - k0) / 127.0 * FINE_SCALE)))
                else:
                    self.set_param(p, value / 127.0)
                if self.shift:
                    self.cc_sent.pop(cc, None)             # fine mode: the knob no longer equals the parameter, resync on release
                else:
                    self.cc_sent[cc] = value               # the ring already shows the value the knob just sent
                try:
                    self.hint("%s  %s: %s" % (self.pname, plugins.getParamName(p, self.sel_track, self.sel_slot),
                                              plugins.getParamValueString(p, self.sel_track, self.sel_slot)))
                except Exception:                           # noqa: BLE001
                    pass
        elif self.mode == MODE_CHANNELS:
            self.cr_knob(k, value, cc)
        elif k < 8:
            try:
                mixer.setTrackPan(self.track_of(k), value / 127.0 * 2.0 - 1.0)
            except Exception as e:                          # noqa: BLE001
                print("APC40: pan error:", e)
            self.cc_sent[cc] = value

    def fader(self, idx, pos):
        prev, self.fader_pos[idx] = self.fader_pos[idx], pos
        if self.mode == MODE_CHANNELS and self.cr_level == CR_LEVEL_PROPS:
            prop = idx if idx < 8 else PROP_REPEAT           # faders 1-8 = properties 1-8, master fader = Repeat
            getter = lambda: self.step_norm(self.cr_sel_channel, self.cr_focused_step, prop)
            setter = lambda v: self.set_prop_norm(prop, v)
        elif idx == 8:                                      # master fader: always the Master track volume
            getter = lambda: self.safe(mixer.getTrackVolume, 0)
            setter = lambda v: mixer.setTrackVolume(0, v)
        elif self.mode == MODE_CHANNELS:
            return                                          # faders are only used by Level 3 of the Channel Rack
        elif self.mode == "fx":
            p = self.bank * BANK_SIZE + 16 + idx
            if not self.sel_present() or p >= self.pcount:
                return
            getter = lambda: self.param_value(p)
            setter = lambda v: self.set_param(p, v)
        else:
            t = self.track_of(idx)
            getter = lambda: self.safe(mixer.getTrackVolume, t)
            setter = lambda v: mixer.setTrackVolume(t, v)
        if not self.fader_armed[idx]:                       # pickup: faders are not motorised, so never jump the target
            target = getter()
            if target is None:
                return
            crossed = prev is not None and (prev - target) * (pos - target) <= 0
            if abs(pos - target) > PICKUP_TOLERANCE and not crossed:
                return
            self.fader_armed[idx] = True
        try:
            setter(pos)
        except Exception as e:                              # noqa: BLE001
            print("APC40: fader error:", e)

    # ------------------------------------------------------------ Channel Rack: FL helpers
    def warn_once(self, key, text):
        if key not in self.warned:
            self.warned.add(key)
            print("APC40:", text)

    def channel_count(self):
        try:
            return int(channels.channelCount())
        except Exception:                                   # noqa: BLE001
            return 0

    def selected_channel(self):
        try:
            return int(channels.selectedChannel())
        except Exception:                                   # noqa: BLE001
            return 0

    def grid_bit(self, ch, step):
        try:
            return bool(channels.getGridBit(ch, step))
        except Exception:                                   # noqa: BLE001
            return False

    def set_grid_bit(self, ch, step, on):
        try:
            channels.setGridBit(ch, step, 1 if on else 0)
        except Exception as e:                              # noqa: BLE001
            self.warn_once("setGridBit", "setGridBit failed: %s" % e)

    def channel_flag(self, fn_name, ch):
        try:
            return bool(getattr(channels, fn_name)(ch))
        except Exception:                                   # noqa: BLE001
            return False

    def channel_name(self, ch):
        try:
            return channels.getChannelName(ch)
        except Exception:                                   # noqa: BLE001
            return "?"

    def channel_toggle(self, fn_name, ch):
        try:
            getattr(channels, fn_name)(ch)                  # muteChannel / soloChannel toggle when no value is given
        except Exception as e:                              # noqa: BLE001
            self.warn_once(fn_name, "%s failed: %s" % (fn_name, e))

    def pattern_number(self):
        try:
            return int(patterns.patternNumber())
        except Exception:                                   # noqa: BLE001
            return 0

    # ------------------------------------------------------------ Channel Rack: note properties (graph editor values)
    # Read:  channels.getCurrentStepParam(channelIndex, step, param)
    # Write: channels.setStepParameterByIndex(channelIndex, patternNumber, step, param, value)
    def step_raw(self, ch, step, prop):
        try:
            return int(channels.getCurrentStepParam(ch, step, prop))
        except Exception as e:                              # noqa: BLE001
            self.warn_once(("read", prop), "getCurrentStepParam failed for %s: %s" % (PROP_NAMES[prop], e))
            return None

    def step_norm(self, ch, step, prop):
        raw = self.step_raw(ch, step, prop)
        if raw is None:
            return None
        lo, hi, _ = PROP_RANGES[prop]
        return max(0.0, min(1.0, (raw - lo) / float(hi - lo)))

    def write_step_prop(self, ch, step, prop, raw):
        lo, hi, _ = PROP_RANGES[prop]
        raw = int(max(lo, min(hi, raw)))
        try:
            if AUTO_ACTIVATE_STEP and not self.grid_bit(ch, step):
                self.set_grid_bit(ch, step, True)
            channels.setStepParameterByIndex(ch, self.pattern_number(), step, prop, raw)
            return raw
        except Exception as e:                              # noqa: BLE001
            self.warn_once(("write", prop), "setStepParameterByIndex failed for %s: %s" % (PROP_NAMES[prop], e))
            return None

    def set_prop_norm(self, prop, v):
        lo, hi, _ = PROP_RANGES[prop]
        raw = self.write_step_prop(self.cr_sel_channel, self.cr_focused_step, prop, int(round(lo + v * (hi - lo))))
        if raw is not None:
            self.hint("Step %d  %s: %d" % (self.cr_focused_step + 1, PROP_NAMES[prop], raw))

    def reset_prop(self, prop):
        raw = self.write_step_prop(self.cr_sel_channel, self.cr_focused_step, prop, PROP_RANGES[prop][2])
        if raw is not None:
            self.hint("Step %d  %s reset to %d" % (self.cr_focused_step + 1, PROP_NAMES[prop], raw))
        self.rearm_faders()

    def nudge_shift(self, delta):
        cur = self.step_raw(self.cr_sel_channel, self.cr_focused_step, PROP_SHIFT) or 0
        raw = self.write_step_prop(self.cr_sel_channel, self.cr_focused_step, PROP_SHIFT, cur + delta)
        if raw is not None:
            self.hint("Step %d  Shift: %d" % (self.cr_focused_step + 1, raw))

    def dump_step(self):
        vals = []
        for prop in range(len(PROP_NAMES)):
            vals.append("%s=%s" % (PROP_NAMES[prop], self.step_raw(self.cr_sel_channel, self.cr_focused_step, prop)))
        print("APC40: channel %d step %d raw properties: %s" % (self.cr_sel_channel, self.cr_focused_step + 1, "  ".join(vals)))

    def ring_to(self, cc, norm, force, now):
        if not force and now - self.touched.get(cc, -99.0) < TOUCH_HOLD_SECONDS:
            return
        target = int(round(max(0.0, min(1.0, norm or 0.0)) * 127))
        if not force and abs(target - self.cc_sent.get(cc, -99)) < RING_MIN_DELTA:
            return
        self.ring(cc, target)

    # ------------------------------------------------------------ Channel Rack: levels, rendering
    def cr_set_level(self, level):
        self.cr_level = level
        self.rearm_faders()
        self.hint({CR_LEVEL_SELECT: "Channel Rack: channels", CR_LEVEL_SEQ: "Channel Rack: step sequencer",
                   CR_LEVEL_PROPS: "Channel Rack: note properties"}[level])
        if level == CR_LEVEL_PROPS:
            self.dump_step()
        self.render(True)

    def cr_next_level(self):
        self.cr_set_level(self.cr_level % 3 + 1)

    def cr_focus(self, step):
        step = max(0, min(self.cr_pattern_length - 1, step))
        if step != self.cr_focused_step:
            self.cr_focused_step = step
            self.rearm_faders()
            self.hint("Step %d" % (step + 1))

    def cr_select(self, idx):
        self.cr_sel_channel = self.cr_last_fl_channel = idx
        self.cr_channel_base = (idx // 40) * 40
        try:
            channels.selectOneChannel(idx)
        except Exception as e:                              # noqa: BLE001
            self.warn_once("selectOneChannel", "selectOneChannel failed: %s" % e)
        self.hint("Channel %d: %s" % (idx + 1, self.channel_name(idx)))

    def render_channels(self, want):
        count, sel = self.channel_count(), self.cr_sel_channel
        if self.cr_level == CR_LEVEL_SELECT:
            for row in range(5):
                for col in range(NUM_COLS):
                    idx = self.cr_channel_base + row * NUM_COLS + col
                    if idx >= count:
                        vel = LED_OFF
                    else:
                        steady = LED_RED if self.channel_flag("isChannelMuted", idx) else LED_GREEN
                        vel = steady + 1 if idx == sel else steady          # blink variant = steady + 1
                    want[(col, GRID_NOTES[row])] = vel
        else:
            for row in range(5):
                for col in range(NUM_COLS):
                    step = row * NUM_COLS + col
                    on = step < self.cr_pattern_length and sel < count and self.grid_bit(sel, step)
                    if step >= self.cr_pattern_length or sel >= count:
                        vel = LED_OFF
                    elif step == self.cr_focused_step:
                        vel = LED_ORANGE_BLINK if on else LED_RED_BLINK     # focused: orange = note on, red = note off
                    else:
                        vel = LED_GREEN if on else LED_OFF
                    want[(col, GRID_NOTES[row])] = vel
        want[(0, N_STOP)] = 1
        for col in range(NUM_COLS):
            want[(col, N_SEL)] = 1 if col == self.cr_level - 1 else 0         # level indicator
            want[(col, N_REC)] = 1 if self.cr_level == CR_LEVEL_PROPS else 0  # reset-property pads
        want[(0, N_ACT)] = 0 if self.channel_flag("isChannelMuted", sel) else 1
        want[(0, N_SOLO)] = 1 if self.channel_flag("isChannelSolo", sel) else 0
        for i, note in enumerate(SCENE_NOTES):
            want[(0, note)] = 1 if CR_PATTERN_LENGTHS[i] == self.cr_pattern_length else 0

    # ------------------------------------------------------------ Channel Rack: input
    def channels_button(self, ch, note):
        count, sel = self.channel_count(), self.cr_sel_channel
        if note == N_STOP_ALL:
            if self.shift:                                  # destructive, so it needs SHIFT
                for c in range(count):
                    for step in range(self.cr_pattern_length):
                        self.set_grid_bit(c, step, False)
                self.hint("Cleared every channel's steps")
        elif note in (N_BANK_UP, N_BANK_DOWN):
            self.cr_select(max(0, min(count - 1, sel + (-1 if note == N_BANK_UP else 1))))
        elif note in (N_NUDGE_PLUS, N_NUDGE_MINUS):
            if self.cr_level == CR_LEVEL_PROPS:
                self.nudge_shift((6 if self.shift else 1) * (1 if note == N_NUDGE_PLUS else -1))
        elif note in SCENE_NOTES:
            self.cr_pattern_length = CR_PATTERN_LENGTHS[SCENE_NOTES.index(note)]
            self.cr_focus(self.cr_focused_step)
            self.hint("Pattern length: %d steps" % self.cr_pattern_length)
        else:
            row = NOTE_TO_FX_ROW.get(note)
            if row is None or ch >= NUM_COLS:
                return
            if row < 5:
                self.cr_grid_press(ch, row)
            elif row == 5 and ch == 0:                      # clip stop pad 1: clear the selected channel
                for step in range(self.cr_pattern_length):
                    self.set_grid_bit(sel, step, False)
                self.hint("Cleared channel %d" % (sel + 1))
            elif row == 9 and ch < 3:                       # track select pads 1-3: jump to a level
                self.cr_set_level(ch + 1)
                return
            elif row == 6 and ch == 0:                      # activator pad 1: mute selected channel
                self.channel_toggle("muteChannel", sel)
            elif row == 7 and ch == 0:                      # solo pad 1: solo selected channel
                self.channel_toggle("soloChannel", sel)
            elif row == 8 and self.cr_level == CR_LEVEL_PROPS and ch < 8:
                self.reset_prop(ch)                         # record/arm pads: reset that property of the focused note
        self.render(True)

    def cr_grid_press(self, col, row):
        count = self.channel_count()
        if self.cr_level == CR_LEVEL_SELECT:
            idx = self.cr_channel_base + row * NUM_COLS + col
            if idx < count:
                if self.shift:
                    self.channel_toggle("muteChannel", idx)
                else:
                    self.cr_select(idx)
            return
        step = row * NUM_COLS + col
        if step >= self.cr_pattern_length:
            return
        sel = self.cr_sel_channel
        if self.cr_level == CR_LEVEL_SEQ:
            if self.shift:
                self.cr_focus(step)
                self.cr_set_level(CR_LEVEL_PROPS)
            else:
                self.set_grid_bit(sel, step, not self.grid_bit(sel, step))
                self.cr_focus(step)
        else:
            if self.shift:
                self.set_grid_bit(sel, step, not self.grid_bit(sel, step))
            self.cr_focus(step)

    def cr_knob(self, k, value, cc):
        if self.cr_level != CR_LEVEL_PROPS:
            return
        prop = k if k < 8 else (PROP_REPEAT if k == 8 else None)    # track knobs 1-8 = properties 1-8, device knob 1 = Repeat
        if prop is None:
            return
        self.set_prop_norm(prop, value / 127.0)
        self.cc_sent[cc] = value

    def cr_cue(self, delta):
        self.cue_accum += delta
        while abs(self.cue_accum) >= CUE_TICKS_PER_CHANNEL:
            step = 1 if self.cue_accum > 0 else -1
            self.cue_accum -= step * CUE_TICKS_PER_CHANNEL
            if self.cr_level == CR_LEVEL_SELECT:
                new = max(0, min(self.channel_count() - 1, self.cr_sel_channel + step))
                if new != self.cr_sel_channel:
                    self.cr_select(new)
            else:
                self.cr_focus(self.cr_focused_step + step)
        self.render(self.cr_level == CR_LEVEL_PROPS)

    @staticmethod
    def safe(fn, *args):
        try:
            return float(fn(*args))
        except Exception:                                   # noqa: BLE001
            return None

    # ------------------------------------------------------------ periodic work (called from OnIdle)
    def tick(self, now):
        redraw = False
        if now - self.t_blink >= BLINK_SECONDS:
            self.t_blink, self.blink_on = now, not self.blink_on
            redraw = self.mode in (MODE_FX, MODE_CHANNELS)
        if now - self.t_scan >= SCAN_SECONDS:
            self.t_scan = now
            if self.scan_present():
                self.refresh_selected()
                redraw = True
            if self.mode == MODE_CHANNELS:                  # follow channel selection made inside FL itself
                cur = self.selected_channel()
                if cur != self.cr_last_fl_channel:
                    self.cr_last_fl_channel = cur
                    if cur != self.cr_sel_channel:
                        self.cr_sel_channel, self.cr_channel_base = cur, (cur // 40) * 40
                        redraw = True
            tn = self.safe(mixer.trackNumber)
            if tn is not None:
                tn = int(tn)
                if tn != self.last_fl_track:                # FL's own selection changed: follow it if it is one of our columns
                    self.last_fl_track = tn
                    if self.base <= tn < self.base + NUM_COLS and tn != self.sel_track:
                        self.sel_track = tn
                        self.refresh_selected()
                        redraw = True
            if self.mode == "mixer":
                redraw = True
        if now - self.t_poll >= POLL_SECONDS:
            self.t_poll = now
            if self.mode in (MODE_FX, MODE_CHANNELS):
                self.sync_rings()
        if redraw:
            self.render()

    def init(self):
        if SEND_MODE_SYSEX:
            device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x73, 0x60, 0x00, 0x04, MODE_BYTE, 0x09, 0x00, 0x00, 0xF7]))
        self.scan_present()
        self.last_fl_track = self.safe(mixer.trackNumber)
        self.refresh_selected()
        self.cr_sel_channel = self.cr_last_fl_channel = self.selected_channel()
        self.render()
        print("APC40 Control v0.7 ready: mode=%s, tracks %d-%d" % (self.mode, self.base, self.base + NUM_COLS - 1))
        print("APC40: step API:", ", ".join("%s=%s" % (n, "yes" if hasattr(channels, n) else "NO")
                                           for n in ("setStepParameterByIndex", "getCurrentStepParam", "getStepParam")),
              "| patterns.patternNumber=%s" % ("yes" if hasattr(patterns, "patternNumber") else "NO"))

    def shutdown(self):
        for ch, note in ALL_LED_KEYS:
            send_midi(0x80 | ch, note, 0)


_app = None


def OnInit():
    global _app
    _app = App()
    _app.init()


def OnDeInit():
    if _app is not None:
        _app.shutdown()


def OnMidiMsg(event):
    if _app is not None:
        _app.on_midi(event.status, event.data1, event.data2)
    event.handled = True                                    # never let FL turn APC40 pads into notes


def OnIdle():
    if _app is not None:
        _app.tick(time.time())


def OnRefresh(flags):
    if _app is not None:
        _app.t_scan = 0.0                                   # re-scan slots / FL selection on the next idle tick
