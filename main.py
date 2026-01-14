import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback

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
# [비상용 수동 리스트]
# 네이버 접속이 차단될 경우를 대비해, 현재 방영중인 주요 드라마를 넣어둠 (지속 업데이트 권장)
MANUAL_DRAMA_LIST = [
    "러브 미", "스프링 피버", "아이돌아이", "판사 이한영", "화려한 날들", 
    "은애하는 도적님아", "첫 번째 남자", "친밀한 리플리", "결혼하자 맹꽁아",
    "용감무쌍 용수정", "세 번째 결혼", "우아한 제국", "나의 해리에게",
    "조립식 가족", "이혼숙려캠프", "심장을 훔친 게임", "스캔들", "친절한 선주씨",
    "모텔 캘리포니아", "보물섬", "협상의 기술", "살롱 드 홈즈", "그래, 이혼하자"
]
# ==========================================

# 2. 네이버 '방영중 드라마' 리스트 크롤링 (Whitelist 생성)
def get_active_dramas():
    print("📋 네이버 '방영중 드라마' 목록 확보 시도...")
    active_titles = set()
    
    # 1단계: 수동 리스트 먼저 등록 (기본값)
    for t in MANUAL_DRAMA_LIST:
        active_titles.add(t.replace(" ", ""))
        
    # 2단계: 네이버 검색 시도
    url = "https://search.naver.com/search.naver?where=nexearch&sm=tab_etc&query=방영중드라마"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 네이버 드라마 카드 리스트 (스크린샷 기반 구조 추정)
        # 보통 class="text" 혹은 "title" 안에 제목이 있음
        titles = soup.select(".info_area .tit, .text, .title")
        
        crawled_count = 0
        for t in titles:
            title = t.get_text(strip=True)
            # 글자수가 너무 짧거나(1자), '시청률' 같은 잡다한 텍스트 제외
            if len(title) > 1 and "시청률" not in title:
                clean_t = title.replace(" ", "")
                active_titles.add(clean_t)
                crawled_count += 1
        
        if crawled_count > 0:
            print(f"   ✅ 네이버 크롤링 성공: {crawled_count}개 추가됨")
        else:
            print("   ⚠️ 네이버 크롤링 실패 (구조 변경 또는 차단), 수동 리스트 사용")
            
    except Exception as e:
        print(f"   ⚠️ 네이버 접속 에러: {e}")
        
    print(f"   ℹ️ 최종 감시 대상 드라마: {len(active_titles)}개")
    return active_titles

# 3. 닐슨코리아 데이터 수집
def fetch_nielsen_data(url, type_name):
    print(f"[{type_name}] 닐슨 데이터 수집: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nielsenkorea.co.kr/'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'euc-kr' # 한글 깨짐 방지 필수
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        
        table = soup.find("table", class_="ranking_tb")
        if not table:
            print(f"   ⚠️ 테이블 없음 (차단 또는 페이지 오류)")
            return []
            
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 시청률 숫자 변환 (정렬용)
                try:
                    rating_val = float(rating.replace("%", "").strip())
                except:
                    rating_val = 0.0
                
                results.append({
                    "channel": channel,
                    "title": raw_title, # 원본 제목 (나중에 가공)
                    "rating": rating,
                    "rating_val": rating_val
                })
            except: continue
            
        return results
    except Exception as e:
        print(f"   ❌ 접속 에러: {e}")
        return []

# 4. 데이터 매칭 (핵심 로직)
def filter_dramas(nielsen_data, active_set):
    filtered = []
    
    for item in nielsen_data:
        raw_title = item['title']
        clean_raw = raw_title.replace(" ", "")
        
        # 1단계: 괄호 안의 제목 추출 "일일드라마(결혼하자맹꽁아)" -> "결혼하자맹꽁아"
        match = re.search(r'\((.*?)\)', raw_title)
        extracted_title = ""
        if match:
            extracted_title = match.group(1).strip()
        
        # 2단계: 매칭 검사
        is_found = False
        display_title = raw_title
        
        # (1) 괄호 안 제목이 Whitelist에 있는가?
        if extracted_title:
            if extracted_title.replace(" ", "") in active_set:
                is_found = True
                display_title = extracted_title
        
        # (2) 원본 제목 자체가 Whitelist에 포함되는가? (괄호 없는 경우 대비)
        if not is_found:
            for target in active_set:
                if target in clean_raw: # 예: "스프링피버" in "월화드라마스프링피버"
                    is_found = True
                    # display_title은 닐슨 원본 유지하거나, 필요시 매칭된 걸로 교체
                    break
                    
        if is_found:
            item['display_title'] = display_title
            filtered.append(item)
            
    # 시청률 순 정렬
    filtered.sort(key=lambda x: x['rating_val'], reverse=True)
    return filtered

# 5. 메인 실행
def main():
    try:
        # 날짜 계산 (KST)
        kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        yesterday = kst_now - datetime.timedelta(days=1)
        days = ["월", "화", "수", "목", "금", "토", "일"]
        date_str = yesterday.strftime(f"%Y-%m-%d({days[yesterday.weekday()]})")
        
        print(f"--- 실행 시작 ({date_str} 기준) ---")
        
        # 1. 감시 대상 드라마 리스트 확보 (Naver + Manual)
        active_set = get_active_dramas()
        
        # 2. 닐슨 데이터 수집 (Raw Data)
        url_t = "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00"
        raw_t = fetch_nielsen_data(url_t, "지상파")
        
        url_c = "https://www.nielsenkorea.co.kr/tv_cable_day.asp?menu=Tit_2&sub_menu=2_1&area=00"
        raw_c = fetch_nielsen_data(url_c, "종편/케이블")
        
        # 3. 매칭 필터링
        final_t = filter_dramas(raw_t, active_set)
        final_c_all = filter_dramas(raw_c, active_set)
        
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
        
        # 분리 후 재정렬
        final_j.sort(key=lambda x: x['rating_val'], reverse=True)
        final_c.sort(key=lambda x: x['rating_val'], reverse=True)
        
        # 5. 리포트 작성
        report = f"📺 {date_str} 드라마 시청률 랭킹\n(닐슨코리아 / 어제 방영분)\n━━━━━━━━━━━━━━━━━━\n\n"
        
        def make_section(title, data):
            txt = f"📡 {title}\n"
            if data:
                for i, item in enumerate(data[:5]): # 5위까지
                    txt += f" {i+1}위 {item['display_title']} | ({item['channel']}) | {item['rating']}\n"
            else:
                txt += "(결방 또는 데이터 없음)\n"
            return txt + "\n"
            
        report += make_section("지상파 (Top 5)", final_t)
        report += make_section("종편 (Top 5)", final_j)
        report += make_section("케이블 (Top 5)", final_c)
        
        report += "🔗 정보: 닐슨코리아"
        
        send_telegram(report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 치명적 오류:\n{err}")
        send_telegram(f"🚨 봇 오류 발생:\n{str(e)}")

if __name__ == "__main__":
    main()
