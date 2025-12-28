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
        
        # Debug: Save the HTML to see what we're getting
        print(f"HTML length: {len(response.content)}")
        
        # Try to find the passage with more selectors
        passage_content = None
        
        # Method 1: Look for passages class
        passage_content = soup.find('div', class_='passages')
        
        # Method 2: Look for passage-display-bcv
        if not passage_content:
            passage_content = soup.find('div', class_='passage-display-bcv')
            
        # Method 3: Look for bcv (Bible Chapter Verse)
        if not passage_content:
            passage_content = soup.find('div', class_='bcv')
        
        # Method 4: Look for any div with data-passage attribute
        if not passage_content:
            passage_content = soup.find('div', attrs={'data-passage': True})
            
        # Method 5: Just get everything with class containing 'passage' and 'text'
        if not passage_content:
            all_divs = soup.find_all('div')
            for div in all_divs:
                classes = div.get('class', [])
                class_str = ' '.join(classes).lower()
                if 'passage' in class_str or 'text' in class_str:
                    # Check if it has substantial text
                    if len(div.get_text(strip=True)) > 100:
                        passage_content = div
                        print(f"Found passage using method 5: {classes}")
                        break
        
        if not passage_content:
            # Last resort: look for all <p> tags in the main content
            print("Trying to extract all paragraph text...")
            all_paragraphs = soup.find_all('p', class_=lambda x: x and 'text' in str(x).lower())
            if all_paragraphs:
                text = '\n\n'.join([p.get_text(strip=True) for p in all_paragraphs])
                return text if len(text) > 50 else "Error: Could not find passage text."
            return "Error: Could not find passage text (Check reference format)."

        # Extract text clearly
        full_text = []
        
        # Find all paragraphs or spans with text
        for element in passage_content.find_all(['p', 'span']):
            text = element.get_text() 
            if text.strip():
                # Clean up: Remove cross-reference letters often formatted like [a]
                text = re.sub(r'\[[a-zA-Z]\]', '', text) 
                full_text.append(text.strip())
        
        # Remove duplicates while preserving order
        seen = set()
        unique_text = []
        for text in full_text:
            if text not in seen and len(text) > 3:  # Skip very short fragments
                seen.add(text)
                unique_text.append(text)
            
        result = "\n\n".join(unique_text)
        print(f"Extracted Korean text length: {len(result)}")
        return result if result else "Error: No text extracted from passage."

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