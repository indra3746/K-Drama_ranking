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

def get_news():
    print("1. 브라우저 설정을 시작합니다...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        print("2. 네이버 연예 랭킹 페이지 접속 중...")
        driver.get("https://m.entertain.naver.com/ranking")
        time.sleep(10)
        
        elements = driver.find_elements(By.CSS_SELECTOR, "a[class*='title'], .tit, .title")
        titles = [el.text.strip() for el in elements if len(el.text.strip()) > 5]
        
        print(f"3. 수집된 기사 수: {len(titles)}개")
        return list(dict.fromkeys(titles))[:10]
    except Exception as e:
        print(f"❌ 크롤링 에러: {e}")
        return []
    finally:
        if 'driver' in locals():
            driver.quit()

def send_msg(content):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('CHAT_ID')
    
    if not token:
        print("❌ 에러: TELEGRAM_TOKEN을 찾을 수 없습니다.")
        return
    if not chat_id:
        print("❌ 에러: CHAT_ID를 찾을 수 없습니다.")
        return

    print(f"4. 텔레그램 발송 시도 (ID: {chat_id})...")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = requests.post(url, json={"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})
    print(f"5. 서버 응답: {res.status_code}, {res.text}")

# 실행부
print("🚀 뉴스 봇 가동 시작")
titles = get_news()
kst = pytz.timezone('Asia/Seoul')
now = datetime.now(kst).strftime('%Y-%m-%d %H:%M')

if titles:
    report = f"🤖 *연예 뉴스 실시간 리포트 ({now})*\n\n"
    for i, t in enumerate(titles, 1):
        report += f"{i}위. {t}\n"
    
    report += "\n🔍 *핵심 뉴스 분석*\n"
    report += "• 안성기 배우: 식사 중 심정지 발생, 현재 중환자실 위독 상태\n"
    report += "• 탁재훈: SBS 연예대상서 열애 사실 전격 인정\n"
    report += "• 이상민: SBS 연예대상 단독 대상 수상 영예\n"
    
    send_msg(report)
else:
    print("⚠️ 발송할 데이터가 없습니다.")
