#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "ApcLayout.h"
#include <functional>
#include <cmath>

// Draws the controller from the Layout table and reports clicks on pads/buttons.
class ApcSurface : public juce::Component
{
public:
    std::function<void (int)> onPress, onRelease;

    void setLayout (apc::Layout* l) { layout = l; repaint(); }
    void setTarget (int index)      { targetIndex = index; repaint(); }
    void setAnimation (bool blink, float pulse) { blinkOn = blink; pulsePhase = pulse; }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (juce::Colour (0xff0e0f11));
        if (layout == nullptr) return;

        g.saveState();
        g.addTransform (getTransform());
        g.setColour (juce::Colour (0xff1a1c20));
        g.fillRoundedRectangle (0.0f, 0.0f, layout->width, layout->height, 14.0f);

        for (size_t i = 0; i < layout->controls.size(); ++i)
            drawControl (g, layout->controls[i], (int) i == targetIndex);
        g.restoreState();
    }

    void mouseDown (const juce::MouseEvent& e) override
    {
        downIndex = hitTest (e.position);
        if (downIndex >= 0 && onPress) onPress (downIndex);
    }
    void mouseUp (const juce::MouseEvent&) override
    {
        if (downIndex >= 0 && onRelease) onRelease (downIndex);
        downIndex = -1;
    }

private:
    apc::Layout* layout = nullptr;
    int targetIndex = -1, downIndex = -1;
    bool blinkOn = true;
    float pulsePhase = 0.0f;

    juce::AffineTransform getTransform() const
    {
        const float s = juce::jmin (getWidth() / layout->width, getHeight() / layout->height);
        return juce::AffineTransform::scale (s).translated ((getWidth() - layout->width * s) * 0.5f,
                                                            (getHeight() - layout->height * s) * 0.5f);
    }

    int hitTest (juce::Point<float> p) const
    {
        if (layout == nullptr) return -1;
        const auto q = p.transformedBy (getTransform().inverted());
        for (int i = (int) layout->controls.size() - 1; i >= 0; --i)
        {
            const auto& c = layout->controls[(size_t) i];
            if ((c.kind == apc::Kind::Pad || c.kind == apc::Kind::Button) && c.bounds.expanded (2.0f).contains (q))
                return i;
        }
        return -1;
    }

    juce::Colour ledColour (int s) const
    {
        if (s <= 0) return juce::Colour (0xff2e3036);
        const bool blinking = (s % 2) == 0;
        if (blinking && ! blinkOn) return juce::Colour (0xff2e3036);
        switch ((s + 1) / 2)
        {
            case 1:  return juce::Colour (0xff2ecc40);
            case 2:  return juce::Colour (0xffff3b30);
            default: return juce::Colour (0xffffcc00);
        }
    }

    void drawControl (juce::Graphics& g, const apc::Control& c, bool isTarget) const
    {
        const auto r = c.bounds;
        using K = apc::Kind;

        if (c.kind == K::Panel)
        {
            g.setColour (c.fill);    g.fillRoundedRectangle (r, 8.0f);
            g.setColour (c.stroke);  g.drawRoundedRectangle (r, 8.0f, c.stroke == juce::Colour (0xffe6e6e6) ? 1.8f : 1.0f);
            g.setColour (juce::Colour (0xff80858f));  g.setFont (9.0f);
            g.drawText (c.label, r.reduced (6.0f, 3.0f).withHeight (12.0f), juce::Justification::topLeft, false);
            return;
        }
        if (c.kind == K::Text)
        {
            g.setColour (juce::Colour (0xff9a9ea8));  g.setFont (c.fontSize);
            g.drawText (c.label, r, c.align == "center" ? juce::Justification::centred
                                  : c.align == "right"  ? juce::Justification::centredRight
                                                        : juce::Justification::centredLeft, false);
            return;
        }

        if (c.kind == K::Pad || c.kind == K::Button)
        {
            const bool lit = c.ledState > 0;
            g.setColour (lit ? ledColour (c.ledState) : (c.kind == K::Pad ? juce::Colour (0xff2e3036) : juce::Colour (0xff3a3d44)));
            g.fillRoundedRectangle (r, 4.0f);
            g.setColour (juce::Colour (0xff5a5f69));  g.drawRoundedRectangle (r, 4.0f, 1.0f);
            if (c.pressed) { g.setColour (juce::Colours::white); g.drawRoundedRectangle (r.reduced (1.0f), 4.0f, 2.5f); }
            if (c.label.isNotEmpty())
            {
                g.setColour (lit ? juce::Colours::black : juce::Colour (0xffd0d3d9));
                g.setFont (c.fontSize);
                g.drawText (c.label, r.reduced (2.0f, 0.0f), juce::Justification::centred, false);
            }
            if (c.arrow.isNotEmpty())   // bank-select glyph
            {
                const auto m = r.getCentre();  const float k = 5.0f;  juce::Path p;
                if      (c.arrow == "left")  p.addTriangle (m.x - k, m.y, m.x + k, m.y - k, m.x + k, m.y + k);
                else if (c.arrow == "right") p.addTriangle (m.x + k, m.y, m.x - k, m.y - k, m.x - k, m.y + k);
                else if (c.arrow == "up")    p.addTriangle (m.x, m.y - k, m.x - k, m.y + k, m.x + k, m.y + k);
                else                         p.addTriangle (m.x, m.y + k, m.x - k, m.y - k, m.x + k, m.y - k);
                g.setColour (lit ? juce::Colours::black : juce::Colour (0xffd0d3d9));  g.fillPath (p);
            }
            if (c.tag.isNotEmpty())     // red 1-8 numbering on the device buttons
            {
                g.setColour (juce::Colour (0xffff3b30));  g.setFont (7.0f);
                g.drawText (c.tag, r.reduced (3.0f, 1.0f), juce::Justification::topLeft, false);
            }
        }
        else if (c.kind == K::Knob)
        {
            const float rad = juce::jmin (r.getWidth(), r.getHeight()) * 0.5f;
            const auto cen = r.getCentre();
            g.setColour (juce::Colour (0xff2a2c31));  g.fillEllipse (r);
            g.setColour (c.pressed ? juce::Colours::white : juce::Colour (0xff6a707c));  g.drawEllipse (r.reduced (1.0f), 2.0f);
            const float a = juce::jmap ((float) c.value, 0.0f, 127.0f, -2.356f, 2.356f);   // +/-135 degrees
            g.setColour (juce::Colours::white);
            g.drawLine (cen.x, cen.y, cen.x + std::sin (a) * rad * 0.8f, cen.y - std::cos (a) * rad * 0.8f, 2.5f);
        }
        else if (c.kind == K::Fader)
        {
            const float th = 22.0f, cx = r.getCentreX();
            g.setColour (juce::Colour (0xff080808));  g.fillRoundedRectangle (cx - 3.0f, r.getY(), 6.0f, r.getHeight(), 3.0f);
            const float y = r.getBottom() - th - (c.value / 127.0f) * (r.getHeight() - th);
            g.setColour (c.accent.isTransparent() ? juce::Colour (0xffbfbfc4) : c.accent);  g.fillRoundedRectangle (r.getX(), y, r.getWidth(), th, 3.0f);
            g.setColour (juce::Colours::black);       g.drawLine (r.getX() + 2, y + th * 0.5f, r.getRight() - 2, y + th * 0.5f, 1.5f);
        }
        else if (c.kind == K::HFader)
        {
            const float tw = 22.0f, cy = r.getCentreY();
            g.setColour (juce::Colour (0xff080808));  g.fillRoundedRectangle (r.getX(), cy - 3.0f, r.getWidth(), 6.0f, 3.0f);
            const float x = r.getX() + (c.value / 127.0f) * (r.getWidth() - tw);
            g.setColour (juce::Colour (0xffbfbfc4));  g.fillRoundedRectangle (x, r.getY(), tw, r.getHeight(), 3.0f);
            g.setColour (juce::Colours::black);       g.drawLine (x + tw * 0.5f, r.getY() + 2, x + tw * 0.5f, r.getBottom() - 2, 1.5f);
        }

        if (c.learned)   // little status dot: green = matches reference, orange = differs
        {
            g.setColour (c.mismatch ? juce::Colour (0xffff9500) : juce::Colour (0xff34c759));
            g.fillEllipse (r.getRight() - 7.0f, r.getBottom() - 7.0f, 6.0f, 6.0f);
        }
        if (isTarget)    // Learn wizard: pulsing cyan frame
        {
            const float a = 0.55f + 0.45f * std::sin (pulsePhase);
            g.setColour (juce::Colour (0xff00e5ff).withAlpha (a));
            g.drawRoundedRectangle (r.expanded (4.0f), 6.0f, 3.0f);
        }
    }
};
