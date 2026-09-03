# Milestone 2 — Explorer Analysis: Linear Crouch Slider Frontend JS Sync (`app.js`)

## 1. Overview
This report specifies the detailed JavaScript event handling, WebSocket payload structures, and state synchronization logic required in `public/app.js` to support the `#slider-crouch` element and integrate it cleanly with `#crouch-toggle` and backend state broadcasts.

---

## 2. Code Inspection & Current State

### Existing `crouch-toggle` Listener (`public/app.js` lines 197–207)
```javascript
const crouchToggle = document.getElementById('crouch-toggle');
if (crouchToggle) {
    crouchToggle.addEventListener('change', (e) => {
        resetAllButtons(null);
        const active = e.target.checked;
        sendCommand({ type: 'set_crouch', active });
        
        document.querySelector('.crouch-off-label').classList.toggle('active', !active);
        document.querySelector('.crouch-on-label').classList.toggle('active', active);
    });
}
```
**Deficiency**:
- Only sends `{ type: 'set_crouch', active }` without an `offset` field.
- Does not interact with or snap `#slider-crouch` or update `#val-crouch`.

### Existing `ws.onmessage` State Broadcast Handler (`public/app.js` lines 270–302)
```javascript
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'state') {
        const offsets = data.offsets;
        for (let ch = 0; ch < 12; ch++) {
            if (sliders[ch]) {
                sliders[ch].value = offsets[ch];
                values[ch].textContent = `${offsets[ch]}°`;
            }
        }
        updateJoints(offsets);

        // Sync toggle switch state based on average femur position
        ...
    }
};
```
**Deficiency**:
- Ignores `crouch_offset` or `crouch_active` fields sent in WebSocket broadcast state payloads.
- Does not update `#slider-crouch` position or `#val-crouch` text display.

---

## 3. Formulated JS Logic Specifications

### 3.1 Crouch Slider Input Listener (`#slider-crouch`)
- **Element Target**: `document.getElementById('slider-crouch')`
- **Value Readout Target**: `document.getElementById('val-crouch')`
- **Event**: `'input'`
- **Behavior**:
  1. `resetAllButtons(null)` to deactivate competing gait/sweep buttons.
  2. Parses integer value `val` from `e.target.value`.
  3. Updates `valCrouch.textContent` to `${val}°`.
  4. Computes `active = val !== 0`.
  5. Updates `crouchToggle.checked = active` and updates `.crouch-off-label` / `.crouch-on-label` `.active` classes.
  6. Sends WebSocket payload: `{ type: 'set_crouch', cmd: 'set_crouch', offset: val, active: active }`.

### 3.2 Crouch Toggle Handler (`#crouch-toggle`)
- **Element Target**: `document.getElementById('crouch-toggle')`
- **Event**: `'change'`
- **Behavior**:
  1. `resetAllButtons(null)`.
  2. Read `active = e.target.checked`.
  3. Compute `targetOffset = active ? -45 : 0`.
  4. Snap `#slider-crouch` value: `sliderCrouch.value = targetOffset`.
  5. Update readout text: `valCrouch.textContent = `${targetOffset}°``.
  6. Update `.crouch-off-label` and `.crouch-on-label` `.active` classes.
  7. Sends WebSocket payload: `{ type: 'set_crouch', cmd: 'set_crouch', offset: targetOffset, active: active }`.

### 3.3 Incoming WebSocket Broadcast Handling (`ws.onmessage`)
- **Event**: `ws.onmessage`
- **Behavior**:
  1. Parses `data = JSON.parse(event.data)`.
  2. Updates joint sliders and 3D viewer model as before.
  3. Inspects `data.crouch_offset` and `data.crouch_active`:
     - If `data.crouch_offset !== undefined`:
       - `sliderCrouch.value = data.crouch_offset`
       - `valCrouch.textContent = `${data.crouch_offset}°``
       - `active = data.crouch_active !== undefined ? data.crouch_active : (data.crouch_offset !== 0)`
       - `crouchToggle.checked = active`
       - Toggle `.crouch-off-label` / `.crouch-on-label` `.active` class.
     - Else if `data.crouch_active !== undefined`:
       - `active = data.crouch_active`
       - `offset = active ? -45 : 0`
       - `sliderCrouch.value = offset`
       - `valCrouch.textContent = `${offset}°``
       - `crouchToggle.checked = active`
       - Toggle label classes accordingly.

---

## 4. Proposed Diff Snippet for `public/app.js`

```javascript
<<<<
    const crouchToggle = document.getElementById('crouch-toggle');
    if (crouchToggle) {
        crouchToggle.addEventListener('change', (e) => {
            resetAllButtons(null);
            const active = e.target.checked;
            sendCommand({ type: 'set_crouch', active });
            
            document.querySelector('.crouch-off-label').classList.toggle('active', !active);
            document.querySelector('.crouch-on-label').classList.toggle('active', active);
        });
    }
====
    const sliderCrouch = document.getElementById('slider-crouch');
    const valCrouch = document.getElementById('val-crouch');
    const crouchToggle = document.getElementById('crouch-toggle');

    if (sliderCrouch) {
        sliderCrouch.addEventListener('input', (e) => {
            resetAllButtons(null);
            const val = parseInt(e.target.value);
            if (valCrouch) {
                valCrouch.textContent = `${val}°`;
            }
            const active = val !== 0;
            if (crouchToggle) {
                crouchToggle.checked = active;
            }
            document.querySelector('.crouch-off-label')?.classList.toggle('active', !active);
            document.querySelector('.crouch-on-label')?.classList.toggle('active', active);

            sendCommand({
                type: 'set_crouch',
                cmd: 'set_crouch',
                offset: val,
                active: active
            });
        });
    }

    if (crouchToggle) {
        crouchToggle.addEventListener('change', (e) => {
            resetAllButtons(null);
            const active = e.target.checked;
            const targetOffset = active ? -45 : 0;

            if (sliderCrouch) {
                sliderCrouch.value = targetOffset;
            }
            if (valCrouch) {
                valCrouch.textContent = `${targetOffset}°`;
            }

            sendCommand({
                type: 'set_crouch',
                cmd: 'set_crouch',
                offset: targetOffset,
                active: active
            });

            document.querySelector('.crouch-off-label')?.classList.toggle('active', !active);
            document.querySelector('.crouch-on-label')?.classList.toggle('active', active);
        });
    }
>>>>
```

And in `initWebSocket()`:

```javascript
<<<<
        if (data.type === 'state') {
            const offsets = data.offsets;
            for (let ch = 0; ch < 12; ch++) {
                if (sliders[ch]) {
                    sliders[ch].value = offsets[ch];
                    values[ch].textContent = `${offsets[ch]}°`;
                }
            }
            updateJoints(offsets);

            // Sync toggle switch state based on average femur position
====
        if (data.type === 'state' || data.cmd === 'state') {
            const offsets = data.offsets;
            for (let ch = 0; ch < 12; ch++) {
                if (sliders[ch]) {
                    sliders[ch].value = offsets[ch];
                    values[ch].textContent = `${offsets[ch]}°`;
                }
            }
            updateJoints(offsets);

            // Sync crouch slider and crouch toggle switch state
            const sliderCrouch = document.getElementById('slider-crouch');
            const valCrouch = document.getElementById('val-crouch');
            const crouchToggle = document.getElementById('crouch-toggle');

            if (data.crouch_offset !== undefined) {
                const offset = data.crouch_offset;
                const active = data.crouch_active !== undefined ? data.crouch_active : (offset !== 0);
                if (sliderCrouch) sliderCrouch.value = offset;
                if (valCrouch) valCrouch.textContent = `${offset}°`;
                if (crouchToggle) {
                    crouchToggle.checked = active;
                    document.querySelector('.crouch-off-label')?.classList.toggle('active', !active);
                    document.querySelector('.crouch-on-label')?.classList.toggle('active', active);
                }
            } else if (data.crouch_active !== undefined) {
                const active = data.crouch_active;
                const offset = active ? -45 : 0;
                if (sliderCrouch) sliderCrouch.value = offset;
                if (valCrouch) valCrouch.textContent = `${offset}°`;
                if (crouchToggle) {
                    crouchToggle.checked = active;
                    document.querySelector('.crouch-off-label')?.classList.toggle('active', !active);
                    document.querySelector('.crouch-on-label')?.classList.toggle('active', active);
                }
            }

            // Sync toggle switch state based on average femur position
>>>>
```

---

## 5. Verification
- `test_suite.py`: Run `python3 test_suite.py` to confirm HTML/JS contracts pass cleanly.
