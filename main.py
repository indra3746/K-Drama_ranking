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

# [핵심 함수] 두 문자열의 유사도 계산 (0.0 ~ 1.0)
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
    
    # [비상용 수동 리스트] 위키에 없어도 이건 꼭 챙겨라
    manual_list = [
        "결혼하자맹꽁아", "친절한선주씨", "스캔들", "심장을훔친게임", 
        "나의해리에게", "조립식가족", "이혼숙려캠프", "보물섬", 
        "모텔캘리포니아", "러브미", "스프링피버", "아이돌아이",
        "용감무쌍용수정", "세번째결혼", "우아한제국"
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
                            # '보기', '드라마' 등 제외하고 제목만
                            if len(text) > 1 and "드라마" not in text:
                                drama_set.add(normalize(text))
        except: pass

    print(f"✅ 비교군(Whitelist) 확보 완료: {len(drama_set)}개")
    return list(drama_set) # 유사도 비교를 위해 리스트로 변환

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
        res.encoding = 'euc-kr' 
        
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
        
        # 비교를 위해 정규화(공백제거)
        target_name = normalize(extracted)
        
        is_match = False
        display_title = extracted
        
        # [유사도 매칭 시작]
        # Whitelist(위키DB)에 있는 제목들과 하나씩 비교해서 가장 높은 점수를 찾음
        best_score = 0.0
        
        for db_title in wiki_
