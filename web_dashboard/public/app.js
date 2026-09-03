import { init3D, updateJoints, centerCamera } from './3d_viewer.js';

const LEG_NAMES = ["Left Front", "Left Middle", "Left Back", "Right Front", "Right Middle", "Right Back"];
const LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10];
const LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4];

let ws;
const sliders = {};
const values = {};
let gaitActive = false;
let sweepActive = false;
const legSweepsActive = Array(6).fill(false);

function resetAllButtons(exceptButton = null) {
    const gaitBtn = document.getElementById('btn-gait-toggle');
    if (gaitBtn && gaitBtn !== exceptButton) {
        gaitActive = false;
        gaitBtn.textContent = "Start Gait";
        gaitBtn.classList.remove('active');
    }
    const sweepBtn = document.getElementById('btn-sweep-toggle');
    if (sweepBtn && sweepBtn !== exceptButton) {
        sweepActive = false;
        sweepBtn.textContent = "Start Sweep";
        sweepBtn.classList.remove('active');
    }
    const legSweepBtns = document.querySelectorAll('.btn-leg-sweep');
    legSweepBtns.forEach((btn, index) => {
        if (btn !== exceptButton) {
            legSweepsActive[index] = false;
            btn.textContent = "Sweep Leg";
            btn.classList.remove('active');
        }
    });
}

function initUI() {
    const leftSidebar = document.getElementById('left-sidebar');
    const rightSidebar = document.getElementById('right-sidebar');
    const template = document.getElementById('leg-card-template').content;

    for (let leg = 0; leg < 6; leg++) {
        const clone = document.importNode(template, true);
        clone.querySelector('.leg-title').textContent = `Leg ${leg}: ${LEG_NAMES[leg]}`;
        
        const coxaCh = LEG_COXA_CHANNELS[leg];
        const femurCh = LEG_FEMUR_CHANNELS[leg];
        
        clone.querySelector('.ch-coxa').textContent = coxaCh;
        clone.querySelector('.ch-femur').textContent = femurCh;
        
        const sliderCoxa = clone.querySelector('.slider-coxa');
        const sliderFemur = clone.querySelector('.slider-femur');
        
        const valCoxa = clone.querySelector('.val-coxa');
        const valFemur = clone.querySelector('.val-femur');

        sliderCoxa.addEventListener('input', (e) => {
            valCoxa.textContent = `${e.target.value}°`;
            sendServoCommand(coxaCh, parseInt(e.target.value));
        });
        
        sliderFemur.addEventListener('input', (e) => {
            valFemur.textContent = `${e.target.value}°`;
            sendServoCommand(femurCh, parseInt(e.target.value));
        });

        sliders[coxaCh] = sliderCoxa;
        sliders[femurCh] = sliderFemur;
        values[coxaCh] = valCoxa;
        values[femurCh] = valFemur;

        const btnLegCenter = clone.querySelector('.btn-leg-center');
        btnLegCenter.addEventListener('click', () => {
            resetAllButtons(null);
            sendCommand({ type: 'center_leg', leg });
        });

        const sliderLegSpeed = clone.querySelector('.slider-leg-speed');
        sliderLegSpeed.addEventListener('input', (e) => {
            sendCommand({
                type: 'set_leg_sweep',
                leg: leg,
                active: legSweepsActive[leg],
                speed: parseFloat(e.target.value)
            });
        });

        const btnLegSweep = clone.querySelector('.btn-leg-sweep');
        btnLegSweep.addEventListener('click', (e) => {
            const willBeActive = !e.target.classList.contains('active');
            resetAllButtons(willBeActive ? e.target : null);
            
            legSweepsActive[leg] = willBeActive;
            e.target.textContent = willBeActive ? "Stop Sweep" : "Sweep Leg";
            e.target.classList.toggle('active', willBeActive);
            
            sendCommand({
                type: 'set_leg_sweep',
                leg: leg,
                active: willBeActive,
                speed: parseFloat(sliderLegSpeed.value)
            });
        });

        if (leg < 3) leftSidebar.appendChild(clone);
        else rightSidebar.appendChild(clone);
    }
    
    // UI Handlers
    document.getElementById('select-motion-profile').addEventListener('change', (e) => {
        sendCommand({
            type: 'set_motion_profile',
            profile: e.target.value
        });
    });

    const sliderPoseSpeed = document.getElementById('slider-pose-speed');
    const valPoseSpeed = document.getElementById('val-pose-speed');
    sliderPoseSpeed.addEventListener('input', (e) => {
        valPoseSpeed.textContent = parseFloat(e.target.value).toFixed(1) + 'x';
    });
    sliderPoseSpeed.addEventListener('change', (e) => {
        sendCommand({
            type: 'set_pose_speed',
            speed: parseFloat(e.target.value)
        });
    });

    document.getElementById('btn-center-all').addEventListener('click', () => {
        resetAllButtons(null);
        sendCommand({ type: 'center_all' });
    });
    
    document.getElementById('btn-recalibrate').addEventListener('click', () => {
        resetAllButtons(null);
        sendCommand({ type: 'recalibrate' });
    });
    
    document.getElementById('btn-reset-cam').addEventListener('click', () => {
        centerCamera();
    });

    document.getElementById('btn-gait-toggle').addEventListener('click', (e) => {
        gaitActive = !gaitActive;
        resetAllButtons(gaitActive ? e.target : null);
        e.target.textContent = gaitActive ? "Stop Gait" : "Start Gait";
        e.target.classList.toggle('active', gaitActive);
        
        sendCommand({
            type: 'set_gait',
            active: gaitActive,
            speed: parseFloat(document.getElementById('gait-speed').value),
            sweep: parseFloat(document.getElementById('gait-sweep').value),
            lift: parseFloat(document.getElementById('gait-lift').value),
            direction: document.getElementById('gait-direction').value
        });
    });

    document.getElementById('gait-direction').addEventListener('change', (e) => {
        if (gaitActive) {
            sendCommand({
                type: 'set_gait',
                active: true,
                speed: parseFloat(document.getElementById('gait-speed').value),
                sweep: parseFloat(document.getElementById('gait-sweep').value),
                lift: parseFloat(document.getElementById('gait-lift').value),
                direction: e.target.value
            });
        }
    });

    document.getElementById('btn-sweep-toggle').addEventListener('click', (e) => {
        sweepActive = !sweepActive;
        resetAllButtons(sweepActive ? e.target : null);
        e.target.textContent = sweepActive ? "Stop Sweep" : "Start Sweep";
        e.target.classList.toggle('active', sweepActive);
        
        sendCommand({
            type: 'set_sweep',
            active: sweepActive,
            speed: parseFloat(document.getElementById('sweep-speed').value),
            mode: document.getElementById('sweep-mode').value
        });
    });

    const poseToggle = document.getElementById('pose-toggle');
    poseToggle.addEventListener('change', (e) => {
        resetAllButtons(null);
        const pose = e.target.checked ? "stand" : "sit";
        sendCommand({ type: 'set_pose', pose });
        
        document.querySelector('.sit-label').classList.toggle('active', !e.target.checked);
        document.querySelector('.stand-label').classList.toggle('active', e.target.checked);
    });

    const sliderCrouch = document.getElementById('slider-crouch');
    const valCrouch = document.getElementById('val-crouch');
    if (sliderCrouch) {
        sliderCrouch.addEventListener('input', (e) => {
            resetAllButtons(null);
            const val = parseInt(e.target.value);
            if (valCrouch) {
                valCrouch.textContent = `${val}°`;
            }
            const active = (val !== 0);
            const crouchToggle = document.getElementById('crouch-toggle');
            if (crouchToggle) {
                crouchToggle.checked = active;
                const offLabel = document.querySelector('.crouch-off-label');
                const onLabel = document.querySelector('.crouch-on-label');
                if (offLabel) offLabel.classList.toggle('active', !active);
                if (onLabel) onLabel.classList.toggle('active', active);
            }
            sendCommand({ type: 'set_crouch', cmd: 'set_crouch', offset: val, active: active });
        });
    }

    const crouchToggle = document.getElementById('crouch-toggle');
    if (crouchToggle) {
        crouchToggle.addEventListener('change', (e) => {
            resetAllButtons(null);
            const active = e.target.checked;
            const val = active ? -45 : 0;
            const sliderCrouch = document.getElementById('slider-crouch');
            const valCrouch = document.getElementById('val-crouch');
            if (sliderCrouch) {
                sliderCrouch.value = val;
            }
            if (valCrouch) {
                valCrouch.textContent = `${val}°`;
            }
            const offLabel = document.querySelector('.crouch-off-label');
            const onLabel = document.querySelector('.crouch-on-label');
            if (offLabel) offLabel.classList.toggle('active', !active);
            if (onLabel) onLabel.classList.toggle('active', active);
            sendCommand({ type: 'set_crouch', cmd: 'set_crouch', offset: val, active: active });
        });
    }

    const sensInput = document.getElementById('slider-scroll-sens');
    const sensVal = document.getElementById('val-scroll-sens');
    if (sensInput && sensVal) {
        sensInput.addEventListener('input', (e) => {
            sensVal.textContent = `${e.target.value}°`;
        });
    }
}

// Global wheel listener for joint sliders
window.addEventListener('wheel', (e) => {
    const slider = e.target.closest('input[type="range"]') || (e.target.closest('.joint') ? e.target.closest('.joint').querySelector('input[type="range"]') : null);
    if (!slider) return;
    
    let ch = null;
    for (let c in sliders) {
        if (sliders[c] === slider) {
            ch = parseInt(c);
            break;
        }
    }
    if (ch === null) return;
    
    e.preventDefault();
    
    const sensInput = document.getElementById('slider-scroll-sens');
    const step = sensInput ? parseInt(sensInput.value) : 5;
    const min = parseInt(slider.min);
    const max = parseInt(slider.max);
    let val = parseInt(slider.value);
    
    if (e.deltaY < 0) {
        val = Math.min(max, val + step);
    } else if (e.deltaY > 0) {
        val = Math.max(min, val - step);
    }
    
    slider.value = val;
    if (values[ch]) {
        values[ch].textContent = `${val}°`;
    }
    
    sendServoCommand(ch, val);
}, { passive: false });

function initWebSocket() {
    const statusLabel = document.getElementById('connection-status');
    // Using current hostname to allow mobile access on same network
    ws = new WebSocket(`ws://${window.location.hostname}:8765`);
    
    ws.onopen = () => {
        statusLabel.textContent = "Connected";
        statusLabel.className = "status-connected";
    };
    
    ws.onclose = () => {
        statusLabel.textContent = "Disconnected (Retrying...)";
        statusLabel.className = "status-disconnected";
        setTimeout(initWebSocket, 2000);
    };
    
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

            const sliderCrouch = document.getElementById('slider-crouch');
            const valCrouch = document.getElementById('val-crouch');
            const crouchToggle = document.getElementById('crouch-toggle');

            if (data.crouch_offset !== undefined) {
                const crouchVal = data.crouch_offset;
                if (sliderCrouch) sliderCrouch.value = crouchVal;
                if (valCrouch) valCrouch.textContent = `${crouchVal}°`;
            }
            if (data.crouch_active !== undefined) {
                const crouchActive = data.crouch_active;
                if (crouchToggle) crouchToggle.checked = crouchActive;
                const offLabel = document.querySelector('.crouch-off-label');
                const onLabel = document.querySelector('.crouch-on-label');
                if (offLabel) offLabel.classList.toggle('active', !crouchActive);
                if (onLabel) onLabel.classList.toggle('active', crouchActive);
            }

            // Sync toggle switch state based on average femur position
            let femurSum = 0;
            for (let ch of LEG_FEMUR_CHANNELS) {
                femurSum += offsets[ch];
            }
            const avgFemur = femurSum / 6;
            const poseToggle = document.getElementById('pose-toggle');
            if (poseToggle) {
                if (avgFemur < -45) {
                    poseToggle.checked = false;
                    document.querySelector('.sit-label').classList.add('active');
                    document.querySelector('.stand-label').classList.remove('active');
                } else {
                    poseToggle.checked = true;
                    document.querySelector('.sit-label').classList.remove('active');
                    document.querySelector('.stand-label').classList.add('active');
                }
            }
        }
    };
}

function sendCommand(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    }
}

function sendServoCommand(channel, offset) {
    sendCommand({ type: 'set_servo', channel, offset });
}

function startApp() {
    initUI();
    init3D();
    initWebSocket();
}

if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', startApp);
} else {
    startApp();
}
