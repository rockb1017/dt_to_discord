#!/usr/bin/env python3
"""Test script to validate Bible JSON reading without posting to Discord"""

import os
import sys

# Set dummy environment variables to bypass checks
os.environ['DISCORD_WEBHOOK_URL'] = 'dummy'
os.environ['DISCORD_GENERAL_WEBHOOK_URL'] = 'dummy'
os.environ['DISCORD_FORUM_CHANNEL_ID'] = 'dummy'
os.environ['DISCORD_SERVER_ID'] = 'dummy'

# Add test mode flag
sys.argv.append('--test')

from daily_qt import fetch_english_text, fetch_korean_text, chunk_verses_by_size
import json

# Test with Luke 3:1-9
test_reference = "Luke 3:1-9"

print(f"Testing with: {test_reference}")
print("=" * 60)

# Fetch English verses
eng_verses = fetch_english_text(test_reference)
print(f"\n{'=' * 60}")
print(f"English Result Type: {type(eng_verses)}")
if isinstance(eng_verses, list) and len(eng_verses) > 0:
    print(f"First item type: {type(eng_verses[0])}")
    if isinstance(eng_verses[0], dict):
        print(f"Keys: {eng_verses[0].keys()}")
        print(f"\nFull English verses:")
        for verse in eng_verses:
            print(f"  {verse['num']}: {verse['text']}")

# Fetch Korean verses
kor_verses = fetch_korean_text(test_reference)
print(f"\n{'=' * 60}")
print(f"Korean Result Type: {type(kor_verses)}")
if isinstance(kor_verses, list) and len(kor_verses) > 0:
    print(f"First item type: {type(kor_verses[0])}")
    if isinstance(kor_verses[0], dict):
        print(f"Keys: {kor_verses[0].keys()}")
        print(f"\nFull Korean verses:")
        for verse in kor_verses:
            print(f"  {verse['num']}: {verse['text']}")

# Test chunking
print(f"\n{'=' * 60}")
print("Testing chunking...")
eng_chunks = chunk_verses_by_size(eng_verses)
kor_chunks = chunk_verses_by_size(kor_verses)

print(f"\nEnglish chunks: {len(eng_chunks)}")
for i, chunk in enumerate(eng_chunks):
    print(f"\nChunk {i+1} ({len(chunk)} chars):")
    print(chunk[:150] + "..." if len(chunk) > 150 else chunk)

print(f"\nKorean chunks: {len(kor_chunks)}")
for i, chunk in enumerate(kor_chunks):
    print(f"\nChunk {i+1} ({len(chunk)} chars):")
    print(chunk[:150] + "..." if len(chunk) > 150 else chunk)

print(f"\n{'=' * 60}")
print("✅ Test complete!")
