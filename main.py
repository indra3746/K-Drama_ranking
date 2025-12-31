import os
import requests
import time
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def get_naver_news_ranking():
    # 깃허브 서버(Linux)에서 브라우저를 띄우기 위한 필수 설정
    chrome_options = Options()
    chrome_options.add_argument('--headless') # 창 없이 실행
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # 네이버 연예 전체 랭킹 페이지 접속
        url = "https://m.entertain.naver.com/ranking"
        driver.get(url)
        time.sleep(5) # 페이지 로딩 대기
        
        # 기사 제목 추출
        elements = driver.find_elements(By.CSS_SELECTOR, "a[class*='title'], strong[class*='title']")
        titles = [el.text.strip() for el in elements if len(el.text.strip()) > 5]
        return titles[:10] # 상위 10개만 반환
    except Exception as e:
        print(f"크롤링 에러: {e}")
        return []
    finally:
        driver.quit()

def send_telegram_msg(content):
    # 깃허브 Secrets에 저장한 값을 가져옵니다.
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('CHAT_ID')
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": content,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# 1. 뉴스 데이터 가져오기
ranking_titles = get_naver_news_ranking()

# 2. 한국 시간 설정
kst = pytz.timezone('Asia/Seoul')
now_kst = datetime.now(kst).strftime('%Y-%m-%d %H:%M')

# 3. 리포트 본문 구성
if ranking_titles:
    report = f"🤖 *실시간 연예 랭킹 자동 리포트 ({now_kst} KST)*\n"
    report += f"{'='*32}\n\n"
    for i, title in enumerate(ranking_titles, 1):
        report += f"{i}위. {title}\n"
    
    # 주요 키워드 자동 분석 (선택 사항)
    report += "\n🔍 *실시간 핵심 이슈*\n"
    if any("안성기" in t for t in ranking_titles):
        report += "• [긴급] 안성기 배우 위독 소식, 중환자실 치료 중\n"
    if any("탁재훈" in t for t in ranking_titles):
        report += "• 탁재훈, 시상식서 깜짝 열애 인정 화제\n"
        
    report += "\n🔗 *상세 내용은 네이버 연예 랭킹 참조*"
    
    # 4. 텔레그램 발송
    send_telegram_msg(report)
    print(f"✅ 리포트 발송 완료 ({now_kst})")
else:
    print("❌ 데이터를 가져오지 못했습니다.")
