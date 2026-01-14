import requests
from bs4 import BeautifulSoup
import datetime
import os
import re

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

# 2. 비드라마(뉴스, 예능, 교양) 필터링 키워드
# 닐슨 데이터에서 드라마만 남기기 위해 아래 단어가 포함되면 제외합니다.
EXCLUDE_KEYWORDS = [
    "뉴스", "News", "스포츠", "베이스볼", "투데이", "모닝와이드", "인간극장", "아침마당", 
    "생활의달인", "가요무대", "전국노래자랑", "동물농장", "서프라이즈", "미운우리새끼", 
    "나혼자산다", "런닝맨", "1박2일", "복면가왕", "불후의명곡", "슈퍼맨", "골때리는", 
    "라디오스타", "아는형님", "동치미", "썰전", "강적들", "탐사", "PD수첩", "그것이", 
    "특파원", "시사", "토론", "다큐", "이슈", "사건", "반장", "특선", "영화", 
    "컬투쇼", "개그", "코미디", "트롯", "현역가왕", "불타는", "뭉쳐야", "한블리"
]

def is_drama(title):
    # 1) 제외 키워드가 있는지 확인
    for kw in EXCLUDE_KEYWORDS:
        if kw in title.replace(" ", ""): # 띄어쓰기 무시하고 체크
            return False
    # 2) '드라마', '미니시리즈', '연속극' 단어가 있으면 무조건 포함
    if any(x in title for x in ["드라마", "시리즈", "연속극"]):
        return True
    return True # 기본적으로 통과 (화이트리스트 방식이 아니므로)

# 3. 닐슨코리아 파싱 함수
def fetch_nielsen_ratings(url, channel_type):
    print(f"[{channel_type}] 접속 중: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8' # 한글 깨짐 방지
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        # 닐슨코리아 테이블 구조 (ranking_tb)
        table = soup.find("table", class_="ranking_tb")
        if not table:
            return []
            
        rows = table.find_all("tr")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue # 데이터 행이 아님
            
            # 순위, 채널, 프로그램명, 시청률 추출
            # (닐슨 웹 구조: 등수 | 채널 | 프로그램 | 시청률 ...)
            try:
                rank = cols[0].get_text(strip=True)
                channel = cols[1].get_text(strip=True)
                title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 순위가 숫자가 아니면 패스 (헤더 등)
                if not rank.isdigit(): continue
                
                # [중요] 드라마 필터링
                if not is_drama(title): continue
                
                # 데이터 저장
                results.append({
                    "rank": rank,
                    "channel": channel,
                    "title": title,
                    "rating": rating
                })
            except: continue
            
        return results
        
    except Exception as e:
        print(f"파싱 에러: {e}")
        return []

# 4. 메인 실행
def main():
    # 어제 날짜 구하기 (닐슨은 기본적으로 어제 데이터를 보여줌)
    # 한국 시간 기준 계산
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    yesterday = kst_now - datetime.timedelta(days=1)
    
    days = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
    
    # 1. 지상파 데이터 가져오기
    terrestrial_url = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
    t_data = fetch_nielsen_ratings(terrestrial_url, "지상파")
    
    # 2. 종편/케이블 데이터 가져오기 (닐슨은 둘을 합쳐서 보여줌)
    cable_url = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
    c_data = fetch_nielsen_ratings(cable_url, "종편/케이블")
    
    # 3. 데이터 분류 (종편 vs 케이블)
    # 닐슨 케이블 리스트에서 종편 4사(JTBC, MBN, TV CHOSUN, CHANNEL A)를 분리
    jongpyeon_channels = ["JTBC", "MBN", "TV CHOSUN", "채널A", "TV조선"]
    
    jongpyeon_list = []
    cable_list = []
    
    for item in c_data:
        # 채널명 정리 (공백 제거 및 대문자)
        ch_norm = item['channel'].replace(" ", "").upper()
        
        is_jp = False
        for jp in jongpyeon_channels:
            if jp.replace(" ", "").upper() in ch_norm:
                is_jp = True
                break
        
        if is_jp:
            jongpyeon_list.append(item)
        else:
            cable_list.append(item)
            
    # 4. 리포트 작성
    report = f"📺 {date_str} 드라마 시청률 랭킹\n(어제 방영분 / 닐슨코리아)\n━━━━━━━━━━━━━━━━━━\n\n"
    
    # 지상파 출력 (Top 5)
    report += "📡 지상파 (KBS/MBC/SBS)\n"
    if t_data:
        count = 0
        for item in t_data:
            if count >= 5: break # 5위까지만
            # 포맷: 1위 제목 | (채널) | 12.8%
            report += f" {item['rank']}위 {item['title']} | ({item['channel']}) | {item['rating']}%\n"
            count += 1
    else:
        report += "(집계 중 또는 방영작 없음)\n"
    report += "\n"

    # 종편 출력 (Top 5)
    report += "📡 종편 (JTBC/MBN/TV조선/채널A)\n"
    if jongpyeon_list:
        count = 0
        for item in jongpyeon_list:
            if count >= 5: break
            report += f" {count+1}위 {item['title']} | ({item['channel']}) | {item['rating']}%\n"
            count += 1
    else:
        report += "(집계 중 또는 방영작 없음)\n"
    report += "\n"

    # 케이블 출력 (Top 5)
    report += "📡 케이블 (tvN/ENA/etc)\n"
    if cable_list:
        count = 0
        for item in cable_list:
            if count >= 5: break
            report += f" {count+1}위 {item['title']} | ({item['channel']}) | {item['rating']}%\n"
            count += 1
    else:
        report += "(집계 중 또는 방영작 없음)\n"
    report += "\n"
    
    report += "🔗 정보: 닐슨코리아 공식 홈페이지"
    
    send_telegram(report)

if __name__ == "__main__":
    main()
