# Milestone 2 — Explorer Analysis: Linear Crouch Slider UI & Styling

## 1. Overview
This report specifies the HTML markup and CSS rules required to implement `#slider-crouch` in `public/index.html` and `public/style.css` for Milestone 2.

---

## 2. Existing UI Inspection

### `public/index.html` (Lines 49–71)
```html
<div class="card pose-card">
    <h3>System Presets</h3>
    <div class="toggle-container">
        <span class="toggle-label sit-label">Sit</span>
        <label class="switch">
            <input type="checkbox" id="pose-toggle">
            <span class="slider round"></span>
        </label>
        <span class="toggle-label stand-label">Stand</span>
    </div>
    <div class="toggle-container" style="margin-top: 12px;">
        <span class="toggle-label crouch-off-label active">Crouch OFF</span>
        <label class="switch">
            <input type="checkbox" id="crouch-toggle">
            <span class="slider round"></span>
        </label>
        <span class="toggle-label crouch-on-label">Crouch ON</span>
    </div>
    <div class="input-group" style="margin-top: 12px;">
        <label>Pose Speed: <span id="val-pose-speed">1.0x</span></label>
        <input type="range" id="slider-pose-speed" min="0.2" max="3.0" step="0.1" value="1.0">
    </div>
</div>
```

### `public/style.css` (Relevant Rules)
- Global Slider Rule (Lines 222–225):
  ```css
  input[type="range"] {
      flex: 1;
      accent-color: var(--accent);
  }
  ```
- Input Group Rule (Lines 210–220):
  ```css
  .input-group {
      display: flex;
      align-items: center;
      margin-bottom: 10px;
  }
  .input-group label {
      width: 80px;
      font-size: 13px;
      color: var(--text-muted);
  }
  ```
- Pose Card Rule (Lines 265–270):
  ```css
  .pose-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
  }
  ```

---

## 3. Proposed HTML Specification for `#slider-crouch`

Target File: `public/index.html`
Placement: Inside `<div class="card pose-card">`, immediately below the Crouch toggle container (`<div class="toggle-container" style="margin-top: 12px;">...</div>`) and above the Pose Speed input group.

### Proposed Markup
```html
<div class="input-group" style="margin-top: 12px;">
    <label>Crouch Angle: <span id="val-crouch">0°</span></label>
    <input type="range" id="slider-crouch" min="-45" max="45" step="1" value="0">
</div>
```

### Specification Details
1. **Container**: `<div class="input-group" style="margin-top: 12px;">` matches existing control groupings in `.pose-card`.
2. **Label**: `<label>Crouch Angle: <span id="val-crouch">0°</span></label>` provides text label and dynamic numerical readout span.
3. **Element ID**: `id="slider-crouch"` satisfying requirement R2.
4. **Range Attributes**:
   - `min="-45"`
   - `max="45"`
   - `step="1"`
   - `value="0"`

---

## 4. Proposed CSS Specification for `public/style.css`

Target File: `public/style.css`

### Proposed CSS Enhancements
To fit the new slider cleanly inside `.pose-card` without layout overflow within the fixed `height: 250px` `.controls-panel`:

```css
/* Pose Card Input Group Tuning */
.pose-card .input-group {
    width: 100%;
    max-width: 260px;
    margin-top: 8px !important;
    margin-bottom: 4px;
}

.pose-card .input-group label {
    width: 110px;
    font-size: 13px;
    color: var(--text-muted);
}

.pose-card .toggle-container {
    margin-top: 10px !important;
}
```

### Rationale
- `width: 100%; max-width: 260px;`: Ensures input groups stretch horizontally while remaining centered inside `.pose-card`.
- `width: 110px;` on label: Prevents `"Crouch Angle: -45°"` from wrapping to a second line.
- Margin reduction (`margin-top: 10px`, `margin-top: 8px`): Preserves vertical spacing inside fixed-height controls panel (250px).

---

## 5. Verification Plan
- Inspect `public/index.html` structure after implementation.
- Run `python3 test_suite.py` to confirm Tier 1 test `test_03_crouch_slider_ui_markup_contract` passes.
