import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from bs4 import BeautifulSoup # New library for scraping
from datetime import datetime
import re
import os

# --- CONFIGURATION ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
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
        if response.status_code != 200:
            return "Error connecting to BibleGateway."
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # The text is usually inside a div class 'passage-text'
        passage_content = soup.find('div', class_='passage-text')
        
        if not passage_content:
            return "Error: Could not find passage text (Check reference format)."

        # Extract text clearly
        # BibleGateway puts verse numbers in <sup> tags and footnotes in special classes.
        # We want to keep it readable.
        
        full_text = []
        
        # Find all verse paragraphs
        paragraphs = passage_content.find_all('p')
        
        for p in paragraphs:
            # Get text but remove the little footnote letters if possible
            # This is a simple extraction; might include small verse numbers
            text = p.get_text() 
            
            # Clean up: Remove cross-reference letters often formatted like [a]
            text = re.sub(r'\[[a-zA-Z]\]', '', text) 
            
            # Clean up: Remove extra verse numbers that stick to words
            # (BibleGateway formatting can be tricky, this keeps it simple)
            full_text.append(text.strip())
            
        return "\n\n".join(full_text)

    except Exception as e:
        print(f"Korean Scrape Error: {e}")
        return "Error fetching Korean text."

# --- DISCORD POSTING ---
def post_to_discord(reference, eng_text, kor_text):
    # Truncate if too long (Discord limit is 1024 chars per field)
    if len(eng_text) > 1000: eng_text = eng_text[:950] + "... (See Link)"
    if len(kor_text) > 1000: kor_text = kor_text[:950] + "... (See Link)"

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
                    "value": f"```{kor_text}```", 
                    "inline": False
                }
            ],
            "footer": {
                "text": f"Posted on {datetime.now().strftime('%B %d, %Y')}"
            }
        }]
    }

    requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print(f"Posted {reference} to Discord.")

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