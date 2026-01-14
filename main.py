import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback
import time
from difflib import SequenceMatcher # [핵심] 유사도 비교 도구

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

# [핵심] 두 문자열의 유사도 계산 (0.0 ~ 1.0)
def get_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

# 문자열 정규화 (공백/특수문자 제거 후 비교용)
def normalize(text):
    if not text: return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', text)

# 2. 위키백과 DB 구축 (Whitelist)
def get_wiki_drama_list():
    print("📋 위키백과 드라마 DB 구축 중...")
    drama_set = set()
    
    # [비상용] 위키에 없어도 이건 꼭 챙겨라 (최신작)
    manual_list = [
        "결혼하자맹꽁아", "친절한선주씨", "스캔들", "심장을훔친게임", 
        "나의해리에게", "조립식가족", "이혼숙려캠프", "보물섬", 
        "모텔캘리포니아", "러브미", "스프링피버", "아이돌아이",
        "용감무쌍용수정", "세번째결혼", "우아한제국", "은애하는도적님아",
        "첫번째남자", "친밀한리플리", "화려한날들", "판사이한영"
    ]
    for m in manual_list:
        drama_set.add(normalize(m))
    
    # 위키백과 크롤링
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
                                drama_set.add(normalize(text))
        except: pass

    print(f"✅ 비교군(Whitelist) 확보 완료: {len(drama_set)}개")
    return list(drama_set) # 리스트로 변환하여 반환

# 3. 닐슨코리아 데이터 수집
def fetch_nielsen_data(session, url, type_name):
    print(f"[{type_name}] 닐슨 접속 시도: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Cache-Control': 'no-cache'
    }
    
    try:
        res = session.get(url, headers=headers, timeout=20)
        res.encoding = 'euc-kr' # 인코딩 고정
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            print(f"   ❌ [{type_name}] 테이블 못 찾음")
            return []
            
        rows = table.find_all("tr")
        print(f"   ℹ️ {len(rows)}행 데이터 발견")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
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

# 4. 필터링 로직 (유사도 기반 매칭)
def filter_dramas(nielsen_data, wiki_db):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        
        # 1. 괄호 추출: "일일드라마(결혼하자 맹꽁아)" -> "결혼하자 맹꽁아"
        match = re.search(r'\((.*?)\)', raw_title)
        extracted = match.group(1).strip() if match else raw_title
        
        # 비교를 위해 정규화
        target_name = normalize(extracted)
        
        is_match = False
        display_title = extracted
        
        # [유사도 매칭]
        # 위키 DB와 비교하여 가장 높은 유사도를 찾음
        best_score = 0.0
        
        for db_title in wiki_db:
            score = get_similarity(target_name, db_title)
            if score > best_score:
                best_score = score
        
        # 기준: 유사도가 0.6(60%) 이상이면 통과
        if best_score >= 0.6:
            is_match = True
            # print(f"   ✅ 매칭(유사도 {best_score:.2f}): {raw_title}")
        
        # [보완] 유사도가 낮아도 키워드가 있으면 통과
        if not is_match:
            if any(k in raw_title for k in ["드라마", "미니시리즈", "연속극"]):
                is_match = True

        if is_match:
            item['display_title'] = display_title
            item['is_verified'] = True
            filtered.append(item)
    
    # [안전장치] 만약 필터링 결과가 하나도 없다면? -> 상위 3개 강제 포함
    if not filtered and nielsen_data:
        print("   ⚠️ 필터링 결과 0개 -> 상위 3개 강제 출력")
        for item in nielsen_data[:3]:
            item['display_title'] = item['title'] + "(미검증)"
            item['is_verified'] = False
            filtered.append(item)

    # 시청률 내림차순 정렬
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
        
        wiki_db = get_wiki_drama_list()
        
        session = requests.Session()
        
        # 1. 지상파
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
        raw_t = fetch_nielsen_data(session, url_t, "지상파")
        final_t = filter_dramas(raw_t, wiki_db)
        
        time.sleep(3) # 대기
        
        # 2. 종편/케이블
        url_c = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
        raw_c = fetch_nielsen_data(session, url_c, "종편/케이블")
        final_c_all = filter_dramas(raw_c, wiki_db)
        
        # 3. 리포트 분류
        jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
        final_j = []
        final_c = []
        
        for item in final_c_all:
            ch_norm = normalize(item['channel']).upper()
            if any(normalize(j).upper() in ch_norm for j in jongpyeon_chs):
                final_j.append(item)
            else:
                final_c.append(item)
        
        final_j.sort(key=lambda x: x['rating_val'], reverse=True)
        final_c.sort(key=lambda x: x['rating_val'], reverse=True)
        
        # 4. 최종 메시지
        report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
        
        def make_section(title, data):
            txt = f"📡 {title}\n"
            if data:
                for i, item in enumerate(data[:5]):
                    mark = "" if item.get('is_verified') else "❓"
                    txt += f" {i+1}위 {mark}{item['display_title']} | ({item['channel']}) | {item['rating']}\n"
            else:
                txt += "(결방 또는 데이터 없음)\n"
            return txt + "\n"
        
        report += make_section("지상파", final_t)
        report += make_section("종편", final_j)
        report += make_section("케이블", final_c)
        
        report += "🔗 정보: 닐슨코리아 / 위키백과"
        
        send_telegram(report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 에러: {err}")
        send_telegram(f"🚨 에러 발생: {e}")

if __name__ == "__main__":
    main()
