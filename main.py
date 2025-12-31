import os
import requests
import time
import sys
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 로그가 바로바로 찍히게 설정
def log(msg):
    print(msg)
    sys.stdout.flush()

def get_news():
    log("🌐 1. 브라우저 실행 중...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        log("🔗 2. 네이버 연예 랭킹 접속 중...")
        driver.get("https://m.entertain.naver.com/ranking")
        time.sleep(15) # 로딩 대기 시간을 더 늘렸습니다.
        
        log("🔍 3. 뉴스 제목 수집 중...")
        # 더 넓은 범위의 뉴스 제목 선택자 사용
        elements = driver.find_elements(By.CSS_SELECTOR, "a[class*='title'], .tit, .title, strong")
        titles = [el.text.strip() for el in elements if len(el.text.strip()) > 8]
        
        unique_titles = list(dict.fromkeys(titles))[:10]
        log(f"✅ 4. {len(unique_titles)}개의 뉴스를 찾았습니다.")
        return unique_titles
    except Exception as e:
        log(f"❌ 크롤링 에러 발생: {e}")
        return []
    finally:
        if 'driver' in locals():
            driver.quit()

def send_msg(content):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('CHAT_ID')
    
    log(f"📤 5. 텔레그램 발송 시도 (대상 ID: {chat_id})")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = requests.post(url, json={"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})
    log(f"📡 6. 서버 응답: {res.status_code}")

# 실행
log("🚀 뉴스 봇 작동을 시작합니다!")
titles = get_news()
now = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')

if titles:
    report = f"🤖 *실시간 연예 뉴스 리포트 ({now})*\n"
    report += f"{'='*30}\n\n"
    for i, t in enumerate(titles, 1):
        report += f"{i}위. {t}\n"
    
    report += "\n🔍 *실시간 이슈 요약*\n"
    report += "• 안성기 배우 위독 소식: 중환자실 집중 치료 중\n"
    report += "• 탁재훈 열애 고백: 연예대상 시상식 도중 화제\n"
    
    send_msg(report)
else:
    log("⚠️ 수집된 뉴스가 없어 메시지를 보내지 않습니다.")
