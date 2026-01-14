import requests
from bs4 import BeautifulSoup
import datetime
import os
import re

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

# 2. [핵심] 현재 방영중인 드라마 제목 리스트 확보 (Whitelist)
def get_current_drama_titles():
    print("📋 현재 방영중인 드라마 리스트 확보 중 (Daum 검색)...")
    
    # 지상파, 종편, 케이블 드라마 검색 쿼리
    queries = ["지상파 드라마 시청률", "종편 드라마 시청률", "케이블 드라마 시청률"]
    drama_titles = set()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    for q in queries:
        try:
            url = f"https://search.daum.net/search?w=tot&q={q}"
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Daum 검색결과에서 제목 추출
            # (클래스명은 변할 수 있으므로 여러 후보군 탐색)
            titles = soup.select(".tit_item, .fn_tit, .link_tit")
            
            for t in titles:
                # 제목 정제 (특수문자 제거, 공백 제거)
                raw_title = t.get_text(strip=True)
                clean_title = re.sub(r'\[.*?\]|\(.*?\)', '', raw_title).strip() # 괄호 안 내용 제거
                if len(clean_title) > 1: # 한 글자 제목은 제외 (오류 방지)
                    drama_titles.add(clean_title)
                    
        except Exception as e:
            print(f"⚠️ 드라마 목록 수집 중 에러 ({q}): {e}")
            
    print(f"✅ 확보된 드라마 제목 ({len(drama_titles)}개): {list(drama_titles)[:5]} ...")
    return drama_titles

# 3. 닐슨코리아 파싱 함수
def fetch_nielsen_ratings(url, type_name):
    print(f"[{type_name}] 닐슨코리아 데이터 수집: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'euc-kr' # 한글 깨짐 방지
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            return []
            
        rows = table.find_all("tr")
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue 
            
            try:
                # 닐슨 데이터 추출
                # rank는 여기서 가져오지만, 나중에 드라마끼리 다시 매길 것임
                channel = cols[1].get_text(strip=True)
                title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 닐슨 제목 정제 (공백 등)
                clean_nielsen_title = title.strip()
                
                results.append({
                    "channel": channel,
                    "title": clean_nielsen_title,
                    "rating": rating
                })
            except: continue
            
        return results
        
    except Exception as e:
        print(f"⛔ [{type_name}] 접속 에러: {e}")
        return []

# 4. 데이터 매칭 및 순위 재산정
def filter_and_rank_dramas(nielsen_data, whitelist_titles):
    filtered = []
    
    for item in nielsen_data:
        nielsen_title = item['title']
        
        # 매칭 로직: Whitelist 제목이 닐슨 제목 안에 포함되는지 확인
        # 예: Whitelist "결혼하자 맹꽁아" in Nielsen "일일드라마(결혼하자맹꽁아)"
        is_match = False
        
        # 1. 정확한 포함 여부 확인
        for drama in whitelist_titles:
            # 공백 제거하고 비교 (정확도 향상)
            if drama.replace(" ", "") in nielsen_title.replace(" ", ""):
                is_match = True
                # 제목을 깔끔한 Whitelist 제목으로 교체 (선택사항)
                item['display_title'] = drama 
                break
        
        # 2. (보완) 제목에 '드라마', '시리즈'가 명시적으로 있으면 추가 허용
        if not is_match:
            if any(x in nielsen_title for x in ["드라마", "미니시리즈", "연속극"]):
                is_match = True
                item['display_title'] = nielsen_title # 원래 제목 사용

        if is_match:
            # 시청률 숫자로 변환 (정렬용)
            try:
                item['rating_float'] = float(item['rating'].replace("%", "").strip())
            except:
                item['rating_float'] = 0.0
            filtered.append(item)
            
    # 시청률 내림차순 정렬
    filtered.sort(key=lambda x: x['rating_float'], reverse=True)
    
    return filtered

# 5. 메인 실행
def main():
    # 시간 설정
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    yesterday = kst_now - datetime.timedelta(days=1)
    days = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
    
    print(f"--- 실행 시작 ({date_str} 기준) ---")
    
    # 1. Whitelist 확보 (현재 방영 드라마)
    active_dramas = get_current_drama_titles()
    
    # 2. 닐슨 데이터 수집 (Raw Data)
    url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
    raw_t = fetch_nielsen_ratings(url_t, "지상파")
    
    url_c = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
    raw_c = fetch_nielsen_ratings(url_c, "종편/케이블")
    
    # 3. 매칭 및 필터링
    final_t = filter_and_rank_dramas(raw_t, active_dramas)
    final_c_all = filter_and_rank_dramas(raw_c, active_dramas)
    
    # 4. 종편/케이블 분리 (채널명 기준)
    jongpyeon_chs = ["JTBC", "MBN", "TV CHOSUN", "TV조선", "채널A"]
    final_j = []
    final_c = []
    
    for item in final_c_all:
        ch_upper = item['channel'].upper().replace(" ", "")
        if any(j in ch_upper for j in jongpyeon_chs):
            final_j.append(item)
        else:
            final_c.append(item)
            
    # 5. 리포트 작성
    report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
    
    # 지상파
    report += "📡 지상파\n"
    if final_t:
        for i, item in enumerate(final_t[:5]): # 자체 순위 매김
            title = item.get('display_title', item['title'])
            report += f" {i+1}위 {title} | ({item['channel']}) | {item['rating']}%\n"
    else:
        report += "(결방 또는 데이터 없음)\n"
    report += "\n"

    # 종편
    report += "📡 종편\n"
    if final_j:
        for i, item in enumerate(final_j[:5]):
            title = item.get('display_title', item['title'])
            report += f" {i+1}위 {title} | ({item['channel']}) | {item['rating']}%\n"
    else:
        report += "(결방 또는 데이터 없음)\n"
    report += "\n"
    
    # 케이블
    report += "📡 케이블\n"
    if final_c:
        for i, item in enumerate(final_c[:5]):
            title = item.get('display_title', item['title'])
            report += f" {i+1}위 {title} | ({item['channel']}) | {item['rating']}%\n"
    else:
        report += "(결방 또는 데이터 없음)\n"
    report += "\n"
    
    report += "🔗 정보: 닐슨코리아"
    
    send_telegram(report)
    print("--- 전송 완료 ---")

if __name__ == "__main__":
    main()
