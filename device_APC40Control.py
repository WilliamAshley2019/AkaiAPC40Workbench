# name=APC40 MkI Control (Mixer + FX + Channel Rack)
# supportedDevices=APC40
#
# Akai APC40 MkI control script for FL Studio 2026.1.7+.   v0.4
#
# CHANNEL RACK MODE (Send B) has THREE LEVELS, mirroring FL Studio's own GUI:
#   LEVEL 1 - CHANNEL SELECT:
#     * Grid = 40 channel slots (5 rows x 8 cols) per bank
#     * Green = active/unmuted channel
#     * Red = muted channel
#     * Dim = empty slot
#     * Selected channel FLASHES (green if unmuted, red if muted)
#     * Press pad = select channel
#     * Shift + pad = toggle mute on that channel
#     * Cue Level knob = scroll channels by 1
#     * Bank L/R = scroll bank by 8 channels
#     * Scene 1-5 = pattern length 8/16/32/64/128
#     * Scene 6/7 = rotate left/right on selected channel
#     * Scene 8 = clear selected channel
#     * Stop All = clear all steps in pattern
#     * Master Select = enter Level 2 (Step Sequencer)
#
#   LEVEL 2 - STEP SEQUENCER (for selected channel):
#     * Grid = up to 40 step positions (5 rows x 8 cols) for the selected channel
#     * Green = step is on, Dim = step is off
#     * Focused step FLASHES
#     * Press pad = toggle step on/off
#     * Shift + pad = enter Level 3 (Note Properties for that step)
#     * Cue Level knob = scroll focused step
#     * Master Select = return to Level 1
#     * Scene 1-5 = pattern length 8/16/32/64/128
#     * Scene 6/7 = fill each 2/4 (or rotate)
#     * Scene 8 = clear selected channel's steps
#
#   LEVEL 3 - NOTE PROPERTIES (for focused step):
#     * Row 9 (Record/Arm) pads select property: Pitch / Velocity / Rel Vel / Fine Pitch / Panning / Mod X / Mod Y / Shift
#     * Faders 1-8 = edit property for steps 1-8 (relative to current page)
#     * Track Knobs 1-8 = edit property for steps 9-16
#     * Device Knobs 1-8 = edit property for steps 17-24
#     * Master Fader = nudge
#     * Cue Level knob = scroll focused step
#     * Shift + pad = toggle step on/off
#     * Master Select = return to Level 2
#
#   SOLO: Shift + Scene 8 (or reassign as desired)
#   MUTE: Shift + pad in Level 1, or Scene 8 with shift elsewhere

import time

import channels
import device
import mixer
import plugins
import ui

# ---------------------------------------------------------------- configuration
MODE_BYTE = 0x42
SEND_MODE_SYSEX = True
NUM_COLS = 8
NUM_SLOTS = 10
BANK_SIZE = 24
PICKUP_TOLERANCE = 0.04
CUE_TICKS_PER_CHANNEL = 2
FOCUS_ON_SELECT = True
FINE_SCALE = 0.25
TOUCH_HOLD_SECONDS = 0.6
RING_MIN_DELTA = 2
BLINK_SECONDS = 0.4
SCAN_SECONDS = 0.25
POLL_SECONDS = 0.10

# ---------------------------------------------------------------- modes and levels
MODE_MIXER = "mixer"
MODE_FX = "fx"
MODE_CHANNELS = "channels"

CR_LEVEL_SELECT = 1
CR_LEVEL_SEQ = 2
CR_LEVEL_PROPS = 3

CR_CHANNELS_PER_BANK = 40
CR_STEPS_PER_ROW = 8
CR_MAX_STEPS = 128
CR_PATTERN_LENGTHS = [8, 16, 32, 64, 128]

# Note property indices (matching FL Studio's Graph Editor order)
PROP_PITCH = 0
PROP_VELOCITY = 1
PROP_RELEASE_VEL = 2
PROP_FINE_PITCH = 3
PROP_PANNING = 4
PROP_MOD_X = 5
PROP_MOD_Y = 6
PROP_SHIFT = 7
PROP_NAMES = ["Pitch", "Velocity", "Rel Vel", "Fine Pitch", "Panning", "Mod X", "Mod Y", "Shift"]

# ---------------------------------------------------------------- verified APC40 MkI map
N_REC, N_SOLO, N_ACT, N_SEL, N_STOP = 48, 49, 50, 51, 52
GRID_NOTES = [53, 54, 55, 56, 57]
FX_ROW_NOTES = GRID_NOTES + [N_STOP, N_ACT, N_SOLO, N_REC, N_SEL]
NOTE_TO_FX_ROW = dict((n, i) for i, n in enumerate(FX_ROW_NOTES))
SCENE_NOTES = [82, 83, 84, 85, 86, 87, 88, 89]
N_MASTER_SEL, N_STOP_ALL = 80, 81
N_PAN, N_SEND_A, N_SEND_B, N_SEND_C = 87, 88, 89, 90
N_BANK_UP, N_BANK_DOWN, N_BANK_RIGHT, N_BANK_LEFT = 94, 95, 96, 97
N_SHIFT = 98
TRACK_KNOB_CC = list(range(48, 56))
DEVICE_KNOB_CC = list(range(16, 24))
CC_FADER, CC_MASTER, CC_CUE = 7, 14, 47
RING_TYPE_TRACK = list(range(56, 64))
RING_TYPE_DEVICE = list(range(24, 32))

CATEGORY_KEYWORDS = [
    (1, ("limiter", "compress", "maximus", "gate", "transient", "clipper", "squeeze", "multiband", "expander", "dynamics",
         "de-ess", "deess", "leveler", "levelling", "distort", "overdrive", "saturat", "waveshap", "bitcrush", "crusher",
         "fuzz", "tube", "blood", "soundgoodizer", "tape")),
    (2, ("reverb", "reeverb", "delay", "echo", "convolv", "luxeverb", "chorus", "flang", "phaser", "tremolo", "vibrato",
         "vocoder", "gross beat", "granul", "pitcher", "emphasis", "wobble", "autopan", "spatial", "hall", "plate", "space")),
]
CATEGORY_VEL = {0: 1, 1: 3, 2: 5}

LED_OFF, LED_GREEN, LED_GREEN_BLINK, LED_RED, LED_RED_BLINK, LED_ORANGE, LED_ORANGE_BLINK = 0, 1, 2, 3, 4, 5, 6
RING_OFF, RING_SINGLE, RING_VOLUME, RING_PAN = 0, 1, 2, 3

ALL_LED_KEYS = ([(c, n) for c in range(NUM_COLS) for n in (N_REC, N_SOLO, N_ACT, N_SEL, N_STOP) + tuple(GRID_NOTES)]
                + [(0, n) for n in SCENE_NOTES + [N_MASTER_SEL, N_PAN, N_SEND_A, N_SEND_B, N_SEND_C]])


def send_midi(status, d1, d2):
    device.midiOutMsg(status | (d1 << 8) | (d2 << 16))


class App:
    def __init__(self):
        self.mode = MODE_MIXER
        self.base = 1
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
        self.touched = {}
        self.fine = {}
        self.cat = {}
        self.focus_fn = None
        self.focus_warned = False
        # Channel Rack state
        self.cr_level = CR_LEVEL_SELECT
        self.cr_channel_base = 0
        self.cr_sel_channel = 0
        self.cr_focused_step = 0            # step index (0-127)
        self.cr_pattern_length = 32
        self.cr_property = PROP_VELOCITY
        self.cr_nudge_value = 0.0

    # ------------------------------------------------------------ output
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
        except Exception:
            pass

    # ------------------------------------------------------------ helpers
    def track_of(self, col):
        return self.base + col

    def slot_present(self, track, slot):
        try:
            return bool(plugins.isValid(track, slot))
        except Exception:
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
        except Exception:
            return 0
        for cat, words in CATEGORY_KEYWORDS:
            if any(w in name for w in words):
                return cat
        return 0

    def focus_plugin(self):
        if not (FOCUS_ON_SELECT and self.sel_present()):
            return
        candidates = [("mixer", mixer, "focusEditor"), ("mixer", mixer, "showEditor"),
                      ("plugins", plugins, "showEditor"), ("plugins", plugins, "focusEditor")]
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
            except Exception:
                pass

    def sel_present(self):
        return self.slot_present(self.sel_track, self.sel_slot)

    def refresh_selected(self):
        if self.sel_present():
            try:
                self.pname = plugins.getPluginName(self.sel_track, self.sel_slot)
                self.pcount = plugins.getParamCount(self.sel_track, self.sel_slot)
            except Exception:
                self.pname, self.pcount = "?", 0
        else:
            self.pname, self.pcount = "", 0
        self.bank = max(0, min(self.bank, self.max_bank()))

    def max_bank(self):
        return max(0, (self.pcount - 1) // BANK_SIZE) if self.pcount else 0

    def param_value(self, p):
        try:
            return float(plugins.getParamValue(p, self.sel_track, self.sel_slot))
        except Exception:
            return None

    def set_param(self, p, v):
        try:
            plugins.setParamValue(float(v), p, self.sel_track, self.sel_slot)
        except Exception:
            pass

    def select_track(self, track):
        self.sel_track = track
        self.last_fl_track = track
        try:
            mixer.setActiveTrack(track)
        except Exception:
            pass

    # ------------------------------------------------------------ Channel Rack helpers
    def channel_count(self):
        try:
            return channels.channelCount()
        except Exception:
            return 0

    def selected_channel(self):
        try:
            return channels.selectedChannel(0, 0, 1)
        except Exception:
            return 0

    def grid_bit(self, ch, step):
        try:
            return bool(channels.getGridBit(ch, step))
        except Exception:
            return False

    def set_grid_bit(self, ch, step, value):
        try:
            channels.setGridBit(ch, step, 1 if value else 0)
        except Exception:
            pass

    def channel_muted(self, ch):
        try:
            return bool(channels.isChannelMuted(ch))
        except Exception:
            return False

    def channel_solo(self, ch):
        try:
            return bool(channels.isChannelSolo(ch))
        except Exception:
            return False

    def channel_name(self, ch):
        try:
            return channels.getChannelName(ch)
        except Exception:
            return "?"

    def set_step_property(self, ch, step, prop, value):
        """Set a step's note property. value: 0.0-1.0"""
        try:
            if hasattr(channels, "setStepParameter"):
                channels.setStepParameter(ch, step, prop, value)
                return True
        except Exception:
            pass
        try:
            if hasattr(channels, "setGridBitValue") and prop == PROP_VELOCITY:
                channels.setGridBitValue(ch, step, value)
                return True
        except Exception:
            pass
        return False

    def get_step_property(self, ch, step, prop):
        try:
            if hasattr(channels, "getStepParameter"):
                return float(channels.getStepParameter(ch, step, prop))
        except Exception:
            pass
        return None

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
                if row < 5:
                    steady = CATEGORY_VEL[self.cat.get((track, row), 0)]
                    vel = (steady + 1 if present else LED_RED_BLINK) if selected else (steady if present else LED_OFF)
                elif selected:
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
            except Exception:
                pass
            want[(col, N_SEL)] = 1 if t == self.sel_track else 0

    def render_channels(self, want):
        if self.cr_level == CR_LEVEL_SELECT:
            self.render_channels_select(want)
        elif self.cr_level == CR_LEVEL_SEQ:
            self.render_channels_seq(want)
        else:
            self.render_channels_props(want)

    def render_channels_select(self, want):
        """Level 1: 40 channel slots per bank. Green = active, Red = muted, Blink = selected."""
        ch_count = self.channel_count()
        sel_ch = self.cr_sel_channel
        base = self.cr_channel_base

        for row in range(5):
            note = GRID_NOTES[row]
            for col in range(NUM_COLS):
                ch_idx = base + row * NUM_COLS + col
                if ch_idx >= ch_count:
                    want[(col, note)] = LED_OFF
                    continue
                muted = self.channel_muted(ch_idx)
                is_selected = (ch_idx == sel_ch)
                if is_selected:
                    # Blink: red if muted, green if active
                    want[(col, note)] = LED_RED_BLINK if muted else LED_GREEN_BLINK
                else:
                    want[(col, note)] = LED_RED if muted else LED_GREEN

        # Rows 6-10: single-channel shortcuts for selected channel
        want[(0, N_STOP)] = 1               # clear indicator
        want[(0, N_ACT)] = 0 if self.channel_muted(sel_ch) else 1  # mute state
        want[(0, N_SOLO)] = 1 if self.channel_solo(sel_ch) else 0  # solo state
        # Level indicator: light up row 10 to show Level 1
        for col in range(NUM_COLS):
            want[(col, N_SEL)] = 1 if col == 0 else 0
        # Property indicator off in Level 1
        for col in range(NUM_COLS):
            want[(col, N_REC)] = 0

        # Scene buttons: pattern length
        for i, scene_note in enumerate(SCENE_NOTES):
            want[(0, scene_note)] = 1 if i < len(CR_PATTERN_LENGTHS) else 0

    def render_channels_seq(self, want):
        """Level 2: 40 step positions for selected channel."""
        sel_ch = self.cr_sel_channel
        ch_count = self.channel_count()

        # Grid: 40 step positions (5 rows x 8 cols)
        for row in range(5):
            note = GRID_NOTES[row]
            for col in range(NUM_COLS):
                step = row * NUM_COLS + col
                if step >= self.cr_pattern_length or sel_ch >= ch_count:
                    want[(col, note)] = LED_OFF
                    continue
                bit = self.grid_bit(sel_ch, step)
                is_focused = (step == self.cr_focused_step)
                if is_focused:
                    want[(col, note)] = LED_GREEN_BLINK if bit else (2 if self.blink_on else 0)
                else:
                    want[(col, note)] = LED_GREEN if bit else LED_OFF

        # Row 6 (Clip Stop): clear indicator
        want[(0, N_STOP)] = 1
        # Row 7 (Activator): mute state of selected channel
        want[(0, N_ACT)] = 0 if self.channel_muted(sel_ch) else 1
        # Row 8 (Solo)
        want[(0, N_SOLO)] = 1 if self.channel_solo(sel_ch) else 0
        # Row 9 (Record Arm): property indicators off in Level 2
        for col in range(NUM_COLS):
            want[(col, N_REC)] = 0
        # Row 10 (Track Select): Level 2 indicator (col 1 lit)
        for col in range(NUM_COLS):
            want[(col, N_SEL)] = 1 if col == 1 else 0

        for i, scene_note in enumerate(SCENE_NOTES):
            want[(0, scene_note)] = 1 if i < len(CR_PATTERN_LENGTHS) else 0

    def render_channels_props(self, want):
        """Level 3: note properties for focused step."""
        sel_ch = self.cr_sel_channel
        focused = self.cr_focused_step

        # Grid: show step context with focused step highlighted
        for row in range(5):
            note = GRID_NOTES[row]
            for col in range(NUM_COLS):
                step = row * NUM_COLS + col
                if step >= self.cr_pattern_length:
                    want[(col, note)] = LED_OFF
                    continue
                bit = self.grid_bit(sel_ch, step)
                is_focused = (step == focused)
                if is_focused:
                    # Focused step: bright (orange to distinguish from Level 2)
                    want[(col, note)] = LED_ORANGE_BLINK if self.blink_on else LED_ORANGE
                else:
                    want[(col, note)] = LED_GREEN if bit else LED_OFF

        # Row 6: clear
        want[(0, N_STOP)] = 1
        # Row 7: mute state
        want[(0, N_ACT)] = 0 if self.channel_muted(sel_ch) else 1
        # Row 8: solo state
        want[(0, N_SOLO)] = 1 if self.channel_solo(sel_ch) else 0
        # Row 9 (Record Arm): property selection — lit pad = current property
        for col in range(NUM_COLS):
            want[(col, N_REC)] = 1 if col == self.cr_property else 0
        # Row 10: Level 3 indicator (col 2 lit)
        for col in range(NUM_COLS):
            want[(col, N_SEL)] = 1 if col == 2 else 0

        for i, scene_note in enumerate(SCENE_NOTES):
            want[(0, scene_note)] = 1 if i < len(CR_PATTERN_LENGTHS) else 0

    def render_ring_types(self):
        fx = self.mode == MODE_FX
        cr = self.mode == MODE_CHANNELS
        for i in range(8):
            if cr:
                self.ring_type(RING_TYPE_TRACK[i], RING_VOLUME)
                self.ring_type(RING_TYPE_DEVICE[i], RING_VOLUME)
            else:
                self.ring_type(RING_TYPE_TRACK[i], RING_VOLUME if fx else RING_PAN)
                self.ring_type(RING_TYPE_DEVICE[i], RING_VOLUME if fx else RING_OFF)

    def ring_type(self, cc, value):
        key = ("type", cc)
        if self.cc_sent.get(key) != value:
            self.cc_sent[key] = value
            send_midi(0xB0, cc, value)

    def sync_rings(self, force=False):
        now = self.clock()
        if self.mode == MODE_FX:
            for k in range(16):
                cc = TRACK_KNOB_CC[k] if k < 8 else DEVICE_KNOB_CC[k - 8]
                if not force and now - self.touched.get(cc, -99.0) < TOUCH_HOLD_SECONDS:
                    continue
                p = self.bank * BANK_SIZE + k
                v = self.param_value(p) if (self.sel_present() and p < self.pcount) else 0.0
                target = int(round(max(0.0, min(1.0, v or 0.0)) * 127))
                if not force and abs(target - self.cc_sent.get(cc, -99)) < RING_MIN_DELTA:
                    continue
                self.ring(cc, target)
        elif self.mode == MODE_CHANNELS:
            sel_ch = self.cr_sel_channel
            # Track knobs = steps 0-7 (or 8-15 depending on level)
            for k in range(8):
                cc = TRACK_KNOB_CC[k]
                step = self.cr_focused_step - 4 + k  # show values around focused step
                if step < 0 or step >= self.cr_pattern_length:
                    self.ring(cc, 0)
                    continue
                v = self.get_step_property(sel_ch, step, self.cr_property)
                self.ring(cc, int((v or 0.0) * 127))
                cc2 = DEVICE_KNOB_CC[k]
                step2 = self.cr_focused_step + 4 + k
                if step2 < 0 or step2 >= self.cr_pattern_length:
                    self.ring(cc2, 0)
                    continue
                v2 = self.get_step_property(sel_ch, step2, self.cr_property)
                self.ring(cc2, int((v2 or 0.0) * 127))
        else:
            for i in range(8):
                if not force and now - self.touched.get(TRACK_KNOB_CC[i], -99.0) < TOUCH_HOLD_SECONDS:
                    continue
                try:
                    pan = mixer.getTrackPan(self.track_of(i))
                except Exception:
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
                self.sync_rings(True)
            return
        if not down:
            return
        if note == N_PAN:
            return self.set_mode(MODE_MIXER)
        if note == N_SEND_A:
            return self.set_mode(MODE_FX)
        if note == N_SEND_B:
            return self.set_mode(MODE_CHANNELS)
        if note == N_SEND_C:
            self.hint("Send C: Playlist mode (not yet implemented)")
            return
        if note == N_MASTER_SEL:
            if self.mode == MODE_CHANNELS:
                # Cycle levels
                if self.shift:
                    # Cycle modes
                    if self.mode == MODE_MIXER:
                        return self.set_mode(MODE_FX)
                    elif self.mode == MODE_FX:
                        return self.set_mode(MODE_CHANNELS)
                    else:
                        return self.set_mode(MODE_MIXER)
                else:
                    # Cycle Channel Rack levels
                    if self.cr_level == CR_LEVEL_SELECT:
                        self.cr_level = CR_LEVEL_SEQ
                        self.cr_focused_step = 0
                        self.hint("Step Sequencer (Level 2)")
                    elif self.cr_level == CR_LEVEL_SEQ:
                        self.cr_level = CR_LEVEL_PROPS
                        self.hint("Note Properties (Level 3) - %s" % PROP_NAMES[self.cr_property])
                    else:
                        self.cr_level = CR_LEVEL_SELECT
                        self.hint("Channel Select (Level 1)")
                    self.render(True)
                return
            else:
                if self.shift:
                    # Cycle modes
                    if self.mode == MODE_MIXER:
                        return self.set_mode(MODE_FX)
                    elif self.mode == MODE_FX:
                        return self.set_mode(MODE_CHANNELS)
                    else:
                        return self.set_mode(MODE_MIXER)
                return
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
        self.rearm_faders()
        self.led_sent.clear()
        self.scan_present()
        self.refresh_selected()
        if mode == MODE_CHANNELS:
            self.cr_level = CR_LEVEL_SELECT
            self.cr_channel_base = 0
            self.cr_sel_channel = self.selected_channel()
            self.cr_focused_step = 0
        self.render(True)
        self.hint("Mode: %s" % mode.upper())

    def shift_tracks(self, delta):
        if self.mode == MODE_CHANNELS:
            if self.cr_level == CR_LEVEL_SELECT:
                # Scroll channel bank
                self.cr_channel_base = max(0, self.cr_channel_base + delta)
                self.hint("Channel bank: %d" % self.cr_channel_base)
            elif self.cr_level == CR_LEVEL_SEQ:
                # Scroll focused step
                new_step = max(0, min(self.cr_pattern_length - 1, self.cr_focused_step + delta // 2))
                self.cr_focused_step = new_step
                self.hint("Step: %d" % (new_step + 1))
            else:
                # Scroll focused step in props mode
                new_step = max(0, min(self.cr_pattern_length - 1, self.cr_focused_step + delta // 2))
                self.cr_focused_step = new_step
                self.hint("Step: %d" % (new_step + 1))
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

    # ------------------------------------------------------------ Channel Rack handlers
    def channels_button(self, ch, note):
        ch_count = self.channel_count()
        sel_ch = self.cr_sel_channel

        # Grid pads (rows 1-5)
        if note in NOTE_TO_FX_ROW:
            row = NOTE_TO_FX_ROW[note]
            if row < 5 and ch < NUM_COLS:
                if self.cr_level == CR_LEVEL_SELECT:
                    ch_idx = self.cr_channel_base + row * NUM_COLS + ch
                    if ch_idx < ch_count:
                        if self.shift:
                            # Shift + pad = toggle mute
                            try:
                                channels.muteChannel(ch_idx, not self.channel_muted(ch_idx))
                            except Exception:
                                pass
                            self.hint("Channel %d: %s" % (ch_idx, "muted" if self.channel_muted(ch_idx) else "active"))
                        else:
                            # Select channel
                            self.cr_sel_channel = ch_idx
                            try:
                                channels.selectOneChannel(ch_idx)
                            except Exception:
                                pass
                            self.hint("Channel %d: %s" % (ch_idx, self.channel_name(ch_idx)))
                elif self.cr_level == CR_LEVEL_SEQ:
                    step = row * NUM_COLS + ch
                    if step < self.cr_pattern_length:
                        if self.shift:
                            # Shift + pad = enter Level 3 for this step
                            self.cr_focused_step = step
                            self.cr_level = CR_LEVEL_PROPS
                            self.hint("Note Properties for step %d" % (step + 1))
                        else:
                            # Toggle step
                            bit = self.grid_bit(sel_ch, step)
                            self.set_grid_bit(sel_ch, step, 0 if bit else 1)
                else:  # CR_LEVEL_PROPS
                    step = row * NUM_COLS + ch
                    if step < self.cr_pattern_length:
                        # Select focused step
                        self.cr_focused_step = step
                        self.hint("Step %d" % (step + 1))
                self.render(True)
            return

        # Row 6 (Clip Stop): clear selected channel
        if note == N_STOP and ch < NUM_COLS:
            if ch == 0:
                for step in range(self.cr_pattern_length):
                    self.set_grid_bit(sel_ch, step, 0)
                self.hint("Cleared channel %d" % sel_ch)
            self.render()
            return

        # Row 7 (Activator): mute
        if note == N_ACT and ch < NUM_COLS:
            if ch == 0:
                try:
                    channels.muteChannel(sel_ch, not self.channel_muted(sel_ch))
                except Exception:
                    pass
            self.render()
            return

        # Row 8 (Solo): solo
        if note == N_SOLO and ch < NUM_COLS:
            if ch == 0:
                try:
                    channels.soloChannel(sel_ch, not self.channel_solo(sel_ch))
                except Exception:
                    pass
            self.render()
            return

        # Row 9 (Record Arm): property mode select (only in Level 3)
        if note == N_REC and ch < NUM_COLS:
            if self.cr_level == CR_LEVEL_PROPS and ch < 8:
                self.cr_property = ch
                self.hint("Property: %s" % PROP_NAMES[ch])
                self.render(True)
            return

        # Row 10 (Track Select): level jump
        if note == N_SEL and ch < NUM_COLS:
            if ch == 0:
                self.cr_level = CR_LEVEL_SELECT
                self.hint("Channel Select (Level 1)")
            elif ch == 1:
                self.cr_level = CR_LEVEL_SEQ
                self.hint("Step Sequencer (Level 2)")
            elif ch == 2:
                self.cr_level = CR_LEVEL_PROPS
                self.hint("Note Properties (Level 3)")
            self.render(True)
            return

        # Stop All: clear all steps in pattern
        if note == N_STOP_ALL:
            for c in range(ch_count):
                for step in range(self.cr_pattern_length):
                    self.set_grid_bit(c, step, 0)
            self.hint("Cleared all steps")
            self.render()
            return

        # Bank Up/Down: scroll channels by 1
        if note == N_BANK_UP:
            new_ch = max(0, sel_ch - 1)
            self.cr_sel_channel = new_ch
            try:
                channels.selectOneChannel(new_ch)
            except Exception:
                pass
            self.hint("Channel %d: %s" % (new_ch, self.channel_name(new_ch)))
            self.render()
            return
        if note == N_BANK_DOWN:
            new_ch = min(ch_count - 1, sel_ch + 1)
            self.cr_sel_channel = new_ch
            try:
                channels.selectOneChannel(new_ch)
            except Exception:
                pass
            self.hint("Channel %d: %s" % (new_ch, self.channel_name(new_ch)))
            self.render()
            return

        # Scene buttons: pattern length
        if note in SCENE_NOTES:
            scene_idx = SCENE_NOTES.index(note)
            if scene_idx < len(CR_PATTERN_LENGTHS):
                self.cr_pattern_length = CR_PATTERN_LENGTHS[scene_idx]
                if self.cr_focused_step >= self.cr_pattern_length:
                    self.cr_focused_step = 0
                self.hint("Pattern length: %d steps" % self.cr_pattern_length)
            self.render(True)
            return

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
            except Exception:
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
        except Exception as e:
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
        if self.mode == MODE_FX:
            self.cue_accum += delta
            while abs(self.cue_accum) >= 4:
                step = 1 if self.cue_accum > 0 else -1
                self.cue_accum -= step * 4
                self.change_bank(step)
            self.render()
        elif self.mode == MODE_CHANNELS:
            self.cue_accum += delta
            while abs(self.cue_accum) >= CUE_TICKS_PER_CHANNEL:
                step = 1 if self.cue_accum > 0 else -1
                self.cue_accum -= step * CUE_TICKS_PER_CHANNEL
                if self.cr_level == CR_LEVEL_SELECT:
                    # Scroll channels
                    new_ch = max(0, min(self.channel_count() - 1, self.cr_sel_channel + step))
                    if new_ch != self.cr_sel_channel:
                        self.cr_sel_channel = new_ch
                        try:
                            channels.selectOneChannel(new_ch)
                        except Exception:
                            pass
                        self.hint("Channel %d: %s" % (new_ch, self.channel_name(new_ch)))
                else:
                    # Scroll focused step
                    new_step = max(0, min(self.cr_pattern_length - 1, self.cr_focused_step + step))
                    if new_step != self.cr_focused_step:
                        self.cr_focused_step = new_step
                        self.hint("Step: %d" % (new_step + 1))
            self.render()

    def knob(self, k, value, cc):
        self.touched[cc] = self.clock()
        if self.mode == MODE_FX:
            p = self.bank * BANK_SIZE + k
            if self.sel_present() and p < self.pcount:
                if self.shift:
                    if cc not in self.fine:
                        self.fine[cc] = (value, self.param_value(p) or 0.0)
                    k0, p0 = self.fine[cc]
                    self.set_param(p, max(0.0, min(1.0, p0 + (value - k0) / 127.0 * FINE_SCALE)))
                else:
                    self.set_param(p, value / 127.0)
                if self.shift:
                    self.cc_sent.pop(cc, None)
                else:
                    self.cc_sent[cc] = value
                try:
                    self.hint("%s  %s: %s" % (self.pname, plugins.getParamName(p, self.sel_track, self.sel_slot),
                                              plugins.getParamValueString(p, self.sel_track, self.sel_slot)))
                except Exception:
                    pass
        elif self.mode == MODE_CHANNELS:
            # In Channel Rack mode, knobs edit note property for a specific step
            sel = self.cr_sel_channel
            # Track knobs = steps around focused step (focused - 4 to focused + 3)
            if k < 8:
                step = self.cr_focused_step - 4 + k
            else:
                step = self.cr_focused_step + 4 + (k - 8)
            if 0 <= step < self.cr_pattern_length:
                self.set_step_property(sel, step, self.cr_property, value / 127.0)
                self.cc_sent[cc] = value
                self.hint("Step %d %s: %d" % (step + 1, PROP_NAMES[self.cr_property], value))
        elif k < 8:
            try:
                mixer.setTrackPan(self.track_of(k), value / 127.0 * 2.0 - 1.0)
            except Exception:
                pass
            self.cc_sent[cc] = value

    def fader(self, idx, pos):
        prev, self.fader_pos[idx] = self.fader_pos[idx], pos
        if idx == 8:
            # Master fader = nudge (in Channel Rack mode)
            if self.mode == MODE_CHANNELS:
                self.cr_nudge_value = (pos - 0.5) * 2.0
                self.hint("Nudge: %.2f" % self.cr_nudge_value)
                return
            getter = lambda: self.safe(mixer.getTrackVolume, 0)
            setter = lambda v: mixer.setTrackVolume(0, v)
        elif self.mode == MODE_CHANNELS:
            # Faders edit note property for steps in current page
            sel = self.cr_sel_channel
            step = idx  # fader 1-8 = steps 0-7 of current page
            if step < self.cr_pattern_length:
                self.set_step_property(sel, step, self.cr_property, pos)
                self.hint("Step %d %s: %d" % (step + 1, PROP_NAMES[self.cr_property], int(pos * 127)))
            return
        elif self.mode == MODE_FX:
            p = self.bank * BANK_SIZE + 16 + idx
            if not self.sel_present() or p >= self.pcount:
                return
            getter = lambda: self.param_value(p)
            setter = lambda v: self.set_param(p, v)
        else:
            t = self.track_of(idx)
            getter = lambda: self.safe(mixer.getTrackVolume, t)
            setter = lambda v: mixer.setTrackVolume(t, v)
        if not self.fader_armed[idx]:
            target = getter()
            if target is None:
                return
            crossed = prev is not None and (prev - target) * (pos - target) <= 0
            if abs(pos - target) > PICKUP_TOLERANCE and not crossed:
                return
            self.fader_armed[idx] = True
        try:
            setter(pos)
        except Exception:
            pass

    @staticmethod
    def safe(fn, *args):
        try:
            return float(fn(*args))
        except Exception:
            return None

    # ------------------------------------------------------------ periodic work
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
            if self.mode == MODE_CHANNELS:
                cur = self.selected_channel()
                if cur != self.cr_sel_channel:
                    self.cr_sel_channel = cur
                    redraw = True
            tn = self.safe(mixer.trackNumber)
            if tn is not None:
                tn = int(tn)
                if tn != self.last_fl_track:
                    self.last_fl_track = tn
                    if self.mode != MODE_CHANNELS and self.base <= tn < self.base + NUM_COLS and tn != self.sel_track:
                        self.sel_track = tn
                        self.refresh_selected()
                        redraw = True
            if self.mode == MODE_MIXER:
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
        self.cr_sel_channel = self.selected_channel()
        self.render()
        print("APC40 Control v0.4 ready: mode=%s" % self.mode)

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
    event.handled = True


def OnIdle():
    if _app is not None:
        _app.tick(time.time())


def OnRefresh(flags):
    if _app is not None:
        _app.t_scan = 0.0