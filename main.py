import os
import requests
import time
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def get_news_data():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://m.entertain.naver.com/ranking")
        time.sleep(15)
        
        # 기사 아이템들을 통째로 가져옵니다.
        items = driver.find_elements(By.CSS_SELECTOR, "li[class*='ranking_item'], div[class*='ranking_item']")
        news_list = []
        
        for item in items:
            try:
                # 텍스트 데이터를 줄 단위로 분리하여 파싱
                raw_text = item.text.strip().split('\n')
                if len(raw_text) < 4: continue
                
                # 보통 구조: [순위, 제목, 요약, "조회수", 숫자]
                # 사용자님께서 올려주신 텍스트 구조를 기반으로 추출
                title = raw_text[1] if not raw_text[1].isdigit() else raw_text[2]
                summary = ""
                view_count = "0"
                
                for i, line in enumerate(raw_text):
                    if "조회수" in line:
                        view_count = raw_text[i+1] if i+1 < len(raw_text) else "0"
                        # 조회수 앞의 라인이 보통 요약문입니다.
                        if i > 0 and raw_text[i-1] != title:
                            summary = raw_text[i-1]
                        break
                
                if title:
                    news_list.append({
                        'title': title,
                        'summary': summary[:80] + "..." if len(summary) > 80 else summary,
                        'views': view_count
                    })
            except:
                continue
                
        return news_list[:10]
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        if 'driver' in locals(): driver.quit()

def send_msg(content):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})

# --- 리포트 생성 ---
news_data = get_news_data()
kst = pytz.timezone('Asia/Seoul')
now = datetime.now(kst).strftime('%Y-%m-%d %H:%M')

if news_data:
    report = f"🤖 *연예 뉴스 실시간 리포트 ({now})*\n"
    report += "━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, item in enumerate(news_data, 1):
        # 숫자 이모지 생성 (1 -> 1️⃣)
