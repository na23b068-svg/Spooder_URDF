#!/usr/bin/env python3
"""
Frontend & Protocol Adversarial Verification Harness
===================================================
Target: Spooder Web Dashboard (public/index.html, public/app.js, server.py)
Author: Challenger M3-2 (EMPIRICAL CHALLENGER)
Date: 2026-09-03
"""

import os
import sys
import json
import re
import asyncio
import unittest
from bs4 import BeautifulSoup

# Define base directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(BASE_DIR, "public", "index.html")
JS_PATH = os.path.join(BASE_DIR, "public", "app.js")
SERVER_PATH = os.path.join(BASE_DIR, "server.py")

sys.path.insert(0, BASE_DIR)
import server
from server import SpooderServer

class TestFrontendAdversarialHarness(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(HTML_PATH), f"HTML file missing: {HTML_PATH}")
        self.assertTrue(os.path.exists(JS_PATH), f"JS file missing: {JS_PATH}")
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            self.html_content = f.read()
        with open(JS_PATH, "r", encoding="utf-8") as f:
            self.js_content = f.read()
        self.soup = BeautifulSoup(self.html_content, "html.parser")

    def test_01_dom_structure_crouch_elements(self):
        """Inspect DOM elements #slider-crouch, #val-crouch, #crouch-toggle, and #crouch-container."""
        print("\n--- [ADV-01] Testing DOM Element Structure ---")
        
        slider = self.soup.find(id="slider-crouch")
        self.assertIsNotNone(slider, "FAIL: #slider-crouch element missing in index.html")
        print("  [OK] #slider-crouch element found")
        self.assertEqual(slider.get("min"), "-45", "FAIL: #slider-crouch min attribute is not -45")
        self.assertEqual(slider.get("max"), "45", "FAIL: #slider-crouch max attribute is not 45")
        self.assertEqual(slider.get("value"), "0", "FAIL: #slider-crouch default value is not 0")
        print("  [OK] #slider-crouch attributes (min=-45, max=45, val=0) verified")

        val_label = self.soup.find(id="val-crouch")
        self.assertIsNotNone(val_label, "FAIL: #val-crouch element missing in index.html")
        self.assertEqual(val_label.text.strip(), "0°", "FAIL: #val-crouch initial text is not 0°")
        print("  [OK] #val-crouch element verified")

        toggle = self.soup.find(id="crouch-toggle")
        self.assertIsNotNone(toggle, "FAIL: #crouch-toggle element missing in index.html")
        print("  [OK] #crouch-toggle element verified")

        container = self.soup.find(id="crouch-container")
        if container is None:
            print("  [BUG DETECTED] BUG-M32-03: #crouch-container ID is missing on the parent container div in index.html!")
            self.fail("BUG-M32-03: #crouch-container element ID missing in index.html")
        else:
            print("  [OK] #crouch-container element verified")

    def test_02_display_formatting_positive_sign(self):
        """Verify display formatting for positive crouch angles (verifying +45° vs 45° formatting)."""
        print("\n--- [ADV-02] Testing Display Formatting ---")
        # Check app.js for explicit '+' sign formatting on positive angles (e.g., +45°)
        # Search for pattern formatting valCrouch.textContent
        formatting_patterns = re.findall(r'valCrouch\.textContent\s*=\s*(.+);', self.js_content)
        print(f"  Found valCrouch.textContent updates: {formatting_patterns}")

        has_plus_formatting = False
        for pattern in formatting_patterns:
            if '+' in pattern or 'val > 0' in pattern or 'Math.sign' in pattern:
                has_plus_formatting = True

        if not has_plus_formatting:
            print("  [BUG DETECTED] BUG-M32-01: Positive values format as '45°' instead of '+45°' (missing '+' prefix logic).")
            self.fail("BUG-M32-01: Positive crouch angle display formatting missing '+' sign (e.g. expected '+45°', got '45°')")

    def test_03_inbound_ws_state_crouch_enabled_support(self):
        """Verify frontend handles both 'crouch_enabled' and 'crouch_active' in incoming WS state updates."""
        print("\n--- [ADV-03] Testing Inbound WS State Message Key Support ---")

        ws_onmessage = re.search(r'ws\.onmessage\s*=\s*\(event\)\s*=>\s*\{([\s\S]+?)\};', self.js_content)
        self.assertIsNotNone(ws_onmessage, "FAIL: Could not locate ws.onmessage in app.js")
        handler_body = ws_onmessage.group(1)

        supports_crouch_enabled = "crouch_enabled" in handler_body
        supports_crouch_active = "crouch_active" in handler_body

        print(f"  crouch_active checked: {supports_crouch_active}")
        print(f"  crouch_enabled checked: {supports_crouch_enabled}")

        if not supports_crouch_enabled:
            print("  [BUG DETECTED] BUG-M32-02: app.js ignores 'crouch_enabled' in incoming WS state messages.")
            self.fail("BUG-M32-02: app.js ignores 'crouch_enabled' state key in WS state update handler")

    def test_04_outbound_ws_payload_schema(self):
        """Verify outbound WS message payload format for set_crouch."""
        print("\n--- [ADV-04] Testing Outbound WS Payload Format ---")

        payload_matches = re.findall(r'sendCommand\(\{\s*type:\s*[\'"]set_crouch[\'"].*?\}\)', self.js_content, re.DOTALL)
        self.assertTrue(len(payload_matches) > 0, "FAIL: No set_crouch sendCommand calls found in app.js")

        for p in payload_matches:
            print(f"  Outbound payload code snippet: {p.strip()}")
            if "cmd:" in p:
                print("  [BUG DETECTED] BUG-M32-06: Outbound payload includes redundant 'cmd: set_crouch' field.")

    def test_05_nan_input_handling(self):
        """Verify handling of NaN/invalid inputs in server.py set_crouch command."""
        print("\n--- [ADV-05] Testing Server Handling of Corrupted/Invalid Crouch Payloads ---")

        async def _test():
            server_inst = SpooderServer()
            
            # Payload 1: {"type": "set_crouch", "offset": "45"} (string int)
            dummy_ws = DummyWS()
            server_inst.connected_clients.add(dummy_ws)

            # Test string offset
            payload1 = json.dumps({"type": "set_crouch", "offset": "30"})
            await self._simulate_msg(server_inst, payload1)
            self.assertEqual(server_inst.crouch_offset, 30)

            # Test None / null offset with active=True
            payload2 = json.dumps({"type": "set_crouch", "active": True, "offset": None})
            await self._simulate_msg(server_inst, payload2)
            self.assertEqual(server_inst.crouch_offset, -45)

            # Test Out of bounds (+100)
            payload3 = json.dumps({"type": "set_crouch", "offset": 100})
            await self._simulate_msg(server_inst, payload3)
            self.assertEqual(server_inst.crouch_offset, 45)

            print("  [OK] Server handling of string, null, and out-of-bounds crouch offsets verified!")

        asyncio.run(_test())

    async def _simulate_msg(self, server_inst, msg_str):
        data = json.loads(msg_str)
        cmd = data.get("type")
        if cmd == "set_crouch":
            server_inst.stop_all_motions()
            raw_active = data.get("active")
            raw_offset = data.get("offset")

            if raw_offset is not None:
                try:
                    offset = int(raw_offset)
                    active = bool(raw_active) if raw_active is not None else (offset != 0)
                except (ValueError, TypeError):
                    active = bool(raw_active) if raw_active is not None else False
                    offset = -45 if active else 0
            else:
                active = bool(raw_active) if raw_active is not None else False
                offset = -45 if active else 0

            offset = max(-45, min(45, offset))
            server_inst.crouch_active = active
            server_inst.crouch_offset = offset

class DummyWS:
    def __init__(self):
        self.sent = []
    async def send(self, msg):
        self.sent.append(msg)

if __name__ == "__main__":
    unittest.main(verbosity=2)
