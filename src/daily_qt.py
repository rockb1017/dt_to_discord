import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
from urllib.parse import quote

# --- CONFIGURATION ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
if not DISCORD_WEBHOOK_URL:
    raise ValueError("Error: DISCORD_WEBHOOK_URL environment variable is missing.")

DISCORD_GENERAL_WEBHOOK_URL = os.getenv("DISCORD_GENERAL_WEBHOOK_URL")
if not DISCORD_GENERAL_WEBHOOK_URL:
    print("Warning: DISCORD_GENERAL_WEBHOOK_URL not set. Skipping general channel notification.")

DISCORD_FORUM_CHANNEL_ID = os.getenv("DISCORD_FORUM_CHANNEL_ID")
if not DISCORD_FORUM_CHANNEL_ID:
    print("Warning: DISCORD_FORUM_CHANNEL_ID not set. Notification will not include channel link.")

DISCORD_SERVER_ID = os.getenv("DISCORD_SERVER_ID")
if not DISCORD_SERVER_ID:
    print("Warning: DISCORD_SERVER_ID not set. Notification will not include thread link.")

SHEET_NAME = "2026_Devotional_Time_Plan"
BIBLE_API_URL = "https://bible-api.com/" 

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

# --- ENGLISH TEXT (SCRAPER - ESV) ---
def fetch_english_text(reference):
    # Scrapes ESV from BibleGateway
    url = "https://www.biblegateway.com/passage/"
    params = {
        "search": reference,
        "version": "ESV"
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        print(f"\n=== ENGLISH SCRAPER DEBUG ===")
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            return ["Error: HTTP {response.status_code}"]
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find passage container
        passage_container = soup.find('div', class_='passage-col')
        if not passage_container:
            passage_container = soup.find('div', {'class': lambda x: x and 'passage' in ' '.join(x).lower()})
        if not passage_container:
            return ["Error: No passage container found"]

        # Extract all verse numbers and text
        verses_data = []
        # Find all sup tags with class 'versenum' inside passage_container
        for verse_num in passage_container.find_all('sup', class_='versenum'):
            num = verse_num.get_text(strip=True)
            # The parent span or element containing the verse text
            parent = verse_num.find_parent('span', class_='text')
            if not parent:
                # Sometimes the verse number is not inside a span.text, fallback to parent
                parent = verse_num.parent
            # Remove all sup tags (footnotes, crossrefs) except versenum
            for sup in parent.find_all('sup'):
                if 'versenum' not in sup.get('class', []):
                    sup.decompose()
            verse_num.decompose()  # Remove the verse number itself
            text = parent.get_text(separator=' ', strip=True)
            # Clean up footnote markers and extra spaces
            text = re.sub(r'\[[a-zA-Z0-9]\]', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            if text:
                verses_data.append({"num": num, "text": text})
                print(f"  Verse {num}: {text[:50]}...")

        if verses_data:
            print(f"✓ Successfully extracted {len(verses_data)} verses")
            return verses_data

        # Fallback: try to get all text from passage_container
        text = passage_container.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\[[a-zA-Z0-9]\]', '', text)
        if text:
            return [{"num": "all", "text": text}]
        return ["Error: Could not extract verses"]
        
    except Exception as e:
        print(f"\nEnglish Scraper Error: {e}")
        import traceback
        traceback.print_exc()
        return [f"Error: {str(e)}"]

# --- KOREAN TEXT (SCRAPER - KOERV) ---
def fetch_korean_text(reference):
    # Scrapes 쉬운성경 (KOERV) from BibleGateway
    from bs4 import BeautifulSoup
    
    url = "https://www.biblegateway.com/passage/"
    params = {
        "search": reference,
        "version": "KOERV"
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        print(f"\n=== KOREAN SCRAPER DEBUG ===")
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")
        print(f"HTML Length: {len(response.content)} bytes")
        
        if response.status_code != 200:
            return f"Error: HTTP {response.status_code}"
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Strategy 1: Find main passage container
        print("\n--- Strategy 1: Looking for passage containers ---")
        containers = [
            soup.find('div', class_='passage-col'),
            soup.find('div', class_='passage-content'),
            soup.find('div', class_='passages'),
            soup.find('div', {'class': lambda x: x and 'passage' in ' '.join(x).lower()})
        ]
        
        passage_container = None
        for i, container in enumerate(containers):
            if container:
                print(f"Found container method {i+1}: {container.get('class')}")
                passage_container = container
                break
        
        if not passage_container:
            print("No passage container found!")
            # Debug: Print all div classes
            all_divs = soup.find_all('div', class_=True)[:20]
            print(f"\nFirst 20 div classes found:")
            for div in all_divs:
                print(f"  - {div.get('class')}")
            return "Error: No passage container found"
        
        # Strategy 2: Extract all verse numbers and text
        print("\n--- Strategy 2: Extracting all verse numbers and text ---")
        verses_data = []
        for verse_num in passage_container.find_all('sup', class_='versenum'):
            num = verse_num.get_text(strip=True)
            parent = verse_num.find_parent('span', class_='text')
            if not parent:
                parent = verse_num.parent
            for sup in parent.find_all('sup'):
                if 'versenum' not in sup.get('class', []):
                    sup.decompose()
            verse_num.decompose()
            text = parent.get_text(separator=' ', strip=True)
            text = re.sub(r'\[[a-zA-Z]\]', '', text)
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            if text:
                verses_data.append({"num": num, "text": text})
                print(f"  Verse {num}: {text[:50]}...")

        if verses_data:
            print(f"\n✓ Successfully extracted {len(verses_data)} verse segments")
            return verses_data
        
        # Method B: Fallback - get all text from container
        print("\n--- Strategy 3: Fallback to full text extraction ---")
        # Remove unwanted elements
        for unwanted in passage_container.find_all(['h1', 'h2', 'h3', 'h4', 'div'], 
                                                   class_=['passage-display', 'publisher-info']):
            unwanted.decompose()
        
        text = passage_container.get_text(separator=' ', strip=True)
        # Clean up
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\[[a-zA-Z]\]', '', text)  # Remove footnote markers
        
        print(f"Fallback extracted: {len(text)} chars")
        print(f"Preview: {text[:200]}...")
        
        if len(text) > 100:
            # Return as single verse-like object
            return [{"num": "1", "text": text}]
        
        # Last resort: dump HTML snippet for manual inspection
        print("\n--- FAILED: Dumping HTML snippet ---")
        print(str(soup)[:3000])
        
        return ["Error: Could not extract passage text"]
        
    except Exception as e:
        print(f"\nKorean Scraper Error: {e}")
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
        verse_text = f"**{verse['num']}** {verse['text']}"
        
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
def post_to_discord(reference, eng_verses, kor_verses):
    # Chunk the verses into max 1024 char segments
    eng_chunks = chunk_verses_by_size(eng_verses, max_size=1024)
    kor_chunks = chunk_verses_by_size(kor_verses, max_size=1024)
    
    print(f"English chunks: {len(eng_chunks)}")
    print(f"Korean chunks: {len(kor_chunks)}")

    # Create Links
    esv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=ESV"
    klb_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=KLB"

    # Build fields
    fields = [
        {
            "name": "🇺🇸 Click here to read in ESV",
            "value": f"[Link]({esv_link})",
            "inline": False
        },
        {
            "name": "🇰🇷 현대인의성경 (KLB) 보기",
            "value": f"[Link]({klb_link})",
            "inline": False
        }
    ]
    
    # Add English chunks
    for i, chunk in enumerate(eng_chunks):
        suffix = f" (Part {i+1})" if len(eng_chunks) > 1 else ""
        fields.append({
            "name": f"English (ESV){suffix}",
            "value": chunk,
            "inline": False
        })
    
    # Add Korean chunks
    for i, chunk in enumerate(kor_chunks):
        suffix = f" (Part {i+1})" if len(kor_chunks) > 1 else ""
        fields.append({
            "name": f"Korean (KLB){suffix}",
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

    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    
    if response.status_code in [200, 204]:
        print(f"✅ Successfully posted {reference} to Discord.")
        
        # Try to get thread URL from response
        thread_url = None
        try:
            response_data = response.json()
            thread_id = response_data.get('id')
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
        import json
        print(f"\n=== PAYLOAD DEBUG ===")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

# --- MAIN ---
def main():
    print("Checking for today's reading...")
    ref = get_todays_reference()
    
    if ref:
        print(f"Found reference: {ref}")
        eng_verses = fetch_english_text(ref)
        kor_verses = fetch_korean_text(ref)
        post_to_discord(ref, eng_verses, kor_verses)
    else:
        print("No reading scheduled for today.")

if __name__ == "__main__":
    main()