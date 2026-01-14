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

# 정규화 (비교용: 공백/특수문자 제거)
def normalize(text):
    if not text: return ""
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', text)

# 제목 정제 (표시용: 괄호 및 태그 제거)
def clean_title_text(text):
    # (일일연속극) 같은 괄호 제거
    text = re.sub(r'\(.*?\)', '', text)
    # <본>, <재> 같은 꺾쇠 괄호 제거
    text = re.sub(r'<.*?>', '', text)
    # 대괄호 제거
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()

# [핵심] 닐슨 서버 응답 복구 (압축해제 + 인코딩)
def get_decoded_html(response):
    content = response.content
    
    # GZIP 매직 넘버 확인
    if len(content) > 2 and content[:2] == b'\x1f\x8b':
        try:
            buf = io.BytesIO(content)
            with gzip.GzipFile(fileobj=buf) as f:
                content = f.read()
        except: pass
            
    # 한글 디코딩 (CP949 > EUC-KR)
    try:
        return content.decode('cp949')
    except:
        try:
            return content.decode('euc-kr')
        except:
            return content.decode('utf-8', 'ignore')

# 2. 위키백과 DB 구축
def get_wiki_drama_list():
    print("📋 위키백과 드라마 DB 구축 중...")
    drama_set = set()
    
    # 최신작/예정작 수동 보완
    manual_list = [
        "결혼하자맹꽁아", "친절한선주씨", "스캔들", "심장을훔친게임", 
        "나의해리에게", "조립식가족", "이혼숙려캠프", "보물섬", 
        "모텔캘리포니아", "러브미", "스프링피버", "아이돌아이",
        "용감무쌍용수정", "세번째결혼", "우아한제국", "은애하는도적님아",
        "첫번째남자", "친밀한리플리", "화려한날들", "판사이한영",
        "마리와별난아빠들", "굿보이", "넉오프", "트리거", "하이퍼나이프"
    ]
    for m in manual_list:
        drama_set.add(normalize(m))
    
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
    return list(drama_set)

# 3. 닐슨코리아 데이터 수집
def fetch_nielsen_data(session, url, type_name):
    print(f"[{type_name}] 접속: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    try:
        res = session.get(url, headers=headers, timeout=20)
        html_content = get_decoded_html(res)
            
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            print(f"   ❌ [{type_name}] 테이블 없음")
            return []
            
        rows = table.find_all("tr")
        print(f"   ℹ️ [{type_name}] {len(rows)}행 발견")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 헤더 행 제외
                if "시청률" in rating or "프로그램" in raw_title:
                    continue
                
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
        print(f"   ❌ [{type_name}] 에러: {e}")
        return []

# 4. 필터링 로직
def filter_dramas(nielsen_data, wiki_db):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        
        # 1. 괄호 안의 제목 추출
        match = re.search(r'\((.*?)\)', raw_title)
        extracted = match.group(1).strip() if match else raw_title
        
        # 태그 제거
        extracted = re.sub(r'<.*?>', '', extracted)
        
        target_name = normalize(extracted)
        is_match = False
        
        # 표시할 제목 (깔끔하게 정제)
        display_title = clean_title_text(raw_title)
        if match:
             display_title = clean_title_text(match.group(1))

        # 유사도 매칭
        best_score = 0.0
        for db_title in wiki_db:
            score = get_similarity(target_name, db_title)
            if score > best_score:
                best_score = score
        
        if best_score >= 0.6:
            is_match = True
        
        # 키워드 보완
        if not is_match and any(k in raw_title for k in ["드라마", "미니시리즈", "연속극"]):
            is_match = True

        if is_match:
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
        days = ["월", "화", "수", "목", "금", "토", "일"]
        date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
        
        print(f"--- 실행 시작 ({date_str} / 수도권 기준) ---")
        
        wiki_db = get_wiki_drama_list()
        
        session = requests.Session()
        
        # [핵심] area=01 (수도권) 적용
        
        # 1. 지상파
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01"
        raw_t = fetch_nielsen_data(session, url_t, "지상파")
        final_t = filter_dramas(raw_t, wiki_db)
        
        time.sleep(2)
        
        # 2. 종편
        url_j = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=2_1&area=01"
        raw_j = fetch_nielsen_data(session, url_j, "종편")
        final_j = filter_dramas(raw_j, wiki_db)

        time.sleep(2)

        # 3. 케이블
        url_c = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=3_1&area=01"
        raw_c = fetch_nielsen_data(session, url_c, "케이블")
        final_c = filter_dramas(raw_c, wiki_db)
        
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
        
        report += "🔗 정보: 닐슨코리아"
        
        send_telegram(report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 에러: {err}")
        send_telegram(f"🚨 에러 발생: {e}")

if __name__ == "__main__":
    main()
