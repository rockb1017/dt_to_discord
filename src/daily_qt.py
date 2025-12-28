import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
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
            return response.json()['text']
    except Exception as e:
        print(f"English API Error: {e}")
    return "Error fetching English text."

# --- KOREAN TEXT (API - KRV) ---
def fetch_korean_text(reference):
    # Uses KRV (Korean Revised Version) via API
    try:
        # Try KRV translation code
        response = requests.get(f"{BIBLE_API_URL}{reference}?translation=krv")
        print(f"Korean API URL: {response.url}")
        print(f"Korean API status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Korean API response keys: {data.keys()}")
            if 'text' in data:
                return data['text']
            else:
                print(f"Korean API response: {data}")
                return "Error: No text in response"
        else:
            print(f"Korean API error response: {response.text}")
    except Exception as e:
        print(f"Korean API Error: {e}")
        import traceback
        traceback.print_exc()
    return "Error fetching Korean text."



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
    
    # Truncate if too long (Discord limit is 1024 chars per field)
    if len(eng_text) > 1000: 
        eng_text = eng_text[:950] + "... [Click link above to read full text]"
    if len(kor_text) > 1000:
        kor_text = kor_text[:950] + "..."

    # Create Links
    esv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=ESV"
    koerv_link = f"https://www.biblegateway.com/passage/?search={quote(reference)}&version=KOERV"

    payload = {
        "username": "Daily QT Bot",
        "thread_name": f"Daily Bread: {reference}",  # Required for forum channels
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
                }
                # {
                #     "name": " Korean (KRV)",
                #     "value": kor_text,
                #     "inline": False
                # }
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
        # kor_text = fetch_korean_text(ref)
        
        post_to_discord(ref, eng_text, "KRV text placeholder")
    else:
        print("No reading scheduled for today.")

if __name__ == "__main__":
    main()