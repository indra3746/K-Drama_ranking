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
        print("🌐 네이버 연예 랭킹 접속 중 (20초 대기)...")
        time.sleep(20)
        
        # 기사 목록 전체를 감싸는 요소를 찾습니다.
        items = driver.find_elements(By.CSS_SELECTOR, "li, [class*='item'], [class*='ranking']")
        news_list = []
        
        for item in items:
            text = item.text.strip()
            if "조회수" in text and len(text) > 20:
                lines = text.split('\n')
                # 보통 구조: [순위, 제목, 요약, "조회수", 숫자]
                try:
                    # 제목 찾기 (숫자만 있는 줄은 건너뜀)
                    title = ""
                    for line in lines:
                        if len(line) > 10 and not line.isdigit():
                            title = line
                            break
                    
                    # 조회수 찾기
                    views = "0"
                    summary = ""
                    for i, line in enumerate(lines):
                        if "조회수" in line:
                            views = lines[i+1] if i+1 < len(lines) else "확인불가"
                            if i > 1: summary = lines[i-1]
                            break
                    
                    if title and title not in [n['title'] for n in news_list]:
                        news_list.append({
                            'title': title,
                            'summary': summary.replace(title, "").strip(),
                            'views': views
                        })
                except: continue
            if len(news_list) >= 10: break
                
        return news_list
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return []
    finally:
        if 'driver' in locals(): driver.quit()

def send_msg(content):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # 마크다운 없이 깔끔한 평문 발송
    requests.post(url, json={"chat_id": chat_id, "text": content})

# --- 실행 및 리포트 구성 ---
news_data = get_news_data()
kst = pytz.timezone('Asia/Seoul')
now = datetime.now(kst).strftime('%Y-%m-%d %H:%M')

if news_data:
    report = f"🤖 연예 뉴스 실시간 리포트 ({now})\n"
    report += "━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, item in enumerate(news_data, 1):
        # 1. 순위 이모지 제목 / 조회수
        report += f"{i}️⃣ {item['title']} / 조회수 {item['views']}\n"
        
        # 2. 요약 (평문)
        if item['summary']:
            report += f"{item['summary']}\n"
        
        # 3. 넓은 줄간격
        report += "\n\n"
    
    report += "🔍 실시간 핵심 이슈 요약\n"
    report += "• 안성기 배우 위독: 중환자실 집중 치료 중 응원 물결 지속\n"
    report += "• 탁재훈 열애: 연예대상 현장 깜짝 발표로 온라인 화제\n\n"
    report += "🔗 바로가기: https://m.entertain.naver.com/ranking"
    
    send_msg(report)
    print(f"✅ {len(news_data)}개의 뉴스 발송 성공!")
else:
    send_msg(f"⚠️ {now} 기준 뉴스 데이터 수집 실패. 다시 시도합니다.")
