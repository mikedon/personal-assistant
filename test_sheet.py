#!/usr/bin/env python3
"""Test script to verify quick input sheet works with keyboard input."""

import sys
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/test_sheet.log')
    ]
)

from src.macos.quick_input_sheet import QuickInputSheet

def test_sheet():
    """Test that the sheet appears and accepts input."""
    print("\n" + "="*60)
    print("QUICK INPUT SHEET TEST")
    print("="*60)
    print("\nCreating sheet...")
    
    # Track if callback was called
    submitted_text = []
    
    def on_submit(parsed):
        print(f"\n✓ CALLBACK RECEIVED: {parsed}")
        submitted_text.append(parsed.text)
    
    sheet = QuickInputSheet(on_submit=on_submit)
    
    print("Showing sheet dialog...")
    sheet.show()
    
    print("\nWaiting for user input (you have 10 seconds to enter text and click Submit)...")
    for i in range(10):
        print(f"  ...{10-i} seconds remaining", end='\r')
        time.sleep(1)
    
    print("\n" + "="*60)
    if submitted_text:
        print(f"✓ TEST PASSED: Sheet accepted input: {submitted_text[0]}")
    else:
        print("✗ TEST FAILED: No input received (dialog may not have keyboard focus)")
    print("="*60 + "\n")
    
    sheet.close()

if __name__ == "__main__":
    test_sheet()
