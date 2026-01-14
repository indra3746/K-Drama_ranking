import time
import datetime
import os
import requests
from bs4 import BeautifulSoup

# 셀레니움 라이브러리
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 1. 텔레그램 전송
def send_telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    if token and chat_id and len(text) > 0:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        except Exception as e:
            print(f"전송 실패: {e}")

# 2. 브라우저 세팅 (강력한 스텔스 모드)
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 화면 없이 실행
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # [중요] 창 크기를 크게 설정해야 데이터가 모바일 버전으로 축소되지 않음
    chrome_options.add_argument("--window-size=1920,1080")
    
    # [중요] 봇 탐지 방지 옵션 추가
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # navigator.webdriver 플래그 제거 (봇 아님을 증명)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

# 3. 네이버 시청률 크롤링
def fetch_naver_ratings(driver, category):
    query = f"{category} 드라마 시청률"
    url = f"https://search.naver.com/search.naver?where=nexearch&sm=tab_etc&query={query}"
    
    print(f"[{category}] 접속 중...")
    driver.get(url)
    
    try:
        # 대기 시간 5초 -> 15초로 연장 (GitHub 서버가 느릴 수 있음)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "rating_list"))
        )
        time.sleep(2) # 렌더링 안정화 대기
    except:
        print(f"[{category}] ⚠️ 데이터 로딩 실패 (화면 구조가 다르거나 차단됨)")
        # 디버깅: 현재 페이지 제목 출력
        print(f"현재 페이지 제목: {driver.title}")
        return []

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    results = []
    
    # 리스트 파싱
    rows = soup.select("div.rating_list > ul > li")
    
    for row in rows[:10]:
        try:
            rank = row.select_one(".rank").get_text(strip=True)
            title = row.select_one(".proc_tit, .title").get_text(strip=True)
            
            # 방송사
            channel = ""
            sub = row.select_one(".sub_text")
            if sub:
                channel = f"({sub.get_text(strip=True)})"
            
            # 시청률
            rating = row.select_one(".rating_val, .score").get_text(strip=True)
            
            # 변동폭
            change = "-"
            fluct = row.select_one(".fluctuation")
            if fluct:
                txt = fluct.get_text(strip=True)
                cls = str(fluct.get("class"))
                if "up" in cls: change = f"▲{txt}"
                elif "down" in cls: change = f"▼{txt}"
                elif "same" in cls: change = "-"
            
            # 한 줄 완성
            line = f"{rank}위 {title} | {channel} | {rating} | {change}"
            results.append(line)
        except:
            continue
            
    return results

# 4. 메인 실행
def main():
    driver = get_driver()
    
    now = datetime.datetime.now()
    days = ["월", "화", "수", "목", "금", "토", "일"]
    # 봇이 실행되는 시점(오늘) 리포트
    date_str = now.strftime(f"%Y-%m-%d({days[now.weekday()]})")
    
    report = f"📺 {date_str} 드라마 시청률 랭킹\n━━━━━━━━━━━━━━━━━━\n\n"
    
    try:
        # 지상파
        report += "📡 지상파 (KBS/MBC/SBS)\n"
        items = fetch_naver_ratings(driver, "지상파")
        if items: report += "\n".join(items)
        else: report += "(집계 중 또는 방영작 없음)"
        report += "\n\n"
        
        # 종편
        report += "📡 종편 (JTBC/MBN/TV조선/채널A)\n"
        items = fetch_naver_ratings(driver, "종편")
        if items: report += "\n".join(items)
        else: report += "(집계 중 또는 방영작 없음)"
        report += "\n\n"
        
        # 케이블
        report += "📡 케이블 (tvN/ENA)\n"
        items = fetch_naver_ratings(driver, "케이블")
        if items: report += "\n".join(items)
        else: report += "(집계 중 또는 방영작 없음)"
        report += "\n\n"
        
        report += "🔗 상세정보: 네이버 시청률 검색"
        
        send_telegram(report)
        
    except Exception as e:
        print(f"전체 에러: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
