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

# --- ENGLISH TEXT (API - WEB) ---
def fetch_english_text(reference):
    # Uses WEB (World English Bible) via API
    try:
        response = requests.get(f"{BIBLE_API_URL}{reference}")
        if response.status_code == 200:
            data = response.json()
            # Check if verses array exists for verse-by-verse formatting
            if 'verses' in data:
                verses = data['verses']
                formatted_text = '\n'.join([f"**{v['verse']}** {v['text']}" for v in verses])
                return formatted_text
            # Fallback to plain text
            return data['text']
    except Exception as e:
        print(f"English API Error: {e}")
    return "Error fetching English text."

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
        
        # Strategy 2: Extract verses with numbers
        print("\n--- Strategy 2: Looking for verse elements ---")
        
        # Method A: Look for span.text with sup.versenum
        verses_data = []
        verse_containers = passage_container.find_all('span', class_='text')
        print(f"Found {len(verse_containers)} span.text elements")
        
        if verse_containers:
            for span in verse_containers:
                # Find verse number
                verse_num = span.find('sup', class_='versenum')
                if verse_num:
                    num = verse_num.get_text(strip=True)
                    # Remove verse number to get just the text
                    verse_num.decompose()
                    text = span.get_text(strip=True)
                    # Clean up footnote markers like [a], [b]
                    text = re.sub(r'\[[a-zA-Z]\]', '', text)
                    if text:
                        verses_data.append(f"**{num}** {text}")
                        print(f"  Verse {num}: {text[:50]}...")
                else:
                    # No verse number, just text
                    text = span.get_text(strip=True)
                    text = re.sub(r'\[[a-zA-Z]\]', '', text)
                    if text and len(text) > 3:
                        verses_data.append(text)
        
        if verses_data:
            result = ' '.join(verses_data)
            print(f"\n✓ Successfully extracted {len(verses_data)} verse segments")
            print(f"Total length: {len(result)} chars")
            print(f"Preview: {result[:150]}...")
            return result
        
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
            return text
        
        # Last resort: dump HTML snippet for manual inspection
        print("\n--- FAILED: Dumping HTML snippet ---")
        print(str(soup)[:3000])
        
        return "Error: Could not extract passage text"
        
    except Exception as e:
        print(f"\nKorean Scraper Error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}"



# --- DISCORD POSTING ---
def post_to_discord(reference, eng_text, kor_text):
    # Debug: Print what we got
    print(f"English text length: {len(eng_text)}")
    print(f"Korean text length: {len(kor_text)}")
    
    # Ensure we have valid text (Discord doesn't allow empty field values)
    if not eng_text or eng_text.strip() == "":
        eng_text = "Error: No English text available"
    if not kor_text or kor_text.strip() == "":
        kor_text = "Error: No Korean text available"
    
    # Truncate if too long (Discord limit is 2000 chars per field)
    if len(eng_text) > 2000: 
        eng_text = eng_text[:1950] + "... [Click link above to read full text]"
    if len(kor_text) > 2000:
        kor_text = kor_text[:1950] + "..."

    # Create Links
    esv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=ESV"
    koerv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=KOERV"

    payload = {
        "username": "Daily DT Bot",
        "thread_name": f"{datetime.now().strftime('%m/%d')} - {reference}",  # Required for forum channels
        "embeds": [{
            "title": f"🌿 Daily Bread: {reference}",
            "color": 3066993, # Teal
            "fields": [
                {
                    "name": "🇺🇸 Click here to read in ESV",
                    "value": f"[Link]({esv_link})",
                    "inline": False
                },
                {
                    "name": "🇰🇷 쉬운성경 (KOERV) 보기",
                    "value": f"[Link]({koerv_link})",
                    "inline": False
                },
                {
                    "name": "English (WEB)",
                    "value": eng_text,
                    "inline": False
                },
                {
                    "name": "Korean (KOERV)",
                    "value": kor_text,
                    "inline": False
                }
            ],
            "footer": {
                "text": f"Posted on {datetime.now().strftime('%B %d, %Y')}"
            }
        }]
    }

    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    
    if response.status_code in [200, 204]:
        print(f"✅ Successfully posted {reference} to Discord.")
    else:
        print(f"❌ Discord webhook failed with status {response.status_code}")
        print(f"Response: {response.text}")

# --- MAIN ---
def main():
    print("Checking for today's reading...")
    ref = get_todays_reference()
    
    if ref:
        print(f"Found reference: {ref}")
        eng_text = fetch_english_text(ref)
        kor_text = fetch_korean_text(ref)
        
        post_to_discord(ref, eng_text, kor_text)
    else:
        print("No reading scheduled for today.")

if __name__ == "__main__":
    main()