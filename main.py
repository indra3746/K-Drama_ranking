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

# [핵심] 위키백과 DB + 수동 요일 정보
def get_wiki_drama_db():
    print("📋 드라마 DB 구축 중...")
    
    # 0:월, 1:화, 2:수, 3:목, 4:금, 5:토, 6:일
    # [수동 지정 리스트] 여기에 요일을 확실히 박아둡니다.
    manual_schedule = {
        "결혼하자맹꽁아": [0, 1, 2, 3, 4], # 일일
        "친절한선주씨": [0, 1, 2, 3, 4],   # 일일
        "스캔들": [0, 1, 2, 3, 4],       # 일일
        "심장을훔친게임": [0, 1, 2, 3, 4], # 일일
        "용감무쌍용수정": [0, 1, 2, 3, 4], # 일일
        "세번째결혼": [0, 1, 2, 3, 4],     # 일일
        
        "나의해리에게": [0, 1], # 월화
        "조립식가족": [2],      # 수요
        "이혼숙려캠프": [3],    # 목요
        "보물섬": [4, 5],       # 금토
        "모텔캘리포니아": [4, 5], # 금토
        "러브미": [5, 6],       # 토일
        
        # 요청하신 케이블 드라마 (월화)
        "스프링피버": [0, 1],   
        "아이돌아이": [0, 1],
        
        "마리와별난아빠들": [0, 1, 2, 3, 4],
        "친밀한리플리": [0, 1, 2, 3, 4],
        "첫번째남자": [0, 1, 2, 3, 4],
        "굿보이": [5, 6],
        "트리거": [5, 6]
    }

    # 정규화된 키로 변환
    drama_schedule = {normalize(k): v for k, v in manual_schedule.items()}
    
    # 위키백과 크롤링 (보조 수단)
    urls = [
        "https://ko.wikipedia.org/wiki/2025년_대한민국의_텔레비전_드라마_목록",
        "https://ko.wikipedia.org/wiki/2026년_대한민국의_텔레비전_드라마_목록"
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            tables = soup.select("table.wikitable")
            for table in tables:
                rows = table.select("tr")
                for row in rows:
                    cols = row.select("td")
                    for col in cols[:3]:
                        targets = col.find_all(['i', 'a'])
                        for t in targets:
                            text = t.get_text(strip=True)
                            if len(text) > 1 and "드라마" not in text:
                                norm_title = normalize(text)
                                # 수동 리스트에 없으면 요일 정보 없이 추가 (이름만 등록)
                                if norm_title not in drama_schedule:
                                    drama_schedule[norm_title] = [] 
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

# 4. 필터링 로직 (요일 체크 강화)
def filter_dramas(nielsen_data, wiki_db, yesterday_weekday):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        
        # 1. 태그로 1차 확인
        is_rerun = False
        if "<재>" in raw_title or "(재)" in raw_title:
            is_rerun = True
            
        # 매칭용 정제
        match = re.search(r'\((.*?)\)', raw_title)
        extracted = match.group(1).strip() if match else raw_title
        extracted = re.sub(r'<.*?>', '', extracted)
        target_name = normalize(extracted)
        
        # 2. 유사도 매칭
        is_match = False
        best_score = 0.0
        matched_days = []
        
        for db_title, days in wiki_db.items():
            score = get_similarity(target_name, db_title)
            if score > best_score:
                best_score = score
                matched_days = days
        
        if best_score >= 0.6:
            is_match = True
            
        # 키워드 보완
        if not is_match and any(k in raw_title for k in ["드라마", "미니시리즈", "연속극"]):
            is_match = True

        # [핵심] 요일 불일치 = 재방송
        # 매칭된 드라마의 방영 요일 정보가 있고(빈 리스트 아님),
        # 어제 요일이 그 리스트에 없다면 -> 재방송
        if is_match and not is_rerun and matched_days:
            if yesterday_weekday not in matched_days:
                is_rerun = True
                print(f"   💡 재방송 감지: {raw_title} (어제:{yesterday_weekday} vs 방송:{matched_days})")

        if is_match:
            display_title = clean_title_text(raw_title)
            if match: display_title = clean_title_text(match.group(1))
            
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
        yesterday_weekday = yesterday.weekday() # 0:월 ~ 6:일
        
        days_str = ["월", "화", "수", "목", "금", "토", "일"]
        date_str = yesterday.strftime(f"%Y-%m-%d({days_str[yesterday_weekday]})")
        
        print(f"--- 실행 시작 ({date_str} / 수도권) ---")
        
        wiki_db = get_wiki_drama_db()
        
        session = requests.Session()
        
        # URL (수도권 area=01)
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01"
        url_j = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=2_1&area=01"
        url_c = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=3_1&area=01"
        
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
