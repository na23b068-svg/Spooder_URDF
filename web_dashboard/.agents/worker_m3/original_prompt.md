## 2026-09-03T05:37:56Z
MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Worker M3 for Spooder Crouch-Walk & Linear Crouch Slider project.
Your working directory is /home/smeer/Downloads/Spooder/web_dashboard/.agents/worker_m3. Please create this directory if it does not exist.

Your objective is to execute Milestone 3 Phase 2 Adversarial Hardening by implementing fixes for all exposed bugs in `server.py`, `public/app.js`, and `public/index.html`, and integrating Tier 5 Adversarial Test cases into `test_suite.py`.

### Detailed Fix Tasks:

1. **Backend Fixes (`server.py`)**:
   - Defensive Offset Parsing: In `set_crouch` handler (line ~515), parse `raw_offset` safely using `try...except (ValueError, TypeError)`. Handle non-numeric strings ("abc", "", None, floats) gracefully by defaulting to 0 or rounding/clamping to integer within [-45, 45].
   - Fix Exception Module Import: Change `except websockets.exceptions.ConnectionClosed:` to `except websockets.ConnectionClosed:` (or import `ConnectionClosed` from `websockets.exceptions`).
   - Exception Isolation: Wrap message decoding (`json.loads`) and command dispatching inside `handler()` in `try...except Exception as e:` to log error and prevent connection crashes on malformed JSON or invalid leg indices (`IndexError`).
   - Positive Crouch Femur Baseline Math: In `run_gait()` (line ~328) and posture deactivation (line ~459), ensure femur baseline crouching correctly applies negative magnitude regardless of positive slider angle value (e.g. if `crouch_offset = 30`, femur baseline must crouch DOWN by `-30°` or `-abs(offset)`, not elevate UP to `+30°`).
   - Animation Task Clean Cancel: Ensure `stop_all_motions()` cancels any active animation tasks (`self._animation_task`) to prevent overlapping task race conditions.

2. **Frontend & Markup Fixes (`public/index.html` & `public/app.js`)**:
   - Markup Contract: In `public/index.html`, add `id="crouch-container"` to the `<div class="input-group" style="margin-top: 12px;">` wrapper around the crouch slider.
   - Positive Sign Formatting: In `public/app.js`, update `valCrouch` display formatting so positive non-zero angles display with an explicit `+` sign (e.g. `val > 0 ? '+' + val + '°' : val + '°'`).
   - WS State Key Compatibility: In `public/app.js` `ws.onmessage` handler, support both `crouch_enabled` and `crouch_active` state keys:
     `const crouchActive = data.crouch_enabled !== undefined ? data.crouch_enabled : data.crouch_active;`
   - Clean Payload Schema: In `public/app.js`, remove redundant `cmd: 'set_crouch'` key from outbound `sendCommand` payloads.

3. **Tier 5 Adversarial Test Integration (`test_suite.py`)**:
   - Add Tier 5 test classes: `Tier5AdversarialWhiteBoxTests` (testing backend defensive parsing, exception isolation, positive crouch gait math, websockets exception handling) and `Tier5AdversarialFrontendProtocolTests` (testing DOM `#crouch-container`, positive display `+45°`, state key fallback `crouch_enabled`, clean WS payload schema).
   - Update `run_suite()` in `test_suite.py` to include Tier 5 in the test runner summary output.
   - Run `python3 test_suite.py` from `/home/smeer/Downloads/Spooder/web_dashboard` and verify ALL tests across Tiers 1-5 pass cleanly (100% pass rate).

4. **Handoff Report**: Write a complete report at `/home/smeer/Downloads/Spooder/web_dashboard/.agents/worker_m3/handoff.md` with:
   - Command line and output of `python3 test_suite.py`.
   - Summary of code changes made in `server.py`, `public/app.js`, `public/index.html`, and `test_suite.py`.
5. Communicate completion back to parent via send_message.
