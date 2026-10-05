#pragma once
#include <juce_core/juce_core.h>
#include <juce_graphics/juce_graphics.h>
#include <vector>

namespace apc
{
enum class Kind { Pad, Button, Knob, Fader, HFader, Text, Panel };
enum class Msg  { None, Note, CC };

inline Kind kindFromString (const juce::String& s)
{
    if (s == "pad") return Kind::Pad;
    if (s == "knob") return Kind::Knob;
    if (s == "fader") return Kind::Fader;
    if (s == "hfader") return Kind::HFader;
    if (s == "text") return Kind::Text;
    if (s == "panel") return Kind::Panel;
    return Kind::Button;
}
inline Msg msgFromString (const juce::String& s)
{
    if (s == "note") return Msg::Note;
    if (s == "cc") return Msg::CC;
    return Msg::None;
}
inline juce::String toString (Msg m) { return m == Msg::Note ? "note" : m == Msg::CC ? "cc" : "none"; }

struct Control
{
    juce::String id, label, desc, group, align, tag, arrow;
    juce::Colour fill { 0xff23262b }, stroke { 0xff343841 }, accent;   // accent: transparent = default
    Kind kind = Kind::Button;
    juce::Rectangle<float> bounds;
    float fontSize = 9.0f;

    // current address (replaced by whatever the Learn wizard observes)
    Msg msg = Msg::None; int ch = 1, num = 0;
    // reference address from the layout file
    Msg expMsg = Msg::None; int expCh = 1, expNum = 0;
    bool led = false;

    // runtime state
    int  value = 0;      // CC value / last note velocity
    int  ledState = 0;   // 0 off, 1 grn, 2 grn blink, 3 red, 4 red blink, 5 yel, 6 yel blink
    bool pressed = false, learned = false, mismatch = false;

    bool hasMidi() const { return msg != Msg::None; }
    juce::String addressText() const
    {
        return toString (msg).toUpperCase() + " ch" + juce::String (ch) + " #" + juce::String (num);
    }
    juce::String expectedText() const
    {
        return toString (expMsg).toUpperCase() + " ch" + juce::String (expCh) + " #" + juce::String (expNum);
    }
};

struct Layout
{
    juce::String name;
    float width = 1000.0f, height = 760.0f;
    std::vector<Control> controls;

    bool loadFromJson (const juce::String& text, juce::String& error)
    {
        juce::var root = juce::JSON::parse (text);
        if (! root.isObject()) { error = "Layout is not a JSON object"; return false; }

        juce::var list = root.getProperty ("controls", juce::var());
        auto* arr = list.getArray();
        if (arr == nullptr) { error = "Layout has no \"controls\" array"; return false; }

        std::vector<Control> out;
        for (auto& v : *arr)
        {
            Control c;
            c.id    = v.getProperty ("id", "").toString();
            c.label = v.getProperty ("label", "").toString();
            c.desc  = v.getProperty ("desc", c.id).toString();
            c.group = v.getProperty ("group", "").toString();
            c.align = v.getProperty ("align", "left").toString();
            c.kind  = kindFromString (v.getProperty ("kind", "button").toString());
            c.tag   = v.getProperty ("tag", "").toString();
            c.arrow = v.getProperty ("arrow", "").toString();
            if (auto f = v.getProperty ("fill", "").toString();   f.isNotEmpty()) c.fill   = juce::Colour::fromString (f);
            if (auto f = v.getProperty ("stroke", "").toString(); f.isNotEmpty()) c.stroke = juce::Colour::fromString (f);
            if (auto f = v.getProperty ("color", "").toString();  f.isNotEmpty()) c.accent = juce::Colour::fromString (f);
            c.bounds = { (float) (double) v.getProperty ("x", 0), (float) (double) v.getProperty ("y", 0),
                         (float) (double) v.getProperty ("w", 10), (float) (double) v.getProperty ("h", 10) };
            c.fontSize = (float) (double) v.getProperty ("size", 9.0);
            c.msg = msgFromString (v.getProperty ("msg", "").toString());
            c.ch  = (int) v.getProperty ("ch", 1);
            c.num = (int) v.getProperty ("num", 0);
            c.led = (bool) v.getProperty ("led", false);
            c.expMsg = c.msg; c.expCh = c.ch; c.expNum = c.num;
            out.push_back (std::move (c));
        }
        name   = root.getProperty ("name", "Controller").toString();
        width  = (float) (double) root.getProperty ("width", 1000);
        height = (float) (double) root.getProperty ("height", 760);
        controls = std::move (out);
        return true;
    }

    int find (Msg m, int ch, int num) const
    {
        for (size_t i = 0; i < controls.size(); ++i)
            if (controls[i].msg == m && controls[i].ch == ch && controls[i].num == num)
                return (int) i;
        return -1;
    }
};
}
