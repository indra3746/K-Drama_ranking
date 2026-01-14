import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback
import time # 딜레이를 위해 필수

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

# 2. 위키백과에서 드라마 제목 자동 수집 (Whitelist)
def get_wiki_drama_list():
    print("📋 위키백과 드라마 DB 구축 중...")
    drama_set = set()
    
    # 작년 말 ~ 올해 드라마를 모두 커버하기 위해 2개 연도 검색
    urls = [
        "https://ko.wikipedia.org/wiki/2025년_대한민국의_텔레비전_드라마_목록",
        "https://ko.wikipedia.org/wiki/2026년_대한민국의_텔레비전_드라마_목록"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for url in urls:
        try:
            print(f"   접속: {url} ...")
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 위키백과 'wikitable' 클래스를 가진 표들 탐색
            tables = soup.select("table.wikitable")
            for table in tables:
                rows = table.select("tr")
                for row in rows:
                    cols = row.select("td")
                    # 보통 제목은 앞쪽(1~2번째) 칸에 위치함
                    for col in cols[:3]:
                        # 1) <i> 태그 (기울임꼴) 안에 있는 텍스트는 99% 드라마 제목
                        italic = col.find("i")
                        if italic:
                            title = italic.get_text(strip=True)
                            drama_set.add(title.replace(" ", ""))
                        
                        # 2) 링크(a) 텍스트 중 따옴표가 있거나 긴 텍스트
                        link = col.find("a")
                        if link:
                            t = link.get_text(strip=True)
                            # '보기', '편집' 등 제외
                            if len(t) > 1 and "드라마" not in t:
                                drama_set.add(t.replace(" ", ""))
            
            time.sleep(1) # 위키 서버 부하 방지
            
        except Exception as e:
            print(f"   ⚠️ 위키 접속 실패: {e}")

    print(f"✅ 위키백과 DB 확보 완료: 총 {len(drama_set)}개 드라마")
    return drama_set

# 3. 닐슨코리아 데이터 수집 (세션 사용 + 딜레이)
def fetch_nielsen_data(session, url, type_name):
    print(f"[{type_name}] 닐슨 접속 시도...")
    
    try:
        # 접속 전 2초 딜레이 (사람인 척)
        time.sleep(2)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.nielsenkorea.co.kr/',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        
        res = session.get(url, headers=headers, timeout=20)
        res.encoding = 'euc-kr' # 인코딩 필수
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        
        # 테이블이 없는 경우 (차단 또는 로딩 실패)
        if not table:
            print(f"   ⚠️ [{type_name}] 테이블을 찾을 수 없음. HTML 구조 확인 필요.")
            # 디버깅: 혹시 리다이렉트 되었는지 확인
            if "로그인" in res.text or "Wait" in res.text:
                print("   🚫 접근 제한됨 (Login/Block)")
            return []
            
        rows = table.find_all("tr")
        print(f"   ✅ 데이터 테이블 발견 ({len(rows)}행)")
        
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
        print(f"   ❌ [{type_name}] 에러: {e}")
        return []

# 4. 필터링 로직 (위키 DB vs 닐슨 Raw)
def filter_dramas(nielsen_data, wiki_db):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        clean_raw = raw_title.replace(" ", "")
        
        is_match = False
        display_title = raw_title
        
        # 1) 괄호 안의 제목 추출
        # 예: 일일드라마(결혼하자맹꽁아) -> 결혼하자맹꽁아
        match = re.search(r'\((.*?)\)', raw_title)
        extracted = ""
        if match:
            extracted = match.group(1).strip()
            
        # 매칭 검사 1: 괄호 안 내용이 위키 DB에 있는가?
        if extracted:
            if extracted.replace(" ", "") in wiki_db:
                is_match = True
                display_title = extracted
        
        # 매칭 검사 2: 위키 제목이 닐슨 원본에 포함되는가?
        if not is_match:
            for wiki_t in wiki_db:
                # 닐슨: "주말드라마오징어게임2" vs 위키: "오징어게임2"
                if wiki_t in clean_raw and len(wiki_t) > 2:
                    is_match = True
                    display_title = wiki_t
                    break
        
        # 매칭 검사 3: (안전장치) '드라마', '미니시리즈' 단어 포함시 무조건 통과
        if not is_match:
            if any(k in clean_raw for k in ["드라마", "미니시리즈", "연속극"]):
                is_match = True
                if extracted: display_title = extracted # 기왕이면 괄호 안 내용으로
        
        if is_match:
            item['display_title'] = display_title
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
        
        print(f"--- 실행 시작 ({date_str} 기준) ---")
        
        # 1. 위키백과에서 리스트 확보
        wiki_db = get_wiki_drama_list()
        
        # 2. 닐슨 데이터 수집 (세션 하나로 유지)
        session = requests.Session()
        
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
        raw_t = fetch_nielsen_data(session, url_t, "지상파")
        
        url_c = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
        raw_c = fetch_nielsen_data(session, url_c, "종편/케이블")
        
        # 3. 매칭 및 필터링
        final_t = filter_dramas(raw_t, wiki_db)
        final_c_all = filter_dramas(raw_c, wiki_db)
        
        # 4. 종편/케이블 분리
        jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
        final_j = []
        final_c = []
        
        for item in final_c_all:
            ch_upper = item['channel'].upper().replace(" ", "")
            if any(j in ch_upper for j in jongpyeon_chs):
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
