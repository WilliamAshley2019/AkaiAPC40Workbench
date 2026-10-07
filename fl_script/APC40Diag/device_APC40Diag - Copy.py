# name=APC40 MkI Diagnostic (Stage 0)
# supportedDevices=APC40
#EXPERIMENTAL
# Stage 0: proves the FL Studio <-> APC40 MkI link before any real features are built.
#   * prints FL's scripting API version and the port number (Script output window)
#   * sends the "Generic mode" introduction SysEx
#   * prints every incoming MIDI message
#   * pressing any clip pad / button cycles its LED through states 0..6 (echo test)
#   * swallows the messages so FL doesn't play notes from the pads
#
# Install:  Documents\Image-Line\FL Studio\Settings\Hardware\APC40Diag\device_APC40Diag.py
# Then:     Options > MIDI settings > Input: APC40, Controller type: "APC40 MkI Diagnostic (Stage 0)",
#           and set the SAME port number on the matching Output device. Enable both. Close the Workbench first.

import device
import general

MODE_BYTE = 0x42            # per Akai's protocol doc: 0x40 generic (banked, LEDs partly automatic), 0x41 Ableton, 0x42 alt Ableton
                            # (all buttons momentary, nothing banked, ALL LEDs host-controlled) <- best for a custom script
SYSEX_INTRO = bytes([0xF0, 0x47, 0x7F, 0x73, 0x60, 0x00, 0x04, MODE_BYTE, 0x09, 0x00, 0x00, 0xF7])

led_state = {}              # (channel, note) -> 0..6


def send_note(channel, note, velocity):
    # packed message: status | data1 << 8 | data2 << 16  (status carries the channel in its low nibble)
    device.midiOutMsg(0x90 | (channel & 0x0F) | (note << 8) | (velocity << 16))


def send_cc(channel, cc, value):
    device.midiOutMsg(0xB0 | (channel & 0x0F) | (cc << 8) | (value << 16))


def OnInit():
    print("APC40 diag: FL scripting API version", general.getVersion())
    print("APC40 diag: port number", device.getPortNumber())
    device.midiOutSysex(SYSEX_INTRO)
    print("APC40 diag: sent mode SysEx (mode byte 0x%02X)" % MODE_BYTE)
    for i in range(8):                       # knob LED ring types: 0 off, 1 single, 2 volume style, 3 pan style
        send_cc(0, 0x38 + i, 2)              # track-control rings (CC 56..63): volume style
        send_cc(0, 0x18 + i, 3)              # device-control rings (CC 24..31): pan style
    print("APC40 diag: ring types set; turn a knob and its ring should follow (echo test)")


def OnDeInit():
    # clear the clip grid LEDs (channel nibble = column 0..7, notes 53..57 = rows)
    for ch in range(8):
        for note in range(53, 58):
            send_note(ch, note, 0)
    print("APC40 diag: closed")


def OnMidiMsg(event):
    kind = event.status & 0xF0
    print("MIDI  status=0x%02X ch=%d data1=%d data2=%d" % (event.status, (event.status & 0x0F) + 1, event.data1, event.data2))
    if kind == 0x90 and event.data2 > 0:                      # any Note On: cycle that button's LED
        key = (event.status & 0x0F, event.data1)
        led_state[key] = (led_state.get(key, 0) + 1) % 7
        send_note(key[0], key[1], led_state[key])
        print("      LED ch=%d note=%d -> state %d" % (key[0] + 1, key[1], led_state[key]))
    if kind == 0xB0 and (event.status & 0x0F) == 0 and (48 <= event.data1 <= 55 or 16 <= event.data1 <= 23):
        send_cc(0, event.data1, event.data2)                  # writing a knob's CC back updates its LED ring position
    event.handled = True                                      # keep FL from playing notes / mapping the CCs


def OnUpdateBeatIndicator(value):
    # 0 = off, 1 = bar, 2 = beat. Will drive the playhead LEDs in later stages.
    print("beat indicator:", value)
