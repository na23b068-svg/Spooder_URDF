import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let scene, camera, renderer, controls;
const legs = [];

// Constants from python script
const LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10];
const LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4];
const FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1];
const LEG_MOUNT_ANGLES = [30, 90, 150, -30, -90, -150].map(d => d * Math.PI / 180);

const P_COXA = [
    new THREE.Vector3(26.231, 35.233, 18.112),
    new THREE.Vector3(-17.397, 40.333, 18.112),
    new THREE.Vector3(-43.628, 5.1, 18.112),
    new THREE.Vector3(43.628, -5.1, 18.112),
    new THREE.Vector3(17.397, -40.333, 17.788),
    new THREE.Vector3(-26.231, -35.233, 17.788)
];

const P_FEMUR_LOCAL = [
    new THREE.Vector3(28.912, 15.177, -4.65),
    new THREE.Vector3(1.312, 32.627, -4.65),
    new THREE.Vector3(-27.6, 17.45, -4.65),
    new THREE.Vector3(27.6, -17.45, -4.65),
    new THREE.Vector3(-1.312, -32.627, -4.65),
    new THREE.Vector3(-28.912, -15.177, -4.65)
];

const URDF_TO_LEG_IDX = {
    1: 3, // RF
    2: 0, // LF
    3: 4, // RM
    4: 1, // LM
    5: 5, // RB
    6: 2  // LB
};

export function init3D() {
    const container = document.getElementById('canvas-container');

    scene = new THREE.Scene();
    
    // Camera Setup
    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 1, 2000);
    camera.up.set(0, 0, 1); // Z is up
    
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);

    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    centerCamera();

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x404040, 2);
    scene.add(ambientLight);
    const dirLight1 = new THREE.DirectionalLight(0xffffff, 2.5);
    dirLight1.position.set(100, -100, 100);
    scene.add(dirLight1);
    const dirLight2 = new THREE.DirectionalLight(0xffffff, 1);
    dirLight2.position.set(-100, 100, -50);
    scene.add(dirLight2);

    // Grid
    const gridHelper = new THREE.GridHelper(400, 20, 0x334155, 0x1e293b);
    gridHelper.rotation.x = Math.PI / 2;
    gridHelper.position.z = -50;
    scene.add(gridHelper);

    // Load Materials
    const chassisMat = new THREE.MeshStandardMaterial({ color: 0xfbbf24, roughness: 0.5, metalness: 0.2 });
    const coxaMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.7 });
    const legLeftMat = new THREE.MeshStandardMaterial({ color: 0x10b981, roughness: 0.5 });
    const legRightMat = new THREE.MeshStandardMaterial({ color: 0xa78bfa, roughness: 0.5 });

    const loader = new STLLoader();

    // 1. Load Chassis
    loader.load('models/base_link.stl', (geometry) => {
        const mesh = new THREE.Mesh(geometry, chassisMat);
        scene.add(mesh);
    });

    // Setup Hierarchical structure for each leg
    for (let i = 0; i < 6; i++) {
        legs.push({
            coxaGroup: new THREE.Group(),
            femurGroup: new THREE.Group()
        });
        
        const p_coxa = P_COXA[i];
        const p_femur = new THREE.Vector3().addVectors(p_coxa, P_FEMUR_LOCAL[i]);
        const mount_ang = LEG_MOUNT_ANGLES[i];
        
        // Coxa Group (rotates around Z)
        legs[i].coxaGroup.position.copy(p_coxa);
        scene.add(legs[i].coxaGroup);

        // Femur Group (rotates around axis perpendicular to mount angle)
        legs[i].femurGroup.position.copy(P_FEMUR_LOCAL[i]); // relative to coxa
        legs[i].axis_femur = new THREE.Vector3(-Math.sin(mount_ang), Math.cos(mount_ang), 0).normalize();
        legs[i].coxaGroup.add(legs[i].femurGroup);
    }

    // Load Leg Meshes
    for (let u_idx = 1; u_idx <= 6; u_idx++) {
        const idx = URDF_TO_LEG_IDX[u_idx];
        const p_coxa = P_COXA[idx];
        const p_femur = new THREE.Vector3().addVectors(p_coxa, P_FEMUR_LOCAL[idx]);
        const legMat = [0, 2, 4].includes(idx) ? legLeftMat : legRightMat;

        // Coxa Mesh
        loader.load(`models/link_1_step_v1_${u_idx}.stl`, (geo) => {
            geo.translate(-p_coxa.x, -p_coxa.y, -p_coxa.z);
            const mesh = new THREE.Mesh(geo, coxaMat);
            legs[idx].coxaGroup.add(mesh);
        });

        // Femur Mesh
        loader.load(`models/link_2_step_v1_${u_idx}.stl`, (geo) => {
            geo.translate(-p_femur.x, -p_femur.y, -p_femur.z);
            const mesh = new THREE.Mesh(geo, legMat);
            legs[idx].femurGroup.add(mesh);
        });

        // Tibia Mesh
        loader.load(`models/link_3_step_v1_${u_idx}.stl`, (geo) => {
            geo.translate(-p_femur.x, -p_femur.y, -p_femur.z);
            const mesh = new THREE.Mesh(geo, legMat);
            legs[idx].femurGroup.add(mesh);
        });
    }

    window.addEventListener('resize', onWindowResize);
    animate();
}

export function centerCamera() {
    camera.position.set(-150, -150, 100);
    controls.target.set(0, 0, 0);
    controls.update();
}

function onWindowResize() {
    const container = document.getElementById('canvas-container');
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

export function updateJoints(offsets) {
    for (let leg = 0; leg < 6; leg++) {
        const coxaCh = LEG_COXA_CHANNELS[leg];
        const femurCh = LEG_FEMUR_CHANNELS[leg];
        
        const coxaOffset = offsets[coxaCh] * Math.PI / 180;
        const femurOffset = (offsets[femurCh] * FEMUR_LIFT_DIRS[leg]) * Math.PI / 180;
        
        // Set Coxa rotation around Z
        legs[leg].coxaGroup.rotation.z = coxaOffset;
        
        // Set Femur rotation around its custom axis
        const femurGroup = legs[leg].femurGroup;
        femurGroup.quaternion.setFromAxisAngle(legs[leg].axis_femur, femurOffset);
    }
}
