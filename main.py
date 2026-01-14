import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback
import time

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

# ==========================================
# [안전장치] 위키백과에 없을 경우를 대비한 수동 리스트 (인기작 위주)
MUST_INCLUDE = [
    "결혼하자맹꽁아", "친절한선주씨", "스캔들", "심장을훔친게임", 
    "용감무쌍용수정", "세번째결혼", "우아한제국", "나의해리에게", 
    "조립식가족", "이혼숙려캠프", "보물섬", "모텔캘리포니아", 
    "언더커버하이스쿨", "협상의기술", "러브미", "스프링피버", "아이돌아이"
]
# ==========================================

# 문자열 정규화 (모든 공백, 특수문자 제거)
def normalize(text):
    if not text: return ""
    # 한글, 영문, 숫자만 남기고 다 날림
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', text)

# 2. 위키백과 DB 구축
def get_wiki_drama_list():
    print("📋 위키백과 드라마 DB 구축 중...")
    drama_set = set()
    
    # 안전장치 먼저 등록
    for d in MUST_INCLUDE:
        drama_set.add(normalize(d))
    
    urls = [
        "https://ko.wikipedia.org/wiki/2025년_대한민국의_텔레비전_드라마_목록",
        "https://ko.wikipedia.org/wiki/2026년_대한민국의_텔레비전_드라마_목록"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
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
                        # i 태그 또는 a 태그 안의 텍스트 추출
                        targets = col.find_all(['i', 'a'])
                        for t in targets:
                            text = t.get_text(strip=True)
                            if len(text) > 1 and "드라마" not in text:
                                drama_set.add(normalize(text))
            time.sleep(1)
        except Exception as e:
            print(f"   ⚠️ 위키 접속 실패: {e}")
            
    print(f"✅ 비교군(Whitelist) 확보 완료: 총 {len(drama_set)}개 드라마")
    return drama_set

# 3. 닐슨코리아 데이터 수집
def fetch_nielsen_data(url, type_name):
    print(f"[{type_name}] 닐슨 접속 시도: {url}")
    
    # [중요] 매번 새로운 헤더 사용 (세션 꼬임 방지)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Cache-Control': 'no-cache'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=20)
        res.encoding = 'euc-kr' 
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            print(f"   ❌ [{type_name}] 테이블 못 찾음 (차단 또는 로딩 실패)")
            # 디버깅용: HTML 일부 출력
            print(f"   📄 HTML 내용 일부: {res.text[:200]}")
            return []
            
        rows = table.find_all("tr")
        print(f"   ℹ️ {len(rows)}행 데이터 발견. 매칭 시작...")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 시청률 숫자 변환
                try:
                    rating_val = float(rating.replace("%", "").strip())
                except:
                    rating_val = 0.0
                
                results.append({
                    "channel": channel,
                    "title": raw_title,
                    "rating": rating,
                    "rating_val": rating_val
                })
            except: continue
            
        return results
        
    except Exception as e:
        print(f"   ❌ [{type_name}] 접속 에러: {e}")
        return []

# 4. 필터링 로직 (핵심 수정: 정규화 비교)
def filter_dramas(nielsen_data, wiki_db):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        
        # 1. 괄호 안의 내용 추출 (닐슨 데이터 정제)
        # 예: "일일드라마(결혼하자 맹꽁아)" -> "결혼하자 맹꽁아"
        match = re.search(r'\((.*?)\)', raw_title)
        extracted = match.group(1).strip() if match else raw_title
        
        # 2. 정규화 (띄어쓰기 제거)
        norm_raw = normalize(raw_title)
        norm_ext = normalize(extracted)
        
        is_match = False
        display_title = extracted # 기본 표시 제목
        
        # 매칭 시도 1: 괄호 안 내용이 DB에 있는가?
        if norm_ext in wiki_db:
            is_match = True
            
        # 매칭 시도 2: 원본 제목이 DB에 포함되는가?
        if not is_match:
            for db_title in wiki_db:
                if db_title in norm_raw and len(db_title) > 2:
                    is_match = True
                    display_title = raw_title # 원본 사용
                    break
        
        # 매칭 시도 3: '드라마', '미니시리즈' 키워드 포함 시 무조건 통과 (신작 대비)
        if not is_match:
            if any(k in norm_raw for k in ["드라마", "미니시리즈", "연속극"]):
                is_match = True
                
        if is_match:
            # 로그 출력 (무엇이 매칭되었는지 확인)
            print(f"      ✅ 매칭 성공: {raw_title} -> {display_title}")
            item['display_title'] = display_title
            filtered.append(item)
        else:
            # 매칭 실패 로그 (왜 안 나왔는지 확인용)
            # 너무 많으면 주석 처리하세요
            # print(f"      🗑️ 제외됨: {raw_title}")
            pass
            
    filtered.sort(key=lambda x: x['rating_val'], reverse=True)
    return filtered

# 5. 메인 실행
def main():
    try:
        kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        yesterday = kst_now - datetime.timedelta(days=1)
        days = ["월", "화", "수", "목", "금", "토", "일"]
        date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
        
        print(f"--- 실행 시작 ({date_str} 기준) ---")
        
        # 1. 위키백과 DB
        wiki_db = get_wiki_drama_list()
        
        # 2. 지상파 수집
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
        raw_t = fetch_nielsen_data(url_t, "지상파")
        final_t = filter_dramas(raw_t, wiki_db)
        
        print("⏳ 케이블 수집을 위해 5초 대기 (서버 부하 방지)...")
        time.sleep(5) # [중요] 딜레이 추가
        
        # 3. 종편/케이블 수집
        url_c = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
        raw_c = fetch_nielsen_data(url_c, "종편/케이블")
        final_c_all = filter_dramas(raw_c, wiki_db)
        
        # 4. 종편/케이블 분리
        jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
        final_j = []
        final_c = []
        
        for item in final_c_all:
            ch_upper = normalize(item['channel']).upper()
            if any(normalize(j).upper() in ch_upper for j in jongpyeon_chs):
                final_j.append(item)
            else:
                final_c.append(item)
        
        final_j.sort(key=lambda x: x['rating_val'], reverse=True)
        final_c.sort(key=lambda x: x['rating_val'], reverse=True)
        
        # 5. 리포트 작성
        report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
        
        def make_section(title, data):
            txt = f"📡 {title}\n"
            if data:
                for i, item in enumerate(data[:5]):
                    txt += f" {i+1}위 {item['display_title']} | ({item['channel']}) | {item['rating']}\n"
            else:
                txt += "(결방 또는 데이터 없음)\n"
            return txt + "\n"
        
        report += make_section("지상파 (Top 5)", final_t)
        report += make_section("종편 (Top 5)", final_j)
        report += make_section("케이블 (Top 5)", final_c)
        
        report += "🔗 정보: 닐슨코리아 / 위키백과"
        
        send_telegram(report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 에러 발생:\n{err}")
        send_telegram(f"🚨 봇 에러:\n{str(e)}")

if __name__ == "__main__":
    main()
