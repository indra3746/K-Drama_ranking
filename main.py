import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback
import time
import gzip
import io
from difflib import SequenceMatcher

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

# 유사도 계산
def get_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

# 정규화
def normalize(text):
    if not text: return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', text)

# 제목 정제
def clean_title_text(text):
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'<.*?>', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()

# 닐슨 응답 복구
def get_decoded_html(response):
    content = response.content
    if len(content) > 2 and content[:2] == b'\x1f\x8b':
        try:
            buf = io.BytesIO(content)
            with gzip.GzipFile(fileobj=buf) as f:
                content = f.read()
        except: pass
    try:
        return content.decode('cp949')
    except:
        try:
            return content.decode('euc-kr')
        except:
            return content.decode('utf-8', 'ignore')

# [핵심 업그레이드] 위키백과에서 '요일 정보'까지 같이 긁어옴
def get_wiki_drama_db():
    print("📋 위키백과 드라마 DB(요일 포함) 구축 중...")
    
    # 구조: {'드라마제목정규화': [0, 1]}  (0=월, 1=화 ...)
    drama_schedule = {}
    
    # 1. 수동 리스트 (요일을 모르면 빈 리스트 [])
    # 필요한 경우 여기에 특정 드라마 요일을 지정할 수도 있음
    manual_list = [
        "결혼하자맹꽁아", "친절한선주씨", "스캔들", "심장을훔친게임", 
        "나의해리에게", "조립식가족", "이혼숙려캠프", "보물섬", 
        "모텔캘리포니아", "러브미", "스프링피버", "아이돌아이",
        "용감무쌍용수정", "세번째결혼", "우아한제국", "은애하는도적님아",
        "첫번째남자", "친밀한리플리", "화려한날들", "판사이한영",
        "마리와별난아빠들", "굿보이", "넉오프", "트리거", "하이퍼나이프"
    ]
    for m in manual_list:
        drama_schedule[normalize(m)] = [] # 요일 모름 (태그에만 의존)
    
    urls = [
        "https://ko.wikipedia.org/wiki/2025년_대한민국의_텔레비전_드라마_목록",
        "https://ko.wikipedia.org/wiki/2026년_대한민국의_텔레비전_드라마_목록"
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # [Smart Parsing] 헤더(요일)와 테이블을 순서대로 읽음
            elements = soup.find_all(['h2', 'h3', 'h4', 'table'])
            current_days = [] # 현재 읽고 있는 섹션의 요일
            
            for el in elements:
                # 1) 헤더에서 요일 감지
                if el.name in ['h2', 'h3', 'h4']:
                    text = el.get_text()
                    if "월화" in text: current_days = [0, 1] # 월, 화
                    elif "수목" in text: current_days = [2, 3] # 수, 목
                    elif "금토" in text: current_days = [4, 5] # 금, 토
                    elif "주말" in text or "토일" in text: current_days = [5, 6] # 토, 일
                    elif "일일" in text: current_days = [0, 1, 2, 3, 4] # 월~금
                    else: pass # 기타 섹션은 요일 유지 혹은 초기화 (여기선 유지)
                
                # 2) 테이블에서 제목 추출 후 현재 요일 할당
                elif el.name == 'table' and 'wikitable' in el.get('class', []):
                    rows = el.select("tr")
                    for row in rows:
                        cols = row.select("td")
                        for col in cols[:3]: # 앞쪽 컬럼에서 제목 찾기
                            targets = col.find_all(['i', 'a'])
                            for t in targets:
                                text = t.get_text(strip=True)
                                if len(text) > 1 and "드라마" not in text:
                                    norm_title = normalize(text)
                                    # 이미 수동으로 넣은 건 덮어쓰지 않음 (혹은 덮어써서 요일 업데이트)
                                    if norm_title not in drama_schedule or not drama_schedule[norm_title]:
                                        drama_schedule[norm_title] = current_days
        except: pass

    print(f"✅ 비교군 확보 완료: {len(drama_schedule)}개")
    return drama_schedule

# 3. 닐슨코리아 데이터 수집
def fetch_nielsen_data(session, url, type_name):
    print(f"[{type_name}] 접속: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    try:
        res = session.get(url, headers=headers, timeout=20)
        html_content = get_decoded_html(res) 
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table: return []
            
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                if "시청률" in rating or "프로그램" in raw_title: continue
                
                try: rating_val = float(rating.replace("%", "").strip())
                except: rating_val = 0.0
                
                results.append({
                    "channel": channel,
                    "title": raw_title,
                    "rating": rating,
                    "rating_val": rating_val
                })
            except: continue
        return results
    except: return []

# 4. 필터링 로직 (요일 체크 추가)
def filter_dramas(nielsen_data, wiki_db, yesterday_weekday):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        
        # 1. 재방송 여부 판단 (우선순위: 태그 > 요일 불일치)
        is_rerun = False
        
        # A. 태그 체크
        if "<재>" in raw_title or "(재)" in raw_title:
            is_rerun = True
            
        # 매칭용 정제
        match = re.search(r'\((.*?)\)', raw_title)
        extracted = match.group(1).strip() if match else raw_title
        extracted = re.sub(r'<.*?>', '', extracted)
        target_name = normalize(extracted)
        
        # B. 유사도 매칭 및 스케줄 확인
        is_match = False
        best_score = 0.0
        matched_wiki_days = [] # 매칭된 드라마의 방영 요일
        
        for db_title, days in wiki_db.items():
            score = get_similarity(target_name, db_title)
            if score > best_score:
                best_score = score
                matched_wiki_days = days
        
        if best_score >= 0.6:
            is_match = True
            
        # 키워드 보완
        if not is_match and any(k in raw_title for k in ["드라마", "미니시리즈", "연속극"]):
            is_match = True

        # [핵심] 요일 불일치 체크
        # 태그가 없었더라도, 위키에 등록된 요일과 어제 요일이 다르면 재방송 취급
        # (단, 요일 정보가 비어있으면 판단 안 함)
        if is_match and not is_rerun and matched_wiki_days:
            if yesterday_weekday not in matched_wiki_days:
                is_rerun = True
                # print(f"   💡 재방송 감지(요일다름): {raw_title} (어제:{yesterday_weekday} vs 방송:{matched_wiki_days})")

        if is_match:
            display_title = clean_title_text(raw_title)
            if match: display_title = clean_title_text(match.group(1))
            
            # 재방송이면 앞에 표시
            if is_rerun:
                display_title = "(재) " + display_title.replace("(재)", "").strip()
            
            item['display_title'] = display_title
            item['is_verified'] = True
            filtered.append(item)
    
    filtered.sort(key=lambda x: x['rating_val'], reverse=True)
    return filtered

# 5. 메인 실행
def main():
    try:
        kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        yesterday = kst_now - datetime.timedelta(days=1)
        # 요일 숫자 (0:월, 1:화 ... 6:일)
        yesterday_weekday = yesterday.weekday()
        
        days_str = ["월", "화", "수", "목", "금", "토", "일"]
        date_str = yesterday.strftime(f"%Y-%m-%d({days_str[yesterday_weekday]})")
        
        print(f"--- 실행 시작 ({date_str} / 수도권) ---")
        
        # DB 구축 (요일 정보 포함)
        wiki_db = get_wiki_drama_db()
        
        session = requests.Session()
        
        # URL (수도권 area=01)
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01"
        url_j = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=2_1&area=01"
        url_c = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=3_1&area=01"
        
        # 수집 및 필터링 (yesterday_weekday 전달)
        final_t = filter_dramas(fetch_nielsen_data(session, url_t, "지상파"), wiki_db, yesterday_weekday)
        time.sleep(1)
        final_j = filter_dramas(fetch_nielsen_data(session, url_j, "종편"), wiki_db, yesterday_weekday)
        time.sleep(1)
        final_c = filter_dramas(fetch_nielsen_data(session, url_c, "케이블"), wiki_db, yesterday_weekday)
        
        # 리포트 작성
        report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 수도권 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
        
        def make_section(title, data):
            txt = f"📡 {title}\n"
            if data:
                for i, item in enumerate(data[:5]):
                    txt += f" {i+1}위 {item['display_title']} | ({item['channel']}) | {item['rating']}\n"
            else:
                txt += "(결방 또는 데이터 없음)\n"
            return txt + "\n"
        
        report += make_section("지상파", final_t)
        report += make_section("종편", final_j)
        report += make_section("케이블", final_c)
        
        report += "🔗 정보: 닐슨코리아\nhttps://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01"
        
        send_telegram(report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 에러: {err}")
        send_telegram(f"🚨 에러 발생: {e}")

if __name__ == "__main__":
    main()
