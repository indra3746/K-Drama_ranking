import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback # 에러 추적용

# 1. 텔레그램 전송 함수
def send_telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    if token and chat_id and len(text) > 0:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        except Exception as e:
            print(f"전송 실패: {e}")

# ==========================================
# [사용자 설정 구역]
# 1. 봇이 자꾸 드라마를 지워버리면 여기에 제목을 추가하세요. (무조건 포함됨)
# 띄어쓰기 없이 적어도 됩니다.
FORCE_INCLUDE = [
    "결혼하자맹꽁아", "친절한선주씨", "스캔들", "심장을훔친게임", 
    "용감무쌍용수정", "세번째결혼", "우아한제국", "나의해리에게", 
    "조립식가족", "이혼숙려캠프"
]

# 2. 드라마가 아닌데 자꾸 나오면 단어를 추가하세요. (무조건 제외됨)
EXCLUDE_KEYWORDS = [
    "뉴스", "News", "스포츠", "야구", "베이스볼", "투데이", "모닝", "인간극장", "아침마당", 
    "생활의달인", "가요무대", "노래자랑", "동물농장", "서프라이즈", "미운우리새끼", 
    "나혼자산다", "런닝맨", "1박2일", "복면가왕", "불후의명곡", "슈퍼맨", "골때리는", 
    "라디오스타", "아는형님", "동치미", "썰전", "탐사", "PD수첩", "그것이", 
    "특파원", "시사", "토론", "다큐", "이슈", "사건", "반장", "특선", "영화", 
    "컬투쇼", "개그", "코미디", "트롯", "현역가왕", "불타는", "뭉쳐야", "한블리",
    "유퀴즈", "동상이몽", "살림남", "사장님", "최강야구", "신랑수업", "금쪽",
    "6시내고향", "고향", "생생", "정보", "틈만나면", "전지적", "구해줘", "홈즈",
    "스페셜", "재방송", "베스트", "하이라이트", "TV동물농장"
]
# ==========================================

def clean_and_check_title(raw_title):
    # 1단계: 괄호 추출 로직 (닐슨 데이터 정제)
    # "일일드라마(결혼하자맹꽁아)" -> "결혼하자맹꽁아"
    match = re.search(r'\((.*?)\)', raw_title)
    
    final_title = raw_title
    if match:
        content = match.group(1).strip()
        if len(content) > 1:
            final_title = content
    else:
        final_title = raw_title.strip()
    
    # 공백 제거한 타이틀 (비교용)
    clean_title_nospace = final_title.replace(" ", "")

    # [안전장치 1] 강제 포함 리스트 확인 (Whitelist)
    # 여기에 있으면 블랙리스트 검사 없이 바로 통과!
    for force in FORCE_INCLUDE:
        if force.replace(" ", "") in clean_title_nospace:
            print(f"   ✨ 강제 포함됨: {final_title}")
            return final_title

    # [안전장치 2] 블랙리스트 필터링
    for kw in EXCLUDE_KEYWORDS:
        if kw in clean_title_nospace or kw in raw_title.replace(" ", ""):
            print(f"   🗑️ 제외됨: {final_title} (키워드: {kw})")
            return None # 제외

    return final_title

# 3. 닐슨코리아 파싱
def fetch_nielsen_ratings(url, type_name):
    print(f"[{type_name}] 데이터 수집 시작: {url}")
    # [중요] 헤더를 보강하여 차단을 방지함
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    try:
        # 타임아웃을 30초로 늘림 (서버가 느릴 때 대비)
        res = requests.get(url, headers=headers, timeout=30)
        res.encoding = 'euc-kr' # 인코딩 고정
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            print(f"⚠️ [{type_name}] 테이블 없음 (IP 차단 가능성)")
            return []
            
        rows = table.find_all("tr")
        print(f"   ℹ️ {len(rows)}개 행 발견")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue 
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 제목 검증
                clean_title = clean_and_check_title(raw_title)
                
                if clean_title:
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
            except Exception as e:
                print(f"   ⚠️ 파싱 에러: {e}")
                continue
            
        return results
        
    except Exception as e:
        print(f"[{type_name}] 접속 에러: {e}")
        raise e # 메인으로 에러를 던짐

# 4. 메인 실행 (안전장치 포함)
def main():
    try:
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
        
        # 3. 데이터 정렬 및 분리
        data_t.sort(key=lambda x: x['rating_val'], reverse=True)
        
        jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
        list_j = []
        list_c = []
        
        for item in data_c:
            ch_upper = item['channel'].upper().replace(" ", "")
            if any(j in ch_upper for j in jongpyeon_chs):
                list_j.append(item)
            else:
                list_c.append(item)
        
        list_j.sort(key=lambda x: x['rating_val'], reverse=True)
        list_c.sort(key=lambda x: x['rating_val'], reverse=True)
                
        # 4. 리포트 작성
        report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
        
        def add_section(title, data_list):
            txt = f"📡 {title}\n"
            if data_list:
                for i, item in enumerate(data_list[:5]):
                    txt += f" {i+1}위 {item['title']} | ({item['channel']}) | {item['rating']}\n"
            else:
                txt += "(결방 또는 데이터 없음)\n"
            return txt + "\n"

        report += add_section("지상파", data_t)
        report += add_section("종편", list_j)
        report += add_section("케이블", list_c)
        
        report += "🔗 정보: 닐슨코리아"
        
        send_telegram(report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        # [핵심] 프로그램이 죽기 전에 에러 내용을 텔레그램으로 보냄
        err_msg = traceback.format_exc()
        print(f"🔥 치명적 오류 발생:\n{err_msg}")
        send_telegram(f"🚨 봇 실행 중 오류 발생!\n\n{str(e)}")

if __name__ == "__main__":
    main()
