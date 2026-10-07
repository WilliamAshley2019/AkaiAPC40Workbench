#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include <juce_audio_devices/juce_audio_devices.h>
#include <BinaryData.h>
#include "ApcLayout.h"
#include "ApcSurface.h"

class MainComponent : public juce::Component,
                      private juce::MidiInputCallback,
                      private juce::Timer
{
public:
    MainComponent()
    {
        {
            auto dir = juce::File::getSpecialLocation (juce::File::userDocumentsDirectory).getChildFile ("APC40Workbench");
            dir.createDirectory();  logFile = dir.getChildFile ("workbench.log");  logFile.deleteFile();
        }
        loadInitialLayout();
        surface.setLayout (&layout);
        surface.onPress   = [this] (int i) { surfacePress (i); };
        surface.onRelease = [this] (int i) { surfaceRelease (i); };
        addAndMakeVisible (surface);

        setupLabel (inLabel, "MIDI In");   setupLabel (outLabel, "MIDI Out");  setupLabel (modeLabel, "Mode");
        for (auto* c : { &inCombo, &outCombo, &modeCombo }) addAndMakeVisible (*c);
        modeCombo.addItem ("Generic (0x40)", 1);  modeCombo.addItem ("Ableton (0x41)", 2);  modeCombo.addItem ("Alt Ableton (0x42)", 3);
        modeCombo.setSelectedId (3, juce::dontSendNotification);   // 0x42: all LEDs host-controlled, nothing banked
        inCombo.onChange  = [this] { openInput  (inCombo.getSelectedItemIndex()); };
        outCombo.onChange = [this] { openOutput (outCombo.getSelectedItemIndex()); };

        setupButton (rescanBtn,  "Rescan",           [this] { refreshDevices(); });
        setupButton (modeBtn,    "Send Mode SysEx",  [this] { sendModeSysex(); });
        setupButton (ledTestBtn, "LED Test",         [this] { ledStage = (ledStage + 1) % 3; applyLedStage(); });
        setupButton (ledOffBtn,  "All LEDs Off",     [this] { allLedsOff(); });
        setupButton (wizBtn,     "Start Learn",      [this] { startWizard(); });
        setupButton (backBtn,    "Back",             [this] { wizardBack(); });
        setupButton (skipBtn,    "Skip",             [this] { wizardSkip (false); });
        setupButton (skipGrpBtn, "Skip Group",       [this] { wizardSkip (true); });
        setupButton (stopBtn,    "Stop Learn",       [this] { stopWizard ("Learn stopped."); });
        setupButton (exportBtn,  "Export Map...",    [this] { exportMap(); });
        setupButton (loadBtn,    "Load Layout...",   [this] { loadLayoutFile(); });
        setupButton (resetBtn,   "Reset Learn",      [this] { resetLearn(); });
        setupButton (copyLogBtn, "Copy Log",         [this] { juce::SystemClipboard::copyTextToClipboard (logBox.getText()); log ("Log copied to clipboard."); });
        setupButton (copySumBtn, "Copy Summary",     [this] { juce::SystemClipboard::copyTextToClipboard (buildSummaryText()); log ("Summary copied to clipboard."); });
        setupButton (probeBtn,   "Send",             [this] { sendProbe(); });
        verboseToggle.setButtonText ("Verbose log (CC + note off)");
        verboseToggle.setColour (juce::ToggleButton::textColourId, juce::Colour (0xffb0b4bd));
        addAndMakeVisible (verboseToggle);
        setupLabel (probeLabel, "Probe:");
        probeType.addItem ("Note On", 1);  probeType.addItem ("Note Off", 2);  probeType.addItem ("CC", 3);
        probeType.setSelectedId (3, juce::dontSendNotification);  addAndMakeVisible (probeType);
        for (auto* e : { &probeCh, &probeNum, &probeVal }) { e->setInputRestrictions (3, "0123456789");  addAndMakeVisible (*e); }
        probeCh.setText ("1");  probeNum.setText ("56");  probeVal.setText ("2");   // CC 56 = track knob 1 ring type (2 = volume style)

        status.setFont (juce::FontOptions (16.0f));
        status.setColour (juce::Label::textColourId, juce::Colours::white);
        status.setText ("Select your APC40 MIDI ports, then click Start Learn (or press things to watch them light up).", juce::dontSendNotification);
        addAndMakeVisible (status);

        logBox.setMultiLine (true);  logBox.setReadOnly (true);  logBox.setScrollbarsShown (true);
        logBox.setFont (juce::FontOptions (juce::Font::getDefaultMonospacedFontName(), 12.0f, juce::Font::plain));
        logBox.setColour (juce::TextEditor::backgroundColourId, juce::Colour (0xff15161a));
        addAndMakeVisible (logBox);

        setSize (1320, 900);
        refreshDevices();
        startTimerHz (20);
        log ("APC40 Workbench ready. Layout: " + layout.name + " (" + juce::String ((int) layout.controls.size()) + " entries)");
    }

    ~MainComponent() override { stopTimer(); if (midiIn) midiIn->stop(); midiIn.reset(); midiOut.reset(); }

    void paint (juce::Graphics& g) override { g.fillAll (juce::Colour (0xff101114)); }

    void resized() override
    {
        auto a = getLocalBounds().reduced (8);
        auto row1 = a.removeFromTop (28);
        inLabel.setBounds (row1.removeFromLeft (52));    inCombo.setBounds (row1.removeFromLeft (230));   row1.removeFromLeft (8);
        outLabel.setBounds (row1.removeFromLeft (58));   outCombo.setBounds (row1.removeFromLeft (230));  row1.removeFromLeft (8);
        rescanBtn.setBounds (row1.removeFromLeft (70));  row1.removeFromLeft (24);
        modeLabel.setBounds (row1.removeFromLeft (44));  modeCombo.setBounds (row1.removeFromLeft (150)); row1.removeFromLeft (6);
        modeBtn.setBounds (row1.removeFromLeft (130));
        a.removeFromTop (6);
        auto row2 = a.removeFromTop (28);
        for (auto* b : { &ledTestBtn, &ledOffBtn, &wizBtn, &backBtn, &skipBtn, &skipGrpBtn, &stopBtn, &resetBtn, &exportBtn, &loadBtn, &copyLogBtn, &copySumBtn })
            b->setBounds (row2.removeFromLeft (104).reduced (2, 0));
        a.removeFromTop (6);
        auto row3 = a.removeFromTop (26);
        verboseToggle.setBounds (row3.removeFromLeft (220));  row3.removeFromLeft (20);
        probeLabel.setBounds (row3.removeFromLeft (52));      probeType.setBounds (row3.removeFromLeft (100));  row3.removeFromLeft (6);
        probeCh.setBounds (row3.removeFromLeft (44));  row3.removeFromLeft (4);
        probeNum.setBounds (row3.removeFromLeft (44)); row3.removeFromLeft (4);
        probeVal.setBounds (row3.removeFromLeft (44)); row3.removeFromLeft (6);
        probeBtn.setBounds (row3.removeFromLeft (70));
        a.removeFromTop (6);
        status.setBounds (a.removeFromTop (26));
        a.removeFromTop (4);
        logBox.setBounds (a.removeFromRight (330));
        a.removeFromRight (8);
        surface.setBounds (a);
    }

private:
    // ---------------------------------------------------------------- UI
    ApcSurface surface;
    juce::Label inLabel, outLabel, modeLabel, status;
    juce::ComboBox inCombo, outCombo, modeCombo;
    juce::TextButton rescanBtn, modeBtn, ledTestBtn, ledOffBtn, wizBtn, backBtn, skipBtn, skipGrpBtn, stopBtn, exportBtn, loadBtn,
                     resetBtn, copyLogBtn, copySumBtn, probeBtn;
    juce::ToggleButton verboseToggle;
    juce::ComboBox probeType;
    juce::TextEditor probeCh, probeNum, probeVal;
    juce::Label probeLabel;
    juce::File logFile;
    juce::TextEditor logBox;
    std::unique_ptr<juce::FileChooser> chooser;

    apc::Layout layout;
    juce::Array<juce::MidiDeviceInfo> inputs, outputs;
    std::unique_ptr<juce::MidiInput>  midiIn;
    std::unique_ptr<juce::MidiOutput> midiOut;

    int ledStage = 0, tick = 0;
    bool blinkOn = true;

    // wizard state
    bool wizardActive = false;
    std::vector<int> wizOrder;
    int wizPos = 0;
    apc::Msg ignoreType = apc::Msg::None;  int ignoreCh = 0, ignoreNum = 0;  juce::uint32 ignoreUntil = 0;

    void setupLabel (juce::Label& l, const juce::String& t)
    {
        l.setText (t, juce::dontSendNotification);  l.setColour (juce::Label::textColourId, juce::Colour (0xffb0b4bd));
        addAndMakeVisible (l);
    }
    void setupButton (juce::TextButton& b, const juce::String& t, std::function<void()> fn)
    {
        b.setButtonText (t);  b.onClick = std::move (fn);  addAndMakeVisible (b);
    }
    void log (const juce::String& s)
    {
        if (logBox.getTotalNumChars() > 150000) logBox.setText (logBox.getText().substring (75000), false);
        logBox.moveCaretToEnd();  logBox.insertTextAtCaret (s + "\n");
        logFile.appendText (s + "\n");   // full, untrimmed copy: Documents/APC40Workbench/workbench.log
    }

    // ---------------------------------------------------------------- layout
    void loadInitialLayout()
    {
        juce::String err;
        auto external = juce::File::getSpecialLocation (juce::File::currentExecutableFile).getSiblingFile ("apc40_layout.json");
        if (external.existsAsFile() && layout.loadFromJson (external.loadFileAsString(), err)) return;
        if (! layout.loadFromJson (juce::String::fromUTF8 (BinaryData::apc40_layout_json, BinaryData::apc40_layout_jsonSize), err))
            juce::Logger::writeToLog ("Embedded layout failed: " + err);
    }
    void loadLayoutFile()
    {
        chooser = std::make_unique<juce::FileChooser> ("Load layout JSON", juce::File(), "*.json");
        chooser->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
            [this] (const juce::FileChooser& fc)
            {
                auto f = fc.getResult();
                if (f == juce::File()) return;
                juce::String err;
                if (layout.loadFromJson (f.loadFileAsString(), err)) { stopWizard ("Layout reloaded."); log ("Loaded " + f.getFileName()); }
                else log ("Layout error: " + err);
                surface.repaint();
            });
    }

    // ---------------------------------------------------------------- MIDI devices
    void refreshDevices()
    {
        inputs = juce::MidiInput::getAvailableDevices();
        outputs = juce::MidiOutput::getAvailableDevices();
        inCombo.clear (juce::dontSendNotification);  outCombo.clear (juce::dontSendNotification);
        int apcIn = -1, apcOut = -1;
        for (int i = 0; i < inputs.size(); ++i)  { inCombo.addItem (inputs[i].name, i + 1);  if (apcIn < 0 && inputs[i].name.containsIgnoreCase ("APC40")) apcIn = i; }
        for (int i = 0; i < outputs.size(); ++i) { outCombo.addItem (outputs[i].name, i + 1); if (apcOut < 0 && outputs[i].name.containsIgnoreCase ("APC40")) apcOut = i; }
        if (apcIn >= 0)  inCombo.setSelectedItemIndex (apcIn, juce::sendNotification);
        if (apcOut >= 0) outCombo.setSelectedItemIndex (apcOut, juce::sendNotification);
        log ("Found " + juce::String (inputs.size()) + " MIDI in / " + juce::String (outputs.size()) + " MIDI out");
    }
    void openInput (int index)
    {
        if (midiIn) { midiIn->stop(); midiIn.reset(); }
        if (index < 0 || index >= inputs.size()) return;
        midiIn = juce::MidiInput::openDevice (inputs[index].identifier, this);
        if (midiIn) { midiIn->start(); log ("MIDI in: " + inputs[index].name); }
        else log ("Could not open MIDI in. Is FL Studio (or another app) holding the port?");
    }
    void openOutput (int index)
    {
        midiOut.reset();
        if (index < 0 || index >= outputs.size()) return;
        midiOut = juce::MidiOutput::openDevice (outputs[index].identifier);
        if (midiOut) log ("MIDI out: " + outputs[index].name);
        else log ("Could not open MIDI out. Is FL Studio (or another app) holding the port?");
    }
    void handleIncomingMidiMessage (juce::MidiInput*, const juce::MidiMessage& m) override
    {
        juce::MessageManager::callAsync ([safe = juce::Component::SafePointer<MainComponent> (this), m]
                                         { if (safe != nullptr) safe->processMidi (m); });
    }

    // ---------------------------------------------------------------- output
    void sendNoteLed (int ch, int note, int vel)
    {
        if (midiOut) midiOut->sendMessageNow (juce::MidiMessage::noteOn (ch, note, (juce::uint8) vel));
    }
    void sendModeSysex()
    {
        if (! midiOut) { log ("No MIDI out selected."); return; }
        const juce::uint8 modes[] = { 0x40, 0x41, 0x42 };
        const juce::uint8 mode = modes[juce::jlimit (0, 2, modeCombo.getSelectedId() - 1)];
        // F0 47 7F 73 60 00 04 <mode> <ver maj> <ver min> <bugfix> F7   (version bytes are a best guess)
        const juce::uint8 data[] = { 0x47, 0x7F, 0x73, 0x60, 0x00, 0x04, mode, 0x09, 0x00, 0x00 };
        midiOut->sendMessageNow (juce::MidiMessage::createSysExMessage (data, (int) sizeof (data)));
        log ("Sent mode SysEx, mode byte 0x" + juce::String::toHexString (mode));
    }
    void applyLedStage()
    {
        int k = 0;
        for (auto& c : layout.controls)
        {
            if (c.kind != apc::Kind::Pad || c.msg != apc::Msg::Note) continue;
            c.ledState = ledStage == 0 ? 0 : (ledStage == 1 ? 1 + 2 * (k % 3) : 2 + 2 * (k % 3));
            sendNoteLed (c.ch, c.num, c.ledState);
            ++k;
        }
        log (ledStage == 0 ? "LED test: pads off" : ledStage == 1 ? "LED test: solid colours" : "LED test: blinking colours");
        surface.repaint();
    }
    void allLedsOff()
    {
        for (auto& c : layout.controls)
            if (c.msg == apc::Msg::Note && c.led) { c.ledState = 0; sendNoteLed (c.ch, c.num, 0); }
        ledStage = 0;  surface.repaint();
    }

    // ---------------------------------------------------------------- surface clicks (LED test per button)
    void surfacePress (int i)
    {
        auto& c = layout.controls[(size_t) i];
        if (c.msg == apc::Msg::Note && c.led)
        {
            c.ledState = (c.ledState + 1) % 7;
            sendNoteLed (c.ch, c.num, c.ledState);
            log ("LED " + c.id + " -> state " + juce::String (c.ledState));
        }
        surface.repaint();
    }
    void surfaceRelease (int) { surface.repaint(); }

    // ---------------------------------------------------------------- incoming MIDI
    void processMidi (const juce::MidiMessage& m)
    {
        if (m.isSysEx()) { log ("SYSEX (" + juce::String (m.getRawDataSize()) + " bytes)"); return; }

        if (m.isNoteOnOrOff())
        {
            const bool on = m.isNoteOn();
            const int ch = m.getChannel(), num = m.getNoteNumber();
            if (on || verboseToggle.getToggleState())
                log (juce::String (on ? "NOTE ON  " : "NOTE OFF ") + "ch" + juce::String (ch) + " #" + juce::String (num) + " v" + juce::String ((int) m.getVelocity()));
            const int i = layout.find (apc::Msg::Note, ch, num);
            if (i >= 0) { auto& c = layout.controls[(size_t) i]; c.pressed = on; if (on) c.value = m.getVelocity(); }
            if (on) learn (apc::Msg::Note, ch, num);
        }
        else if (m.isController())
        {
            const int ch = m.getChannel(), num = m.getControllerNumber(), val = m.getControllerValue();
            if (verboseToggle.getToggleState())
                log ("CC       ch" + juce::String (ch) + " #" + juce::String (num) + " = " + juce::String (val));
            const int i = layout.find (apc::Msg::CC, ch, num);
            if (i >= 0) { auto& c = layout.controls[(size_t) i]; c.value = val; c.minSeen = juce::jmin (c.minSeen, val); c.maxSeen = juce::jmax (c.maxSeen, val); }
            learn (apc::Msg::CC, ch, num);
        }
        else log ("MIDI " + m.getDescription());
        surface.repaint();
    }

    // ---------------------------------------------------------------- Learn wizard
    void startWizard()
    {
        if (! midiIn) { log ("Select the APC40 MIDI input first."); return; }
        wizOrder.clear();
        for (size_t i = 0; i < layout.controls.size(); ++i)
        {
            auto& c = layout.controls[i];
            if (c.kind == apc::Kind::Text || c.kind == apc::Kind::Panel || c.expMsg == apc::Msg::None) continue;
            if (c.learned) continue;   // resume: keep what was already learned
            c.msg = c.expMsg;  c.ch = c.expCh;  c.num = c.expNum;  c.learned = false;  c.mismatch = false;
            wizOrder.push_back ((int) i);
        }
        if (wizOrder.empty()) { log ("Everything is already learned. Use Reset Learn to start over, or Export Map / Copy Summary."); return; }
        wizPos = 0;  wizardActive = true;  ignoreUntil = 0;
        log ("Learn started/resumed: " + juce::String ((int) wizOrder.size()) + " controls left.");
        updateWizardStatus();
    }
    void stopWizard (const juce::String& msg)
    {
        wizardActive = false;  surface.setTarget (-1);
        int learned = 0, diffs = 0;
        for (auto& c : layout.controls) { if (c.learned) ++learned; if (c.learned && c.mismatch) ++diffs; }
        status.setText (msg + "  Learned " + juce::String (learned) + ", differing from reference: " + juce::String (diffs) + ".", juce::dontSendNotification);
        log (status.getText());
        if (msg.startsWith ("Learn finished")) autoSaveMap();
    }
    void updateWizardStatus()
    {
        if (wizPos >= (int) wizOrder.size()) { stopWizard ("Learn finished!"); return; }
        const int idx = wizOrder[(size_t) wizPos];
        const auto& c = layout.controls[(size_t) idx];
        surface.setTarget (idx);
        status.setText ("[" + juce::String (wizPos + 1) + "/" + juce::String ((int) wizOrder.size()) + "]  Press / move:  "
                        + c.desc + "     (reference: " + c.expectedText() + ")", juce::dontSendNotification);
    }
    void learn (apc::Msg type, int ch, int num)
    {
        if (! wizardActive || wizPos >= (int) wizOrder.size()) return;
        const auto now = juce::Time::getMillisecondCounter();
        if (type == ignoreType && ch == ignoreCh && num == ignoreNum && now < ignoreUntil) { ignoreUntil = now + 450; return; }

        const int idx = wizOrder[(size_t) wizPos];
        const int other = layout.find (type, ch, num);
        if (other >= 0 && other != idx && layout.controls[(size_t) other].learned)
        {
            log ("Ignored: that address already belongs to '" + layout.controls[(size_t) other].id + "' - wrong control?");
            return;
        }
        auto& c = layout.controls[(size_t) idx];
        c.msg = type;  c.ch = ch;  c.num = num;  c.learned = true;
        c.mismatch = (type != c.expMsg || ch != c.expCh || num != c.expNum);
        log (juce::String (c.mismatch ? "DIFFERS " : "OK      ") + c.id + " = " + c.addressText()
             + (c.mismatch ? "   (reference " + c.expectedText() + ")" : juce::String()));
        ignoreType = type;  ignoreCh = ch;  ignoreNum = num;  ignoreUntil = now + 450;
        ++wizPos;  updateWizardStatus();
    }
    void wizardBack()
    {
        if (! wizardActive || wizPos == 0) return;
        --wizPos;
        auto& c = layout.controls[(size_t) wizOrder[(size_t) wizPos]];
        c.msg = c.expMsg;  c.ch = c.expCh;  c.num = c.expNum;  c.learned = false;  c.mismatch = false;
        ignoreUntil = 0;  updateWizardStatus();  surface.repaint();
    }
    void wizardSkip (bool wholeGroup)
    {
        if (! wizardActive || wizPos >= (int) wizOrder.size()) return;
        const auto grp = layout.controls[(size_t) wizOrder[(size_t) wizPos]].group;
        do { ++wizPos; }
        while (wholeGroup && wizPos < (int) wizOrder.size() && layout.controls[(size_t) wizOrder[(size_t) wizPos]].group == grp);
        updateWizardStatus();
    }

    // ---------------------------------------------------------------- extras
    void resetLearn()
    {
        wizardActive = false;  surface.setTarget (-1);
        for (auto& c : layout.controls)
        { c.msg = c.expMsg;  c.ch = c.expCh;  c.num = c.expNum;  c.learned = false;  c.mismatch = false;  c.minSeen = 128;  c.maxSeen = -1; }
        status.setText ("Learn reset. Click Start Learn.", juce::dontSendNotification);
        log ("Learn reset.");  surface.repaint();
    }
    void autoSaveMap()
    {
        auto f = logFile.getParentDirectory().getChildFile ("apc40_map.json");
        if (f.replaceWithText (buildMapJson())) log ("Auto-saved map: " + f.getFullPathName());
    }
    juce::String buildSummaryText() const
    {
        juce::String body;  int ok = 0, diff = 0, un = 0;
        for (auto& c : layout.controls)
        {
            if (! c.hasMidi()) continue;
            if (! c.learned) ++un;  else if (c.mismatch) ++diff;  else ++ok;
            body << c.id << " | " << c.addressText() << " | "
                 << (! c.learned ? juce::String ("unlearned") : c.mismatch ? "DIFFERS (ref " + c.expectedText() + ")" : juce::String ("ok"));
            if (c.msg == apc::Msg::CC && c.maxSeen >= c.minSeen) body << " | seen " << c.minSeen << ".." << c.maxSeen;
            body << "\n";
        }
        return "APC40 summary: " + juce::String (ok) + " ok, " + juce::String (diff) + " differ, " + juce::String (un) + " unlearned\n" + body;
    }
    void sendProbe()
    {
        if (! midiOut) { log ("No MIDI out selected."); return; }
        const int ch  = juce::jlimit (1, 16, probeCh.getText().getIntValue());
        const int num = juce::jlimit (0, 127, probeNum.getText().getIntValue());
        const int val = juce::jlimit (0, 127, probeVal.getText().getIntValue());
        const int t = probeType.getSelectedId();
        midiOut->sendMessageNow (t == 1 ? juce::MidiMessage::noteOn  (ch, num, (juce::uint8) val)
                               : t == 2 ? juce::MidiMessage::noteOff (ch, num, (juce::uint8) val)
                                        : juce::MidiMessage::controllerEvent (ch, num, val));
        log ("Probe sent: " + probeType.getText() + " ch" + juce::String (ch) + " #" + juce::String (num) + " v" + juce::String (val));
    }

    // ---------------------------------------------------------------- export
    juce::String buildMapJson() const
    {
        auto* root = new juce::DynamicObject();
        root->setProperty ("device", "Akai APC40 MkI");
        root->setProperty ("generator", "APC40 Workbench 0.1");
        juce::Array<juce::var> arr;
        for (auto& c : layout.controls)
        {
            if (! c.hasMidi()) continue;
            auto* o = new juce::DynamicObject();
            o->setProperty ("id", c.id);  o->setProperty ("group", c.group);
            o->setProperty ("type", apc::toString (c.msg));  o->setProperty ("channel", c.ch);  o->setProperty ("number", c.num);
            o->setProperty ("learned", c.learned);  o->setProperty ("matches_reference", ! c.mismatch);
            if (c.msg == apc::Msg::CC && c.maxSeen >= c.minSeen) { o->setProperty ("min_seen", c.minSeen);  o->setProperty ("max_seen", c.maxSeen); }
            if (c.mismatch)
            {
                o->setProperty ("reference_type", apc::toString (c.expMsg));
                o->setProperty ("reference_channel", c.expCh);  o->setProperty ("reference_number", c.expNum);
            }
            arr.add (juce::var (o));
        }
        root->setProperty ("controls", arr);
        return juce::JSON::toString (juce::var (root), false);
    }
    void exportMap()
    {
        chooser = std::make_unique<juce::FileChooser> ("Save learned map",
            juce::File::getSpecialLocation (juce::File::userDocumentsDirectory).getChildFile ("apc40_map.json"), "*.json");
        chooser->launchAsync (juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::canSelectFiles
                              | juce::FileBrowserComponent::warnAboutOverwriting,
            [this] (const juce::FileChooser& fc)
            {
                auto f = fc.getResult();
                if (f == juce::File()) return;
                if (f.replaceWithText (buildMapJson())) log ("Saved " + f.getFullPathName());
                else log ("Could not write " + f.getFullPathName());
            });
    }

    // ---------------------------------------------------------------- animation
    void timerCallback() override
    {
        ++tick;
        blinkOn = ((tick / 10) % 2) == 0;
        surface.setAnimation (blinkOn, (float) tick * 0.45f);
        surface.repaint();
    }

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (MainComponent)
};
