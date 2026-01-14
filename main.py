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

# 2. 제외 키워드 (블랙리스트) - 드라마가 아닌 것들
EXCLUDE_KEYWORDS = [
    "뉴스", "News", "스포츠", "야구", "베이스볼", "투데이", "모닝", "인간극장", "아침마당", 
    "생활의달인", "가요무대", "노래자랑", "동물농장", "서프라이즈", "미운우리새끼", 
    "나혼자산다", "런닝맨", "1박2일", "복면가왕", "불후의명곡", "슈퍼맨", "골때리는", 
    "라디오스타", "아는형님", "동치미", "썰전", "탐사", "PD수첩", "그것이", 
    "특파원", "시사", "토론", "다큐", "이슈", "사건", "반장", "특선", "영화", 
    "컬투쇼", "개그", "코미디", "트롯", "현역가왕", "불타는", "뭉쳐야", "한블리",
    "유퀴즈", "동상이몽", "살림남", "사장님", "최강야구", "신랑수업", "금쪽",
    "6시내고향", "고향", "생생", "정보", "틈만나면", "전지적", "구해줘", "홈즈",
    "스페셜", "재방송", "베스트", "하이라이트"
]

def clean_and_check_title(raw_title):
    # 1단계: 괄호 추출 로직 (가장 강력함)
    # 예: "일일드라마(결혼하자맹꽁아)" -> "결혼하자맹꽁아" 추출
    # 닐슨에서 드라마는 주로 괄호를 달고 나옵니다.
    match = re.search(r'\((.*?)\)', raw_title)
    
    final_title = raw_title
    is_likely_drama = False
    
    if match:
        content = match.group(1).strip()
        # 괄호 안 내용이 너무 짧거나(1글자), '재', '회' 같은 건 제외
        if len(content) > 1:
            final_title = content
            is_likely_drama = True # 괄호 안에 제목이 있으면 드라마일 확률 높음
    else:
        # 괄호가 없으면 원래 제목 사용
        final_title = raw_title.strip()

    # 2단계: 블랙리스트 필터링
    # 드라마일 확률이 높더라도, 블랙리스트 단어가 포함되어 있으면 탈락
    # (예: "주말뉴스(심층)")
    for kw in EXCLUDE_KEYWORDS:
        if kw in final_title.replace(" ", "") or kw in raw_title.replace(" ", ""):
            return None # 버림

    # 3단계: 최종 승인
    # 괄호가 있었거나, 블랙리스트에 안 걸렸으면 통과
    return final_title

# 3. 닐슨코리아 파싱
def fetch_nielsen_ratings(url, type_name):
    print(f"[{type_name}] 데이터 수집 시작: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        # [중요] 닐슨코리아 인코딩 고정
        res.encoding = 'euc-kr'
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            return []
            
        rows = table.find_all("tr")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue 
            
            try:
                # 닐슨 컬럼 구조: 순위 | 채널 | 프로그램명 | 시청률
                # rank = cols[0].get_text(strip=True) # 순위는 나중에 다시 매김
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 제목 정제 및 필터링
                clean_title = clean_and_check_title(raw_title)
                
                if clean_title:
                    # 시청률 숫자 변환 (정렬용)
                    try:
                        rating_val = float(rating.replace("%", "").strip())
                    except:
                        rating_val = 0.0
                        
                    results.append({
                        "channel": channel,
                        "title": clean_title,
                        "rating": rating,
                        "rating_val": rating_val
                    })
            except: continue
            
        return results
        
    except Exception as e:
        print(f"[{type_name}] 에러: {e}")
        return []

# 4. 메인 실행
def main():
    # 어제 날짜 계산
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    yesterday = kst_now - datetime.timedelta(days=1)
    days = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
    
    print(f"--- 실행 시작 ({date_str} 기준) ---")
    
    # 1. 지상파
    url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
    data_t = fetch_nielsen_ratings(url_t, "지상파")
    
    # 2. 종편/케이블
    url_c = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
    data_c = fetch_nielsen_ratings(url_c, "종편/케이블")
    
    # 3. 데이터 분리 및 정렬
    # 지상파 정렬
    data_t.sort(key=lambda x: x['rating_val'], reverse=True)
    
    # 종편/케이블 분리
    jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
    list_j = []
    list_c = []
    
    for item in data_c:
        ch_upper = item['channel'].upper().replace(" ", "")
        if any(j in ch_upper for j in jongpyeon_chs):
            list_j.append(item)
        else:
            list_c.append(item)
    
    # 각각 정렬
    list_j.sort(key=lambda x: x['rating_val'], reverse=True)
    list_c.sort(key=lambda x: x['rating_val'], reverse=True)
            
    # 4. 리포트 작성
    report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
    
    # 지상파
    report += "📡 지상파\n"
    if data_t:
        for i, item in enumerate(data_t[:5]): # 5위까지
            report += f" {i+1}위 {item['title']} | ({item['channel']}) | {item['rating']}\n"
