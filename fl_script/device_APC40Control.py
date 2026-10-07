# name=APC40 MkI Control (Mixer + FX)
# supportedDevices=APC40
#
# Akai APC40 MkI (original) control script for FL Studio 2026.1.7+.   v0.1
# Addresses come from the Workbench Learn run (137/137 matched) - see docs/APC40_PROTOCOL_NOTES.md.
# Only FL API calls verified in the IL-Group API stubs are used (plugins.*, mixer track functions, mixer.setActiveTrack).
#
# MODES  (PAN button = Mixer, SEND A button = FX; SHIFT + MASTER toggles)
#   MIXER: faders = track volume, ACTIVATOR = mute, SOLO/CUE = solo, REC = arm, TRACK SELECT = select,
#          track knobs = pan (rings follow), master fader = master volume, bank LEFT/RIGHT = +/- 8 tracks
#   FX:    the 8x10 matrix = 8 mixer tracks x 10 effect slots (rows: 5 clip rows, clip stop, activator, solo, rec, track select)
#          press = select that slot.  Track knobs = params 1-8, device knobs = params 9-16, faders 1-8 = params 17-24 (24 per bank)
#          SCENE 1/2 = param bank -/+,  SCENE 3/4 = prev/next preset,  SCENE 5 = dump params to Script output
#          bank UP/DOWN = previous/next slot, bank LEFT/RIGHT = +/- 8 tracks, CUE LEVEL (relative) = scroll param bank
#          LEDs: green = plugin present, orange = selected plugin, red = selected empty slot, single-colour rows blink the selection
#          knob rings follow plugin parameters (no jump); faders use pickup (they have no feedback)
#
# Install: Documents\Image-Line\FL Studio\Settings\Hardware\APC40Control\device_APC40Control.py
# Then Options > MIDI settings: Input APC40 -> controller type "APC40 MkI Control (Mixer + FX)", set the same port number on the
# matching Output, enable both. Disable FL's built-in APC40 script and close the Workbench first.

import time

import device
import mixer
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
BLINK_SECONDS = 0.4
SCAN_SECONDS = 0.25
POLL_SECONDS = 0.10

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
TRACK_KNOB_CC = list(range(48, 56))
DEVICE_KNOB_CC = list(range(16, 24))
CC_FADER, CC_MASTER, CC_CUE = 7, 14, 47
RING_TYPE_TRACK = list(range(56, 64))
RING_TYPE_DEVICE = list(range(24, 32))

LED_OFF, LED_GREEN, LED_GREEN_BLINK, LED_RED, LED_RED_BLINK, LED_ORANGE, LED_ORANGE_BLINK = 0, 1, 2, 3, 4, 5, 6
RING_OFF, RING_SINGLE, RING_VOLUME, RING_PAN = 0, 1, 2, 3

ALL_LED_KEYS = ([(c, n) for c in range(NUM_COLS) for n in (N_REC, N_SOLO, N_ACT, N_SEL, N_STOP) + tuple(GRID_NOTES)]
                + [(0, n) for n in SCENE_NOTES + [N_MASTER_SEL, N_PAN, N_SEND_A, N_SEND_B, N_SEND_C]])


def send_midi(status, d1, d2):
    device.midiOutMsg(status | (d1 << 8) | (d2 << 16))


class App:
    def __init__(self):
        self.mode = "mixer"
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
        return changed

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
    def render(self):
        want = {}
        want[(0, N_PAN)] = 1 if self.mode == "mixer" else 0
        want[(0, N_SEND_A)] = 1 if self.mode == "fx" else 0
        if self.mode == "fx":
            self.render_fx(want)
        else:
            self.render_mixer(want)
        for ch, note in ALL_LED_KEYS:
            self.led(ch, note, want.get((ch, note), 0))
        self.render_ring_types()
        self.sync_rings()

    def render_fx(self, want):
        for col in range(NUM_COLS):
            track = self.track_of(col)
            for row in range(NUM_SLOTS):
                note = FX_ROW_NOTES[row]
                present = self.present.get((track, row), False)
                selected = (track == self.sel_track and row == self.sel_slot)
                if row < 5:                                   # three-colour clip-launch rows
                    vel = (LED_ORANGE if present else LED_RED) if selected else (LED_GREEN if present else LED_OFF)
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
        fx = self.mode == "fx"
        for i in range(8):
            self.ring_type(RING_TYPE_TRACK[i], RING_VOLUME if fx else RING_PAN)
            self.ring_type(RING_TYPE_DEVICE[i], RING_VOLUME if fx else RING_OFF)

    def ring_type(self, cc, value):
        key = ("type", cc)
        if self.cc_sent.get(key) != value:
            self.cc_sent[key] = value
            send_midi(0xB0, cc, value)

    def sync_rings(self):
        if self.mode == "fx":
            for k in range(16):
                cc = TRACK_KNOB_CC[k] if k < 8 else DEVICE_KNOB_CC[k - 8]
                p = self.bank * BANK_SIZE + k
                v = self.param_value(p) if (self.sel_present() and p < self.pcount) else 0.0
                self.ring(cc, (v or 0.0) * 127)
        else:
            for i in range(8):
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
            return
        if not down:
            return
        if note == N_PAN:
            return self.set_mode("mixer")
        if note == N_SEND_A:
            return self.set_mode("fx")
        if note == N_MASTER_SEL and self.shift:
            return self.set_mode("fx" if self.mode == "mixer" else "mixer")
        if note in (N_BANK_LEFT, N_BANK_RIGHT):
            return self.shift_tracks(-NUM_COLS if note == N_BANK_LEFT else NUM_COLS)
        if self.mode == "fx":
            self.fx_button(ch, note)
        else:
            self.mixer_button(ch, note)

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        self.rearm_faders()
        self.led_sent.clear()                               # force a full, clean repaint of the surface
        self.scan_present()
        self.refresh_selected()
        self.render()

    def shift_tracks(self, delta):
        self.base = max(1, self.base + delta)
        self.rearm_faders()
        self.scan_present()
        if not (self.base <= self.sel_track < self.base + NUM_COLS):
            self.select_track(self.base)
            self.refresh_selected()
        self.render()

    def fx_button(self, ch, note):
        if note in NOTE_TO_FX_ROW and ch < NUM_COLS:
            self.sel_track, self.sel_slot = self.track_of(ch), NOTE_TO_FX_ROW[note]
            self.select_track(self.sel_track)
            self.bank = 0
            self.refresh_selected()
            self.rearm_faders()
            self.hint("Track %d  Slot %d: %s" % (self.sel_track, self.sel_slot + 1, self.pname or "(empty)"))
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
        else:
            return
        self.render()

    def change_bank(self, delta):
        nb = max(0, min(self.max_bank(), self.bank + delta))
        if nb != self.bank:
            self.bank = nb
            self.rearm_faders()
            self.hint("%s: parameter page %d/%d" % (self.pname, self.bank + 1, self.max_bank() + 1))

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
        if self.mode != "fx":
            return
        self.cue_accum += delta
        while abs(self.cue_accum) >= CUE_TICKS_PER_BANK:
            step = 1 if self.cue_accum > 0 else -1
            self.cue_accum -= step * CUE_TICKS_PER_BANK
            self.change_bank(step)
        self.render()

    def knob(self, k, value, cc):                          # k 0-7 track knobs, 8-15 device knobs
        if self.mode == "fx":
            p = self.bank * BANK_SIZE + k
            if self.sel_present() and p < self.pcount:
                self.set_param(p, value / 127.0)
                self.cc_sent[cc] = value                   # the ring already shows the value the knob just sent
                try:
                    self.hint("%s  %s: %s" % (self.pname, plugins.getParamName(p, self.sel_track, self.sel_slot),
                                              plugins.getParamValueString(p, self.sel_track, self.sel_slot)))
                except Exception:                           # noqa: BLE001
                    pass
        elif k < 8:
            try:
                mixer.setTrackPan(self.track_of(k), value / 127.0 * 2.0 - 1.0)
            except Exception as e:                          # noqa: BLE001
                print("APC40: pan error:", e)
            self.cc_sent[cc] = value

    def fader(self, idx, pos):
        prev, self.fader_pos[idx] = self.fader_pos[idx], pos
        if idx == 8:                                        # master fader: always the Master track volume
            getter = lambda: self.safe(mixer.getTrackVolume, 0)
            setter = lambda v: mixer.setTrackVolume(0, v)
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
            redraw = self.mode == "fx"
        if now - self.t_scan >= SCAN_SECONDS:
            self.t_scan = now
            if self.scan_present():
                self.refresh_selected()
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
            if self.mode == "fx":
                self.sync_rings()
        if redraw:
            self.render()

    def init(self):
        if SEND_MODE_SYSEX:
            device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x73, 0x60, 0x00, 0x04, MODE_BYTE, 0x09, 0x00, 0x00, 0xF7]))
        self.scan_present()
        self.last_fl_track = self.safe(mixer.trackNumber)
        self.refresh_selected()
        self.render()
        print("APC40 Control v0.1 ready: mode=%s, tracks %d-%d" % (self.mode, self.base, self.base + NUM_COLS - 1))

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
