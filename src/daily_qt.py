import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from bs4 import BeautifulSoup # New library for scraping
from datetime import datetime
import re
import os

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

# --- ENGLISH TEXT (API) ---
def fetch_english_text(reference):
    # Uses WEB (World English Bible) via API
    try:
        response = requests.get(f"{BIBLE_API_URL}{reference}")
        if response.status_code == 200:
            return response.json()['text']
    except Exception as e:
        print(f"English API Error: {e}")
    return "Error fetching English text."

# --- KOREAN TEXT (SCRAPER - RNKSV) ---
def fetch_korean_rnksv(reference):
    # Scrapes '새번역' from BibleGateway
    url = "https://www.biblegateway.com/passage/"
    params = {
        "search": reference,
        "version": "RNKSV" # This is the code for 새번역
    }
    
    headers = {'User-Agent': 'Mozilla/5.0'} # Pretend to be a browser
    
    try:
        response = requests.get(url, params=params, headers=headers)
        print(f"Korean URL: {response.url}")
        print(f"Korean response status: {response.status_code}")
        
        if response.status_code != 200:
            return "Error connecting to BibleGateway."
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all span elements with class 'text'
        text_spans = soup.find_all('span', class_='text')
        print(f"Found {len(text_spans)} span.text elements")
        
        if text_spans:
            full_text = []
            for span in text_spans:
                text = span.get_text(strip=True)
                if text and len(text) > 2:  # Skip verse numbers
                    # Clean up: Remove cross-reference letters
                    text = re.sub(r'\[[a-zA-Z]\]', '', text)
                    # Remove footnote markers
                    text = re.sub(r'\s*\[\d+\]\s*', ' ', text)
                    full_text.append(text.strip())
            
            result = ' '.join(full_text)
            print(f"Extracted Korean text length: {len(result)}")
            return result if len(result) > 50 else "Error: Not enough text extracted."
        
        # Try alternative: look for 'verse' class
        verses = soup.find_all(class_=re.compile(r'.*verse.*', re.I))
        print(f"Found {len(verses)} elements with 'verse' in class")
        
        if verses:
            full_text = []
            for verse in verses:
                text = verse.get_text(strip=True)
                if text and len(text) > 5:
                    text = re.sub(r'\[[a-zA-Z0-9]\]', '', text)
                    full_text.append(text)
            
            result = ' '.join(full_text)
            print(f"Extracted from verses: {len(result)} chars")
            return result if len(result) > 50 else "Error: Not enough text extracted."
        
        # Last resort: dump a snippet of HTML for debugging
        print("=== HTML SNIPPET (first 2000 chars) ===")
        print(str(soup)[:2000])
        print("=== END SNIPPET ===")
        
        return "Error: Could not find passage text (Check reference format)."

    except Exception as e:
        print(f"Korean Scrape Error: {e}")
        import traceback
        traceback.print_exc()
        return "Error fetching Korean text."

# --- DISCORD POSTING ---
def post_to_discord(reference, eng_text, kor_text):
    # Debug: Print what we got
    print(f"English text length: {len(eng_text)}")
    print(f"Korean text length: {len(kor_text)}")
    print(f"English text preview: {eng_text[:100]}...")
    print(f"Korean text preview: {kor_text[:100]}...")
    
    # Ensure we have valid text (Discord doesn't allow empty field values)
    if not eng_text or eng_text.strip() == "":
        eng_text = "Error: No English text available"
    if not kor_text or kor_text.strip() == "":
        kor_text = "Error: No Korean text available"
    
    # Truncate if too long (Discord limit is 1024 chars per field)
    # For code blocks, we need room for the ``` markers (6 chars)
    if len(eng_text) > 1000: 
        eng_text = eng_text[:950] + "... (See Link)"
    if len(kor_text) > 994:  # Leave room for ``` markers
        kor_text = kor_text[:944] + "... (See Link)"

    # Create Links for the title
    eng_link = f"https://www.biblegateway.com/passage/?search={reference}&version=NIV"
    kor_link = f"https://www.biblegateway.com/passage/?search={reference}&version=RNKSV"

    payload = {
        "username": "Daily QT Bot",
        "embeds": [{
            "title": f"🌿 Daily Bread: {reference}",
            "url": kor_link, # Clicking title goes to Korean version
            "color": 3066993, # Teal
            "fields": [
                {
                    "name": "🇺🇸 English (WEB)",
                    "value": eng_text,
                    "inline": False
                },
                {
                    "name": "🇰🇷 Korean (새번역)",
                    "value": kor_text,  # Remove code block formatting for now
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
        kor_text = fetch_korean_rnksv(ref) # Now using the Scraper
        
        post_to_discord(ref, eng_text, kor_text)
    else:
        print("No reading scheduled for today.")

if __name__ == "__main__":
    main()