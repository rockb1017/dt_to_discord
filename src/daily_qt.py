import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from datetime import datetime
import re
import os
from urllib.parse import quote
import json

# --- CONFIGURATION ---
# Check if running in test mode
import sys
TEST_MODE = "--test" in sys.argv

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
if not DISCORD_WEBHOOK_URL and not TEST_MODE:
    raise ValueError("Error: DISCORD_WEBHOOK_URL environment variable is missing.")

DISCORD_GENERAL_WEBHOOK_URL = os.getenv("DISCORD_GENERAL_WEBHOOK_URL")
if not DISCORD_GENERAL_WEBHOOK_URL and not TEST_MODE:
    print("Warning: DISCORD_GENERAL_WEBHOOK_URL not set. Skipping general channel notification.")

DISCORD_FORUM_CHANNEL_ID = os.getenv("DISCORD_FORUM_CHANNEL_ID")
if not DISCORD_FORUM_CHANNEL_ID and not TEST_MODE:
    print("Warning: DISCORD_FORUM_CHANNEL_ID not set. Notification will not include channel link.")

DISCORD_SERVER_ID = os.getenv("DISCORD_SERVER_ID")
if not DISCORD_SERVER_ID and not TEST_MODE:
    print("Warning: DISCORD_SERVER_ID not set. Notification will not include thread link.")

SHEET_NAME = "2026_Devotional_Time_Plan"

# --- GOOGLE SHEETS ---
def get_todays_reference():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("src/service_account.json", scope)
    client = gspread.authorize(creds)
    
    sheet = client.open(SHEET_NAME).sheet1
    data = sheet.get_all_records()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for row in data:
        # Check date (handling potential string format differences)
        if str(row['Date']) == today_str:
            return row['Reference']
    return None

# --- ENGLISH TEXT (JSON - ESV) ---
def fetch_english_text(reference):
    # Reads ESV from bible-esv.json
    try:
        print(f"\n=== ENGLISH (ESV) ===")
        print(f"Reference: {reference}")
        
        # Load JSON file
        with open('src/bible-esv.json', 'r', encoding='utf-8') as f:
            bible_data = json.load(f)
        
        # Parse reference (e.g., "Luke 3:1-9" or "Genesis 1:1-3")
        match = re.match(r'([123]?\s*[A-Za-z]+)\s+(\d+):(\d+)(?:-(\d+))?', reference)
        if not match:
            return [f"Error: Could not parse reference: {reference}"]
        
        book, chapter, start_verse, end_verse = match.groups()
        book = book.strip()
        chapter = str(chapter)
        start_verse = int(start_verse)
        end_verse = int(end_verse) if end_verse else start_verse
        
        # Check if book exists
        if book not in bible_data:
            return [f"Error: Book '{book}' not found in ESV JSON"]
        
        # Check if chapter exists
        if chapter not in bible_data[book]:
            return [f"Error: Chapter {chapter} not found in {book}"]
        
        # Extract verses
        verses_data = []
        chapter_data = bible_data[book][chapter]
        
        for verse_num in range(start_verse, end_verse + 1):
            verse_str = str(verse_num)
            if verse_str in chapter_data:
                text = chapter_data[verse_str]
                verses_data.append({"num": verse_str, "text": text})
                print(f"  Verse {verse_num}: {text[:50]}...")
            else:
                print(f"  Warning: Verse {verse_num} not found")
        
        if verses_data:
            print(f"✓ Successfully extracted {len(verses_data)} verses")
            return verses_data
        else:
            return [f"Error: No verses found for {reference}"]
        
    except Exception as e:
        print(f"\nEnglish JSON Error: {e}")
        import traceback
        traceback.print_exc()
        return [f"Error: {str(e)}"]

# --- KOREAN TEXT (JSON - RNKSV) ---
def fetch_korean_text(reference):
    # Reads 개역개정 (RNKSV) from bible-rnksv.json
    try:
        print(f"\n=== KOREAN (RNKSV) ===")
        print(f"Reference: {reference}")
        
        # Load JSON file
        with open('src/bible-rnksv.json', 'r', encoding='utf-8') as f:
            bible_data = json.load(f)
        
        # Parse reference (e.g., "Luke 3:1-9" or "Genesis 1:1-3")
        match = re.match(r'([123]?\s*[A-Za-z]+)\s+(\d+):(\d+)(?:-(\d+))?', reference)
        if not match:
            return [f"Error: Could not parse reference: {reference}"]
        
        book, chapter, start_verse, end_verse = match.groups()
        book = book.strip()
        chapter = str(chapter)
        start_verse = int(start_verse)
        end_verse = int(end_verse) if end_verse else start_verse
        
        # Check if book exists
        if book not in bible_data:
            return [f"Error: Book '{book}' not found in RNKSV JSON"]
        
        # Check if chapter exists
        if chapter not in bible_data[book]:
            return [f"Error: Chapter {chapter} not found in {book}"]
        
        # Extract verses
        verses_data = []
        chapter_data = bible_data[book][chapter]
        
        for verse_num in range(start_verse, end_verse + 1):
            verse_str = str(verse_num)
            if verse_str in chapter_data:
                text = chapter_data[verse_str]
                verses_data.append({"num": verse_str, "text": text})
                print(f"  Verse {verse_num}: {text[:50]}...")
            else:
                print(f"  Warning: Verse {verse_num} not found")
        
        if verses_data:
            print(f"✓ Successfully extracted {len(verses_data)} verses")
            return verses_data
        else:
            return [f"Error: No verses found for {reference}"]
        
    except Exception as e:
        print(f"\nKorean JSON Error: {e}")
        import traceback
        traceback.print_exc()
        return [f"Error: {str(e)}"]

# --- TEXT CHUNKING ---
def chunk_verses_by_size(verses, max_size=1024):
    """Split verses into chunks that don't exceed max_size"""
    if isinstance(verses, str):
        # If it's an error string, return as is
        return [verses]
    
    if isinstance(verses, list) and len(verses) > 0 and isinstance(verses[0], str):
        # If it's a list of error strings
        return verses
    
    chunks = []
    current_chunk = ""
    
    for verse in verses:
        # Ensure verse is a dict and has required keys
        if not isinstance(verse, dict) or 'num' not in verse or 'text' not in verse:
            print(f"Warning: Invalid verse data: {type(verse)}")
            continue
        
        # Ensure text is a string
        text_value = verse['text']
        if not isinstance(text_value, str):
            print(f"Warning: verse['text'] is {type(text_value)}, not str. Converting...")
            text_value = str(text_value) if text_value else ""
        
        verse_text = f"**{verse['num']}** {text_value}"
        
        # Check if adding this verse would exceed the limit
        if current_chunk:
            test_chunk = current_chunk + " " + verse_text
        else:
            test_chunk = verse_text
        
        if len(test_chunk) > max_size:
            # Save current chunk if it has content
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = verse_text
            else:
                # Single verse is too long, truncate it
                chunks.append(verse_text[:max_size - 50] + "...")
                current_chunk = ""
        else:
            current_chunk = test_chunk
    
    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else ["Error: No text to display"]


# --- GENERAL CHANNEL NOTIFICATION ---
def post_notification_to_general(reference, thread_url=None):
    """Post a simple notification to #general channel"""
    if not DISCORD_GENERAL_WEBHOOK_URL:
        print("Warning: DISCORD_GENERAL_WEBHOOK_URL not set. Skipping general channel notification.")
        return
    
    date_str = datetime.now().strftime('%m/%d')
    
    # Create message with thread link if available
    if thread_url:
        message = f"📖 New Daily Devotional is up! **{date_str} - {reference}** - [Read here]({thread_url})"
    elif DISCORD_FORUM_CHANNEL_ID:
        message = f"📖 New Daily Devotional is up! **{date_str} - {reference}** - Check <#{DISCORD_FORUM_CHANNEL_ID}>!"
    else:
        message = f"📖 New Daily Devotional is up! **{date_str} - {reference}** - Check the forum channel!"
    
    payload = {
        "username": "Daily DT Bot",
        "content": message
    }
    
    response = requests.post(DISCORD_GENERAL_WEBHOOK_URL, json=payload)
    
    if response.status_code in [200, 204]:
        print(f"✅ Notification posted to #general")
    else:
        print(f"⚠️ Failed to post notification to #general: {response.status_code}")
        print(f"Response: {response.text}")

# --- DISCORD POSTING ---
def post_to_discord(reference, eng_verses, kor_verses, test_mode=False):
    # Chunk the verses into max 1024 char segments
    eng_chunks = chunk_verses_by_size(eng_verses, max_size=1024)
    kor_chunks = chunk_verses_by_size(kor_verses, max_size=1024)
    
    print(f"English chunks: {len(eng_chunks)}")
    print(f"Korean chunks: {len(kor_chunks)}")
    
    # Debug: check chunk types
    for i, chunk in enumerate(eng_chunks):
        if not isinstance(chunk, str):
            print(f"ERROR: English chunk {i} is {type(chunk)}, not str!")
            eng_chunks[i] = str(chunk)  # Force convert to string
    
    for i, chunk in enumerate(kor_chunks):
        if not isinstance(chunk, str):
            print(f"ERROR: Korean chunk {i} is {type(chunk)}, not str!")
            kor_chunks[i] = str(chunk)  # Force convert to string

    # Create Links
    esv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=ESV"
    rnksv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=RNKSV"
    today_date = datetime.now().strftime("%Y-%m-%d")
    notes_link = f"https://youthdt.bridgeway.online/?date={today_date}"

    # Build fields
    fields = [
        {
            "name": "📝 Click here to read and write devotional notes",
            "value": f"[Link]({notes_link})",
            "inline": False
        }
    ]
    
    # Add English chunks
    for i, chunk in enumerate(eng_chunks):
        if i == 0:
            name = "English (ESV)"
        else:
            name = "\u200b"  # Zero-width space for blank header
        fields.append({
            "name": name,
            "value": chunk,
            "inline": False
        })
    
    # Add Korean chunks
    for i, chunk in enumerate(kor_chunks):
        if i == 0:
            name = "Korean (새번역)"
        else:
            name = "\u200b"  # Zero-width space for blank header
        fields.append({
            "name": name,
            "value": chunk,
            "inline": False
        })

    payload = {
        "username": "Daily DT Bot",
        "thread_name": f"{datetime.now().strftime('%m/%d')} - {reference}",  # Required for forum channels
        "embeds": [{
            "title": f"🌿 Daily Bread: {reference}",
            "color": 3066993, # Teal
            "fields": fields,
            "footer": {
                "text": f"Posted on {datetime.now().strftime('%B %d, %Y')}"
            }
        }]
    }

    if test_mode:
        print(f"\n{'='*60}")
        print(f"TEST MODE - Not posting to Discord")
        print(f"{'='*60}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\n{'='*60}")
        print(f"English chunks preview:")
        for i, chunk in enumerate(eng_chunks):
            print(f"\nChunk {i+1}:")
            print(chunk[:200] + "..." if len(chunk) > 200 else chunk)
        print(f"\n{'='*60}")
        print(f"Korean chunks preview:")
        for i, chunk in enumerate(kor_chunks):
            print(f"\nChunk {i+1}:")
            print(chunk[:200] + "..." if len(chunk) > 200 else chunk)
        print(f"{'='*60}")
        return
    
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    
    if response.status_code in [200, 204]:
        print(f"✅ Successfully posted {reference} to Discord.")
        
        # Try to get thread URL from response
        thread_url = None
        try:
            response_data = response.json()
            # For forum channels, channel_id contains the thread ID where the message was posted
            thread_id = response_data.get('channel_id')
            if thread_id and DISCORD_SERVER_ID:
                thread_url = f"https://discord.com/channels/{DISCORD_SERVER_ID}/{thread_id}"
                print(f"Thread URL: {thread_url}")
        except:
            pass
        
        # Post notification to general channel
        post_notification_to_general(reference, thread_url)
    else:
        print(f"❌ Discord webhook failed with status {response.status_code}")
        print(f"Response: {response.text}")
        # Also print the payload for debugging
        print(f"\n=== PAYLOAD DEBUG ===")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

# --- MAIN ---
def main(test_mode=False):
    print("Checking for today's reading...")
    ref = get_todays_reference()
    
    if ref:
        print(f"Found reference: {ref}")
        eng_verses = fetch_english_text(ref)
        kor_verses = fetch_korean_text(ref)
        post_to_discord(ref, eng_verses, kor_verses, test_mode=test_mode)
    else:
        print("No reading scheduled for today.")

if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    main(test_mode=test_mode)
