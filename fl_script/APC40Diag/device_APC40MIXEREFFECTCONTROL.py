# name=APC40 FX Workbench

import device
import mixer
import plugins
import general
import midi


# ============================================================
# APC40 FX WORKBENCH
# ============================================================
#
# APC40 Mk I
#
# 8 APC columns  = FL Mixer tracks 1-8
# 10 APC FX rows = FL FX slots 1-10
#
# Rows:
#   0-4 = Clip Launch 1-5
#   5   = Clip Stop
#   6   = Track Activator
#   7   = Solo / Cue
#   8   = Record / Arm
#   9   = Track Select
#
# FX rows 0-9 correspond directly to FL slots 0-9.
#
# FL track 0 is Master, so APC column 0 starts at FL track 1.
#
# ============================================================


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

NUM_TRACKS = 8
NUM_FX_SLOTS = 10

FIRST_FL_TRACK = 1

# Parameter controls
NUM_KNOBS = 16
NUM_FADERS = 8

# APC40 Mk I
DEVICE_KNOBS = [16, 17, 18, 19, 20, 21, 22, 23]
TRACK_KNOBS  = [48, 49, 50, 51, 52, 53, 54, 55]

# Channel faders:
# CC 7, MIDI channels 0-7
FADER_CC = 7

# Master fader
MASTER_FADER_CC = 14
MASTER_FADER_CHANNEL = 0

# APC40 MIDI channels are zero based in FL scripting.
#
# Column 0 = MIDI channel 0
# Column 7 = MIDI channel 7


# ------------------------------------------------------------
# APC40 button notes
# ------------------------------------------------------------

# Standard APC40 Mk I communication protocol.
#
# The channel selects the track.
#
# Clip launch rows:
#
# 0x35 = Clip Launch 1
# 0x36 = Clip Launch 2
# 0x37 = Clip Launch 3
# 0x38 = Clip Launch 4
# 0x39 = Clip Launch 5
#
# Then:
#
# 0x34 = Clip Stop
# 0x32 = Activator
# 0x31 = Solo
# 0x30 = Record Arm
# 0x33 = Track Select


ROW_NOTES = [
    0x35,       # FX slot 1
    0x36,       # FX slot 2
    0x37,       # FX slot 3
    0x38,       # FX slot 4
    0x39,       # FX slot 5
    0x34,       # FX slot 6
    0x32,       # FX slot 7
    0x31,       # FX slot 8
    0x30,       # FX slot 9
    0x33,       # FX slot 10 / Track Select
]


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

selected_track = FIRST_FL_TRACK
selected_slot = 0

# Which parameter bank is displayed on the 16 knobs/faders.
#
# Bank 0:
#   knobs  = parameters 0-15
#   faders = parameters 16-23
#
# Bank 1:
#   knobs  = parameters 24-39
#   faders = parameters 40-47
#
# etc.

parameter_bank = 0

# Cache of the currently selected plugin
cached_plugin_name = ""
cached_parameter_count = 0


# ------------------------------------------------------------
# MIDI output helpers
# ------------------------------------------------------------

def send_note(channel, note, velocity):
    """
    Send MIDI Note On.
    """
    device.midiOutMsg(
        midi.NOTEON |
        (channel & 0x0F),
        note & 0x7F,
        velocity & 0x7F
    )


def send_cc(channel, cc, value):
    """
    Send MIDI CC.
    """
    device.midiOutMsg(
        midi.CONTROLCHANGE |
        (channel & 0x0F),
        cc & 0x7F,
        value & 0x7F
    )


# ------------------------------------------------------------
# FX helpers
# ------------------------------------------------------------

def fl_track(column):
    """
    Convert APC column 0-7 into FL Mixer track.

    APC column 0 -> FL track 1
    APC column 7 -> FL track 8

    FL track 0 is Master.
    """
    return FIRST_FL_TRACK + column


def slot_valid(track, slot):
    """
    True if an FX plugin exists in this slot.
    """
    try:
        return bool(
            mixer.isTrackPluginValid(track, slot)
        )
    except:
        return bool(
            plugins.isValid(track, slot)
        )


def plugin_name(track, slot):
    """
    Return plugin name.
    """
    if not slot_valid(track, slot):
        return ""

    try:
        return plugins.getPluginName(
            track,
            slot,
            1
        )
    except:
        return "Unknown"


def parameter_count(track, slot):
    """
    Return number of exposed plugin parameters.
    """
    if not slot_valid(track, slot):
        return 0

    try:
        return plugins.getParamCount(
            track,
            slot
        )
    except:
        return 0


def parameter_name(track, slot, param):
    """
    Return parameter name.
    """
    try:
        return plugins.getParamName(
            param,
            track,
            slot
        )
    except:
        return ""


def parameter_value(track, slot, param):
    """
    Return normalized parameter value 0.0-1.0.
    """
    try:
        return float(
            plugins.getParamValue(
                param,
                track,
                slot
            )
        )
    except:
        return 0.0


def set_parameter(track, slot, param, value):
    """
    Set normalized plugin parameter.
    """
    if not slot_valid(track, slot):
        return

    try:
        plugins.setParamValue(
            float(value),
            param,
            track,
            slot
        )
    except Exception as e:
        print(
            "APC40 FX: parameter write error:",
            e
        )


# ------------------------------------------------------------
# Selected plugin
# ------------------------------------------------------------

def update_selected_plugin():
    global cached_plugin_name
    global cached_parameter_count

    cached_plugin_name = plugin_name(
        selected_track,
        selected_slot
    )

    cached_parameter_count = parameter_count(
        selected_track,
        selected_slot
    )

    print("")
    print("======================================")
    print("APC40 FX")
    print("Track:", selected_track)
    print("Slot:", selected_slot + 1)
    print("Plugin:", cached_plugin_name)
    print("Parameters:", cached_parameter_count)
    print("Parameter bank:", parameter_bank)
    print("======================================")


def dump_selected_plugin():
    """
    Print every exposed parameter of the selected plugin.
    Extremely useful for learning how a plugin exposes
    its controls to FL Studio.
    """

    if not slot_valid(selected_track, selected_slot):
        print("APC40 FX: no plugin selected.")
        return

    count = parameter_count(
        selected_track,
        selected_slot
    )

    print("")
    print("PLUGIN:", plugin_name(
        selected_track,
        selected_slot
    ))

    print("TRACK:", selected_track)
    print("SLOT:", selected_slot + 1)
    print("PARAMETERS:", count)

    for p in range(count):
        name = parameter_name(
            selected_track,
            selected_slot,
            p
        )

        value = parameter_value(
            selected_track,
            selected_slot,
            p
        )

        print(
            "%03d  %-40s %.4f" %
            (p, name, value)
        )


# ------------------------------------------------------------
# FX slot selection
# ------------------------------------------------------------

def select_fx_slot(column, row):
    """
    APC column -> FL track
    APC row    -> FL FX slot
    """

    global selected_track
    global selected_slot

    if column < 0 or column >= NUM_TRACKS:
        return

    if row < 0 or row >= NUM_FX_SLOTS:
        return

    selected_track = fl_track(column)
    selected_slot = row

    # Make FL Mixer follow the APC40 selection.
    mixer.setTrackNumber(selected_track)

    update_selected_plugin()

    update_all_leds()


# ------------------------------------------------------------
# Parameter mapping
# ------------------------------------------------------------

def knob_parameter(index):
    """
    Map knob 0-15 to plugin parameter.
    """

    return (
        parameter_bank * 24
    ) + index


def fader_parameter(index):
    """
    Map fader 0-7 to plugin parameter.
    """

    return (
        parameter_bank * 24
    ) + NUM_KNOBS + index


# ------------------------------------------------------------
# Knob handling
# ------------------------------------------------------------

def handle_device_knob(index, value):
    """
    APC Device Knobs 1-8.
    """

    if not slot_valid(
        selected_track,
        selected_slot
    ):
        return

    param = knob_parameter(index)

    if param >= cached_parameter_count:
        return

    set_parameter(
        selected_track,
        selected_slot,
        param,
        value / 127.0
    )


def handle_track_knob(index, value):
    """
    APC Track Control knobs.

    In FX mode these become parameters 9-16
    of the selected plugin.
    """

    if not slot_valid(
        selected_track,
        selected_slot
    ):
        return

    param = knob_parameter(
        8 + index
    )

    if param >= cached_parameter_count:
        return

    set_parameter(
        selected_track,
        selected_slot,
        param,
        value / 127.0
    )


# ------------------------------------------------------------
# Faders
# ------------------------------------------------------------

def handle_fader(channel, value):
    """
    APC channel faders become plugin parameters
    17-24 of the selected plugin.
    """

    if channel < 0 or channel >= NUM_FADERS:
        return

    if not slot_valid(
        selected_track,
        selected_slot
    ):
        return

    param = fader_parameter(channel)

    if param >= cached_parameter_count:
        return

    set_parameter(
        selected_track,
        selected_slot,
        param,
        value / 127.0
    )


def handle_master_fader(value):
    """
    Master fader controls the selected FX slot's
    FL Mixer effect mix level.

    Note:
    FL recommends normally leaving this at 100%
    and using the plugin's own wet/dry control.
    """

    if not slot_valid(
        selected_track,
        selected_slot
    ):
        return

    try:
        mixer.setPluginMixLevel(
            selected_track,
            selected_slot,
            value / 127.0
        )
    except Exception as e:
        print(
            "APC40 FX: mix level error:",
            e
        )


# ------------------------------------------------------------
# LED system
# ------------------------------------------------------------

def fx_led_state(track, slot):
    """
    Determine LED color for an FX slot.

    APC40 Mk I clip-launch LED values:

        0 = off
        1 = green
        2 = green blink
        3 = red
        4 = red blink
        5 = yellow
        6 = yellow blink
    """

    if not slot_valid(track, slot):
        return 0

    if (
        track == selected_track
        and slot == selected_slot
    ):
        return 5       # yellow

    return 1           # green


def update_fx_matrix_leds():
    """
    Update all 80 FX buttons.
    """

    for column in range(NUM_TRACKS):

        track = fl_track(column)

        for row in range(NUM_FX_SLOTS):

            note = ROW_NOTES[row]

            velocity = fx_led_state(
                track,
                row
            )

            send_note(
                column,
                note,
                velocity
            )


def update_track_select_leds():
    """
    Track Select row.

    Selected FL track = yellow.
    Other tracks = off.
    """

    for column in range(NUM_TRACKS):

        velocity = 5 if (
            fl_track(column)
            == selected_track
        ) else 0

        send_note(
            column,
            0x33,
            velocity
        )


def update_all_leds():
    """
    Refresh the APC40 FX interface.
    """

    update_fx_matrix_leds()
    update_track_select_leds()


# ------------------------------------------------------------
# Parameter feedback
# ------------------------------------------------------------

def update_parameter_leds():
    """
    Send current plugin parameter values back
    to the APC40 knob LED rings and faders.

    This allows the hardware to follow the plugin.
    """

    if not slot_valid(
        selected_track,
        selected_slot
    ):
        return

    count = cached_parameter_count

    # Device knobs
    for i in range(8):

        param = knob_parameter(i)

        if param < count:

            value = int(
                parameter_value(
                    selected_track,
                    selected_slot,
                    param
                ) * 127
            )

            send_cc(
                0,
                DEVICE_KNOBS[i],
                value
            )

    # Track-control knobs
    for i in range(8):

        param = knob_parameter(8 + i)

        if param < count:

            value = int(
                parameter_value(
                    selected_track,
                    selected_slot,
                    param
                ) * 127
            )

            send_cc(
                0,
                TRACK_KNOBS[i],
                value
            )

    # Faders
    for i in range(8):

        param = fader_parameter(i)

        if param < count:

            value = int(
                parameter_value(
                    selected_track,
                    selected_slot,
                    param
                ) * 127
            )

            send_cc(
                i,
                FADER_CC,
                value
            )

    # Master fader = FX mix
    try:

        mix = mixer.getPluginMixLevel(
            selected_track,
            selected_slot
        )

        send_cc(
            MASTER_FADER_CHANNEL,
            MASTER_FADER_CC,
            int(mix * 127)
        )

    except:
        pass


# ------------------------------------------------------------
# MIDI input
# ------------------------------------------------------------

def OnMidiMsg(event):

    global parameter_bank

    status = event.status & 0xF0
    channel = event.status & 0x0F

    data1 = event.data1
    data2 = event.data2


    # --------------------------------------------------------
    # NOTE messages
    # --------------------------------------------------------

    if status == midi.NOTEON:

        # Ignore velocity-zero note-ons.
        if data2 == 0:
            return

        # FX matrix
        #
        # The row note determines the FX slot.
        # The MIDI channel determines the mixer track.
        #

        for row in range(NUM_FX_SLOTS):

            if data1 == ROW_NOTES[row]:

                # Track select row gets special behavior.
                if row == 9:

                    selected_track = fl_track(channel)

                    mixer.setTrackNumber(
                        selected_track
                    )

                    update_selected_plugin()
                    update_all_leds()
                    update_parameter_leds()

                    event.handled = True
                    return

                # All other rows select an FX slot.
                select_fx_slot(
                    channel,
                    row
                )

                update_parameter_leds()

                event.handled = True
                return


    # --------------------------------------------------------
    # CC messages
    # --------------------------------------------------------

    if status == midi.CONTROLCHANGE:

        # Device knobs
        if data1 in DEVICE_KNOBS:

            index = DEVICE_KNOBS.index(data1)

            handle_device_knob(
                index,
                data2
            )

            event.handled = True
            return


        # Track-control knobs
        if data1 in TRACK_KNOBS:

            index = TRACK_KNOBS.index(data1)

            handle_track_knob(
                index,
                data2
            )

            event.handled = True
            return


        # Channel faders
        if data1 == FADER_CC:

            handle_fader(
                channel,
                data2
            )

            event.handled = True
            return


        # Master fader
        if (
            data1 == MASTER_FADER_CC
            and channel == MASTER_FADER_CHANNEL
        ):

            handle_master_fader(
                data2
            )

            event.handled = True
            return


# ------------------------------------------------------------
# FL Studio refresh callback
# ------------------------------------------------------------

def OnRefresh(flags):

    # Mixer selection or controls changed.
    #
    # Re-read selected plugin when FL tells the
    # script that mixer state changed.

    try:

        current = mixer.trackNumber

        if current != selected_track:

            # Only follow FL selection if it is
            # one of our eight APC tracks.

            if (
                current >= FIRST_FL_TRACK
                and current < FIRST_FL_TRACK + NUM_TRACKS
            ):

                global selected_track

                selected_track = current

                update_selected_plugin()
                update_all_leds()

    except:
        pass


    # Keep plugin parameter hardware feedback current.
    update_parameter_leds()


# ------------------------------------------------------------
# Initialization
# ------------------------------------------------------------

def OnInit():

    global selected_track
    global selected_slot

    selected_track = FIRST_FL_TRACK
    selected_slot = 0

    print("")
    print("======================================")
    print(" APC40 FX WORKBENCH")
    print("======================================")
    print("Tracks :", NUM_TRACKS)
    print("FX slots:", NUM_FX_SLOTS)
    print("APC columns -> FL tracks 1-8")
    print("APC rows    -> FL FX slots 1-10")
    print("======================================")

    # Tell FL to use the selected mixer track.
    mixer.setTrackNumber(
        selected_track
    )

    update_selected_plugin()

    # Initial LED state
    update_all_leds()

    # Initial parameter state
    update_parameter_leds()


# ------------------------------------------------------------
# Deinitialization
# ------------------------------------------------------------

def OnDeInit():

    print("APC40 FX Workbench shutting down.")

    # Turn all matrix LEDs off.
    for channel in range(NUM_TRACKS):

        for row in range(NUM_FX_SLOTS):

            send_note(
                channel,
                ROW_NOTES[row],
                0
            )

    # Turn parameter controls off/zero.
    for cc in DEVICE_KNOBS:
        send_cc(0, cc, 0)

    for cc in TRACK_KNOBS:
        send_cc(0, cc, 0)

    for channel in range(NUM_FADERS):
        send_cc(
            channel,
            FADER_CC,
            0
        )

    send_cc(
        MASTER_FADER_CHANNEL,
        MASTER_FADER_CC,
        0
    )