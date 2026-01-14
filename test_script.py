#!/usr/bin/env python3
"""Test script to check Bible text fetching without posting to Discord"""

import sys
sys.path.insert(0, 'src')

# Temporarily bypass environment checks
import os
os.environ['DISCORD_WEBHOOK_URL'] = 'test'
sys.argv.append('--test')

from daily_qt import fetch_english_text, fetch_korean_text, post_to_discord

# Test with a specific reference
test_reference = "Luke 3:1-9"  # You can change this to today's reading

print(f"Testing with reference: {test_reference}\n")
print("="*60)

eng_verses = fetch_english_text(test_reference)
print("\n" + "="*60)
kor_verses = fetch_korean_text(test_reference)
print("\n" + "="*60)

post_to_discord(test_reference, eng_verses, kor_verses, test_mode=True)
