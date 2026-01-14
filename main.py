import requests
from bs4 import BeautifulSoup
import datetime
import os

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
# 닐슨 데이터에는 장르 구분이 없어서 제목으로 걸러내야 함
EXCLUDE_KEYWORDS = [
    "뉴스", "News", "스포츠", "베이스볼", "투데이", "모닝", "인간극장", "아침마당", 
    "생활의달인", "가요무대", "노래자랑", "동물농장", "서프라이즈", "미운우리새끼", 
    "나혼자산다", "런닝맨", "1박2일", "복면가왕", "불후의명곡", "슈퍼맨", "골때리는", 
    "라디오스타", "아는형님", "동치미", "썰전", "탐사", "PD수첩", "그것이", 
    "특파원", "시사", "토론", "다큐", "이슈", "사건", "반장", "특선", "영화", 
    "컬투쇼", "개그", "코미디", "트롯", "현역가왕", "불타는", "뭉쳐야", "한블리",
    "유퀴즈", "동상이몽", "살림남", "사장님", "최강야구", "신랑수업"
]

def is_drama(title):
    clean_title = title.replace(" ", "")
    # 1) 제외 키워드가 있는지 확인
    for kw in EXCLUDE_KEYWORDS:
        if kw in clean_title:
            return False
    # 2) 예외적으로 포함할 드라마 키워드 (혹시 필터에 걸릴까봐)
    if any(x in title for x in ["드라마", "시리즈", "연속극"]):
        return True
    return True

# 3. 닐슨코리아 파싱 함수
def fetch_nielsen_ratings(url):
    print(f"접속 중: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8' # 한글 깨짐 방지
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        # 닐슨코리아 테이블 찾기
        table = soup.find("table", class_="ranking_tb")
        if not table:
            return []
            
        rows = table.find_all("tr")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue 
            
            try:
                rank = cols[0].get_text(strip=True)
                channel = cols[1].get_text(strip=True)
                title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 헤더 제외
                if not rank.isdigit(): continue
                
                # 드라마만 남기기
                if not is_drama(title): continue
                
                results.append({
                    "rank": rank,
                    "channel": channel,
                    "title": title,
                    "rating": rating
                })
            except: continue
            
        return results
        
    except Exception as e:
        print(f"에러: {e}")
        return []

# 4. 메인 실행
def main():
    # 날짜 계산 (한국 시간 기준 어제)
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    yesterday = kst_now - datetime.timedelta(days=1)
    
    days = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
    
    # 1. 지상파 URL
    url_terrestrial = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
    data_t = fetch_nielsen_ratings(url_terrestrial)
    
    # 2. 종편/케이블 URL
    url_cable = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
    data_c = fetch_nielsen_ratings(url_cable)
    
    # 종편 채널 분류
    jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
    list_j = []
    list_c = []
    
    for item in data_c:
        # 채널명에 종편 이름이 포함되어 있는지 확인
        if any(j in item['channel'].upper() for j in jongpyeon_chs):
            list_j.append(item)
        else:
            list_c.append(item)
            
    # 3. 리포트 작성
    report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
    
    # 지상파
    report += "📡 지상파 (Top 5)\n"
    if data_t:
        for item in data_t[:5]:
            report += f" {item['rank']}위 {item['title']} | ({item['channel']}) | {item['rating']}%\n"
    else:
        report += "(데이터 없음)\n"
    report += "\n"

    # 종편
    report += "📡 종편 (Top 5)\n"
    if list_j:
        for i, item in enumerate(list_j[:5]):
            report += f" {i+1}위 {item['title']} | ({item['channel']}) | {item['rating']}%\n"
    else:
        report += "(데이터 없음)\n"
    report += "\n"
    
    # 케이블
    report += "📡 케이블 (Top 5)\n"
    if list_c:
        for i, item in enumerate(list_c[:5]):
            report += f" {i+1}위 {item['title']} | ({item['channel']}) | {item['rating']}%\n"
    else:
        report += "(데이터 없음)\n"
    report += "\n"
    
    report += "🔗 정보: 닐슨코리아 공식 홈페이지"
    
    send_telegram(report)

if __name__ == "__main__":
    main()
