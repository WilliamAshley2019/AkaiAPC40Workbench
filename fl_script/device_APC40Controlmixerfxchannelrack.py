# name=APC40 MkI Control (Mixer + FX + Channel Rack)
# supportedDevices=APC40
#
# Akai APC40 MkI (original) control script for FL Studio 2026.1.7+.   v0.2
# Addresses come from the Workbench Learn run (137/137 matched) - see docs/APC40_PROTOCOL_NOTES.md.
# Only FL API calls verified in the IL-Group API stubs are used (plugins.*, mixer track functions, mixer.setActiveTrack,
# channels.* for Channel Rack mode).
#
# MODES  (PAN = Mixer, SEND A = FX, SEND B = Channel Rack; SHIFT + MASTER toggles between Mixer/FX)
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
#   CHANNELS (Send B): rows 1-5 = step sequencer for 5 channels x 8 steps per page.
#          Press pads to toggle steps.  Row 6 = select channel, Row 7 = mute, Row 8 = solo, Row 9 = arm,
#          Row 10 = jump to step page.  Bank LEFT/RIGHT = step page scroll.  CUE LEVEL = step page scroll.
#          Track knobs = velocity for steps 1-8 (where supported), Device knobs = steps 9-16.
#          Faders = step pan (where supported).  Master fader = selected channel volume.
#          SCENE 1/2/3 = Fill Each 2/4/8, SCENE 4/5 = Rotate L/R, SCENE 6 = Clone Loop, SCENE 7 = Clear Steps,
#          SCENE 8 = Toggle 5ch/8ch view.  Stop All = clear all steps in pattern.
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

# ---------------------------------------------------------------- Channel Rack mode config
MODE_MIXER = "mixer"
MODE_FX = "fx"
MODE_CHANNELS = "channels"
CR_VISIBLE_STEPS = 8        # steps visible per page (one row of 8 pads)
CR_VISIBLE_CHANNELS = 5     # channels shown in rows 1-5
CR_MAX_STEPS = 64           # max steps to scan (FL supports up to 512, but 64 is practical)
CR_VELOCITY_MAX = 127

# ---------------------------------------------------------------- verified APC40 MkI map
N_REC, N_SOLO, N_ACT, N_SEL, N_STOP = 48, 49, 50, 51, 52
GRID_NOTES = [53, 54, 55, 56, 57]
FX_ROW_NOTES = GRID_NOTES + [N_STOP, N_ACT, N_SOLO, N_REC, N_SEL]       # matrix row 0..9 -> note
NOTE_TO_FX_ROW = dict((n, i) for i, n in enumerate(FX_ROW_NOTES))
SCENE_NOTES = [82, 83, 84, 85, 86, 87, 88, 89]                          # 8 scene launch buttons
N_MASTER_SEL, N_STOP_ALL = 80, 81
N_PAN, N_SEND_A, N_SEND_B, N_SEND_C = 87, 88, 89, 90
N_BANK_UP, N_BANK_DOWN, N_BANK_RIGHT, N_BANK_LEFT = 94, 95, 96, 97
N_SHIFT = 98
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
        # Channel Rack mode state
        self.cr_step_offset = 0             # which step page we're viewing (0, 8, 16, ...)
        self.cr_view_mode = 0               # 0 = 5ch view, 1 = 8ch view
        self.cr_selected_ch = 0             # cached selected channel for CR mode

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
        except Exception:
            pass

    # ------------------------------------------------------------ FL state helpers
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
            except Exception as e:
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
        except Exception as e:
            print("APC40: param write error:", e)

    def select_track(self, track):
        self.sel_track = track
        self.last_fl_track = track
        try:
            mixer.setActiveTrack(track)
        except Exception:
            try:
                mixer.setTrackNumber(track)
            except Exception as e:
                print("APC40: select track error:", e)

    # ------------------------------------------------------------ FL channels helpers (Channel Rack mode)
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
        except Exception as e:
            print("APC40: setGridBit error:", e)

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

    def channel_armed(self, ch):
        try:
            return bool(channels.isChannelArmed(ch))
        except Exception:
            return False

    def channel_name(self, ch):
        try:
            return channels.getChannelName(ch)
        except Exception:
            return "?"

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
        """Channel Rack mode: 5 channels x 8 steps, plus channel controls on rows 6-10."""
        ch_count = self.channel_count()
        sel_ch = self.selected_channel()
        step_base = self.cr_step_offset

        # Rows 1-5: step sequencer grid (5 channels x 8 steps)
        for row in range(CR_VISIBLE_CHANNELS):
            if row >= ch_count:
                continue
            note = GRID_NOTES[row]
            for col in range(NUM_COLS):
                step = step_base + col
                if step >= CR_MAX_STEPS:
                    want[(col, note)] = 0
                    continue
                bit = self.grid_bit(row, step)
                if row == sel_ch:
                    # Selected channel: bright blink for active steps
                    want[(col, note)] = 2 if (bit and self.blink_on) else (1 if bit else 0)
                else:
                    want[(col, note)] = 1 if bit else 0

        # Row 6 (Clip Stop): channel select
        for col in range(NUM_COLS):
            if col < ch_count:
                want[(col, N_STOP)] = 1 if col == sel_ch else 0

        # Row 7 (Activator): mute
        for col in range(NUM_COLS):
            if col < ch_count:
                want[(col, N_ACT)] = 0 if self.channel_muted(col) else 1

        # Row 8 (Solo): solo
        for col in range(NUM_COLS):
            if col < ch_count:
                want[(col, N_SOLO)] = 1 if self.channel_solo(col) else 0

        # Row 9 (Record Arm): arm
        for col in range(NUM_COLS):
            if col < ch_count:
                want[(col, N_REC)] = 1 if self.channel_armed(col) else 0

        # Row 10 (Track Select): step page jump indicators
        current_page = step_base // CR_VISIBLE_STEPS
        for col in range(NUM_COLS):
            want[(col, N_SEL)] = 1 if col == current_page else 0

        # Scene buttons show CR-specific state
        want[(0, SCENE_NOTES[0])] = 1  # Fill 2
        want[(0, SCENE_NOTES[1])] = 1  # Fill 4
        want[(0, SCENE_NOTES[2])] = 1  # Fill 8
        want[(0, SCENE_NOTES[3])] = 1  # Rotate L
        want[(0, SCENE_NOTES[4])] = 1  # Rotate R
        want[(0, SCENE_NOTES[5])] = 1  # Clone
        want[(0, SCENE_NOTES[6])] = 1  # Clear
        want[(0, SCENE_NOTES[7])] = 1  # Toggle view

    def render_ring_types(self):
        fx = self.mode == MODE_FX
        cr = self.mode == MODE_CHANNELS
        for i in range(8):
            if cr:
                # Channel Rack: track knobs = velocity (RING_VOLUME style), device knobs = velocity
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
            # Channel Rack: rings show velocity for the selected channel's steps
            sel_ch = self.selected_channel()
            for k in range(8):
                cc = TRACK_KNOB_CC[k]
                if not force and now - self.touched.get(cc, -99.0) < TOUCH_HOLD_SECONDS:
                    continue
                # Try to read step velocity if the API supports it
                step = self.cr_step_offset + k
                vel = self.get_step_velocity(sel_ch, step)
                self.ring(cc, vel if vel is not None else 0)
                cc2 = DEVICE_KNOB_CC[k]
                if not force and now - self.touched.get(cc2, -99.0) < TOUCH_HOLD_SECONDS:
                    continue
                step2 = self.cr_step_offset + 8 + k
                vel2 = self.get_step_velocity(sel_ch, step2)
                self.ring(cc2, vel2 if vel2 is not None else 0)
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

    def get_step_velocity(self, ch, step):
        """Try to read step velocity. Returns 0-127 or None if unsupported."""
        try:
            # Try various API names that may exist in different FL builds
            if hasattr(channels, "getStepVelocity"):
                v = channels.getStepVelocity(ch, step)
                return int(round(v * 127)) if v is not None else None
            if hasattr(channels, "getGridBitValue"):
                v = channels.getGridBitValue(ch, step)
                return int(round(v * 127)) if v is not None else None
        except Exception:
            pass
        return None

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
        if note == N_MASTER_SEL and self.shift:
            # Cycle through modes
            if self.mode == MODE_MIXER:
                return self.set_mode(MODE_FX)
            elif self.mode == MODE_FX:
                return self.set_mode(MODE_CHANNELS)
            else:
                return self.set_mode(MODE_MIXER)
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
            self.cr_step_offset = 0
            self.cr_selected_ch = self.selected_channel()
        self.render(True)
        self.hint("Mode: %s" % mode.upper())

    def shift_tracks(self, delta):
        if self.mode == MODE_CHANNELS:
            # In Channel Rack mode, bank left/right scrolls step pages
            new_offset = self.cr_step_offset + (delta // NUM_COLS) * CR_VISIBLE_STEPS
            new_offset = max(0, min(CR_MAX_STEPS - CR_VISIBLE_STEPS, new_offset))
            if new_offset != self.cr_step_offset:
                self.cr_step_offset = new_offset
                self.hint("Step page: %d" % (self.cr_step_offset // CR_VISIBLE_STEPS + 1))
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

    # ------------------------------------------------------------ Channel Rack mode handlers
    def channels_button(self, ch, note):
        """Handle Channel Rack mode button presses with full 10-row grid."""
        ch_count = self.channel_count()
        sel_ch = self.selected_channel()

        # Rows 1-5: step toggling
        if note in NOTE_TO_FX_ROW:
            row = NOTE_TO_FX_ROW[note]
            if row < CR_VISIBLE_CHANNELS and ch < NUM_COLS:
                step = self.cr_step_offset + ch
                if row < ch_count and step < CR_MAX_STEPS:
                    bit = self.grid_bit(row, step)
                    self.set_grid_bit(row, step, 0 if bit else 1)
                    if row != sel_ch:
                        try:
                            channels.selectOneChannel(row)
                        except Exception:
                            pass
                self.render()
            return

        # Row 6 (Clip Stop): select channel
        if note == N_STOP and ch < NUM_COLS:
            if ch < ch_count:
                try:
                    channels.selectOneChannel(ch)
                except Exception:
                    pass
                self.hint("Channel %d: %s" % (ch, self.channel_name(ch)))
            self.render()
            return

        # Row 7 (Activator): mute
        if note == N_ACT and ch < NUM_COLS:
            if ch < ch_count:
                try:
                    channels.muteChannel(ch, not self.channel_muted(ch))
                except Exception:
                    pass
            self.render()
            return

        # Row 8 (Solo): solo
        if note == N_SOLO and ch < NUM_COLS:
            if ch < ch_count:
                try:
                    channels.soloChannel(ch, not self.channel_solo(ch))
                except Exception:
                    pass
            self.render()
            return

        # Row 9 (Record Arm): arm
        if note == N_REC and ch < NUM_COLS:
            if ch < ch_count:
                try:
                    channels.armChannel(ch, not self.channel_armed(ch))
                except Exception:
                    pass
            self.render()
            return

        # Row 10 (Track Select): step page jump
        if note == N_SEL and ch < NUM_COLS:
            self.cr_step_offset = min(ch * CR_VISIBLE_STEPS, CR_MAX_STEPS - CR_VISIBLE_STEPS)
            self.hint("Step page: %d" % (self.cr_step_offset // CR_VISIBLE_STEPS + 1))
            self.render(True)
            return

        # Stop All: clear all steps in pattern
        if note == N_STOP_ALL:
            for c in range(ch_count):
                for step in range(CR_MAX_STEPS):
                    self.set_grid_bit(c, step, 0)
            self.hint("Cleared all steps")
            self.render()
            return

        # Bank Up/Down: scroll channels in CR mode
        if note in (N_BANK_UP, N_BANK_DOWN):
            sel = self.selected_channel() + (-1 if note == N_BANK_UP else 1)
            if 0 <= sel < ch_count:
                try:
                    channels.selectOneChannel(sel)
                except Exception:
                    pass
                self.hint("Channel %d: %s" % (sel, self.channel_name(sel)))
            self.render()
            return

        # Scene Launch buttons: scripted operations
        if note == SCENE_NOTES[0]:
            self.cr_fill_each(2)
        elif note == SCENE_NOTES[1]:
            self.cr_fill_each(4)
        elif note == SCENE_NOTES[2]:
            self.cr_fill_each(8)
        elif note == SCENE_NOTES[3]:
            self.cr_rotate(-1)
        elif note == SCENE_NOTES[4]:
            self.cr_rotate(+1)
        elif note == SCENE_NOTES[5]:
            self.cr_clone_loop()
        elif note == SCENE_NOTES[6]:
            self.cr_clear_selected()
        elif note == SCENE_NOTES[7]:
            self.cr_toggle_view()
        else:
            return
        self.render(True)

    def cr_fill_each(self, interval):
        """Fill selected channel with steps at every `interval`."""
        sel = self.selected_channel()
        for step in range(CR_MAX_STEPS):
            self.set_grid_bit(sel, step, 0)
        for step in range(0, CR_MAX_STEPS, interval):
            self.set_grid_bit(sel, step, 1)
        self.hint("Filled every %d" % interval)
        self.render()

    def cr_rotate(self, direction):
        """Rotate selected channel's step pattern left or right."""
        sel = self.selected_channel()
        # Use 16 steps as the rotation window
        length = 16
        bits = [self.grid_bit(sel, i) for i in range(length)]
        if direction > 0:
            bits = [bits[-1]] + bits[:-1]
        else:
            bits = bits[1:] + [bits[0]]
        for i, v in enumerate(bits):
            self.set_grid_bit(sel, i, v)
        self.hint("Rotated %s" % ("right" if direction > 0 else "left"))
        self.render()

    def cr_clone_loop(self):
        """Duplicate the first 16 steps of the selected channel to steps 17-32."""
        sel = self.selected_channel()
        for i in range(16):
            bit = self.grid_bit(sel, i)
            self.set_grid_bit(sel, 16 + i, bit)
        self.hint("Cloned 16 steps to next page")
        self.render()

    def cr_clear_selected(self):
        """Clear steps for the selected channel only."""
        sel = self.selected_channel()
        for step in range(CR_MAX_STEPS):
            self.set_grid_bit(sel, step, 0)
        self.hint("Cleared channel %d" % sel)
        self.render()

    def cr_toggle_view(self):
        """Toggle between 5-channel and 8-channel step views."""
        self.cr_view_mode = 1 - self.cr_view_mode
        self.hint("View: %s" % ("5ch" if self.cr_view_mode == 0 else "8ch"))
        self.render()

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
            while abs(self.cue_accum) >= CUE_TICKS_PER_BANK:
                step = 1 if self.cue_accum > 0 else -1
                self.cue_accum -= step * CUE_TICKS_PER_BANK
                self.change_bank(step)
            self.render()
        elif self.mode == MODE_CHANNELS:
            # In Channel Rack mode, CUE scrolls step pages
            self.cue_accum += delta
            while abs(self.cue_accum) >= CUE_TICKS_PER_BANK:
                step = 1 if self.cue_accum > 0 else -1
                self.cue_accum -= step * CUE_TICKS_PER_BANK
                new_offset = self.cr_step_offset + step * CR_VISIBLE_STEPS
                new_offset = max(0, min(CR_MAX_STEPS - CR_VISIBLE_STEPS, new_offset))
                if new_offset != self.cr_step_offset:
                    self.cr_step_offset = new_offset
                    self.hint("Step page: %d" % (self.cr_step_offset // CR_VISIBLE_STEPS + 1))
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
            # In Channel Rack mode, knobs edit step velocity
            sel = self.selected_channel()
            step = self.cr_step_offset + (k if k < 8 else (k - 8) + 8)
            if step < CR_MAX_STEPS:
                # Ensure the step is active
                self.set_grid_bit(sel, step, 1)
                # Try to set velocity via API
                self.set_step_velocity(sel, step, value)
                try:
                    self.hint("Step %d vel: %d" % (step + 1, value))
                except Exception:
                    pass
                self.cc_sent[cc] = value
        elif k < 8:
            try:
                mixer.setTrackPan(self.track_of(k), value / 127.0 * 2.0 - 1.0)
            except Exception as e:
                print("APC40: pan error:", e)
            self.cc_sent[cc] = value

    def set_step_velocity(self, ch, step, value):
        """Try to set step velocity. Tries multiple API names."""
        try:
            if hasattr(channels, "setStepVelocity"):
                channels.setStepVelocity(ch, step, value / 127.0)
                return True
            if hasattr(channels, "setGridBitValue"):
                channels.setGridBitValue(ch, step, value / 127.0)
                return True
        except Exception:
            pass
        return False

    def fader(self, idx, pos):
        prev, self.fader_pos[idx] = self.fader_pos[idx], pos
        if idx == 8:
            getter = lambda: self.safe(mixer.getTrackVolume, 0)
            setter = lambda v: mixer.setTrackVolume(0, v)
        elif self.mode == MODE_CHANNELS:
            # In Channel Rack mode, faders edit step pan (or volume if pan unsupported)
            sel = self.selected_channel()
            step = self.cr_step_offset + idx
            if step >= CR_MAX_STEPS:
                return
            # For now, map faders to step velocity as a fallback
            self.set_step_velocity(sel, step, int(pos * 127))
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
        except Exception as e:
            print("APC40: fader error:", e)

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
                # Detect if user changed channel selection in FL
                cur = self.selected_channel()
                if cur != self.cr_selected_ch:
                    self.cr_selected_ch = cur
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
            if self.mode == MODE_FX:
                self.sync_rings()
            elif self.mode == MODE_CHANNELS:
                self.sync_rings()
        if redraw:
            self.render()

    def init(self):
        if SEND_MODE_SYSEX:
            device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x73, 0x60, 0x00, 0x04, MODE_BYTE, 0x09, 0x00, 0x00, 0xF7]))
        self.scan_present()
        self.last_fl_track = self.safe(mixer.trackNumber)
        self.refresh_selected()
        self.cr_selected_ch = self.selected_channel()
        self.render()
        print("APC40 Control v0.2 ready: mode=%s, tracks %d-%d" % (self.mode, self.base, self.base + NUM_COLS - 1))

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