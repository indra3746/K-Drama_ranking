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
