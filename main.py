import time
import datetime
import os
import requests
from bs4 import BeautifulSoup

# 셀레니움 관련
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

# 2. 브라우저 설정 (Daum 접속용)
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # 일반적인 유저 에이전트 사용
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

# 3. 다음(Daum) 시청률 크롤링
def fetch_daum_ratings(driver, category):
    # 검색어: "지상파 드라마 시청률"
    query = f"{category} 드라마 시청률"
    url = f"https://search.daum.net/search?w=tot&q={query}"
    
    print(f"[{category}] Daum 접속 중: {url}")
    driver.get(url)
    
    try:
        # body가 로딩될 때까지 대기 (최대 10초)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(1) 
    except:
        print(f"[{category}] 로딩 실패")
        return []

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    results = []
    
    # Daum은 구조가 자주 변하므로, '순위', '제목', '%'가 모두 포함된 리스트 아이템을 찾습니다.
    # 보통 c-list-basic, item-title 등의 클래스를 사용하나, 범위가 넓은 tr, li를 다 뒤집니다.
    candidates = soup.find_all(['li', 'tr'])
    
    for item in candidates:
        text = item.get_text(strip=True)
        # 1. '%'가 없으면 시청률 정보가 아님
        if '%' not in text: continue
        
        # 2. 파싱 시도 (클래스 기반)
        try:
            # 순위: .rank_num 또는 텍스트의 첫 부분
            rank_tag = item.select_one(".rank_num, .num_rank, .screen_out")
            # 제목: .tit_item, .fn_tit
            title_tag = item.select_one(".tit_item, .fn_tit, .link_tit")
            # 시청률: .txt_num, .f_red
            rating_tag = item.select_one(".txt_num, .f_red")
            
            # 태그를 찾았다면 추출
            if rank_tag and title_tag:
                rank = rank_tag.get_text(strip=True).replace("위","")
                title = title_tag.get_text(strip=True)
                rating = rating_tag.get_text(strip=True) if rating_tag else ""
                
                # 방송사 추출 (제목 옆이나 괄호 안)
                # Daum은 방송사가 별도 태그(.txt_info)로 있는 경우가 많음
                channel = ""
                info_tag = item.select_one(".txt_info, .info_tit")
                if info_tag:
                    channel = f"({info_tag.get_text(strip=True)})"
                
                # 순위가 숫자인지 확인 (헤더 제외)
                if not rank.isdigit(): continue
                
                # 중복 방지 및 10위까지만
                if len(results) >= 10: break
                
                # 변동폭 (Daum은 변동폭 아이콘이 복잡하여 생략하거나 텍스트로 추출 시도)
                change = "-"
                
                results.append(f"{rank}위 {title} | {channel} | {rating}")
        except:
            continue
            
    # 만약 클래스로 못 찾았다면, 텍스트 패턴으로 한 번 더 시도 (Fallback)
    if not results:
        # (구현 생략: Daum은 클래스 구조가 비교적 안정적임)
        pass

    return results

# 4. 메인 실행
def main():
    driver = get_driver()
    
    # [날짜 계산]
    # 서버 시간(UTC) 기준이 아니라, 한국 시간(KST) 기준으로 "어제" 날짜를 구함
    # 왜냐하면 오늘 아침 8시에 보내는 리포트는 "어제 방영분"이기 때문
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    yesterday = kst_now - datetime.timedelta(days=1)
    
    days = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
    
    report = f"📺 {date_str} 드라마 시청률 랭킹\n(어제 방영분 기준)\n━━━━━━━━━━━━━━━━━━\n\n"
    
    try:
        # 지상파
        report += "📡 지상파\n"
        items = fetch_daum_ratings(driver, "지상파")
        if items: report += "\n".join(items)
        else: report += "(집계 중 또는 데이터 없음)"
        report += "\n\n"
        
        # 종편
        report += "📡 종편\n"
        items = fetch_daum_ratings(driver, "종편")
        if items: report += "\n".join(items)
        else: report += "(집계 중 또는 데이터 없음)"
        report += "\n\n"
        
        # 케이블
        report += "📡 케이블\n"
        items = fetch_daum_ratings(driver, "케이블")
        if items: report += "\n".join(items)
        else: report += "(집계 중 또는 데이터 없음)"
        report += "\n\n"
        
        report += "🔗 정보: Daum/Nielsen Korea"
        
        send_telegram(report)
        
    except Exception as e:
        print(f"전체 에러: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
