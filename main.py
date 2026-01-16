import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import traceback
import time
import gzip
import io

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

# 제목 정제 (태그 제거만 수행)
def clean_title(text):
    # <본>, <재> 등 꺾쇠 괄호 내용 제거하지 않고 남길지, 지울지 결정
    # 사용자가 '판단'하길 원하셨으므로, 지저분한 태그만 제거하고 (재) 같은건 남깁니다.
    # 하지만 닐슨 원본은 보통 깔끔하므로 최소한의 공백 정리만 합니다.
    return text.strip()

# 닐슨 응답 복구 (압축/인코딩 해결)
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

# 닐슨 데이터 가져오기 (단순 수집)
def fetch_raw_data(session, url, label):
    print(f"[{label}] 데이터 수집 중...")
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    data_map = {} # 제목을 키로 사용하여 검색하기 위함
    data_list = [] # 순서대로 저장하기 위함
    
    try:
        res = session.get(url, headers=headers, timeout=20)
        html_content = get_decoded_html(res)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        table = soup.find("table", class_="ranking_tb")
        if not table: return [], {}
            
        rows = table.find_all("tr")
        rank_cursor = 1
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            try:
                channel = cols[1].get_text(strip=True)
                raw_title = cols[2].get_text(strip=True)
                rating = cols[3].get_text(strip=True)
                
                # 헤더 제외
                if "시청률" in rating or "프로그램" in raw_title: continue
                
                clean_t = clean_title(raw_title)
                
                item = {
                    "rank": rank_cursor,
                    "channel": channel,
                    "title": clean_t,
                    "rating": rating
                }
                
                data_list.append(item)
                data_map[clean_t] = rating # 제목으로 시청률 찾기용
                rank_cursor += 1
                
            except: continue
            
        return data_list, data_map
        
    except Exception as e:
        print(f"에러 발생 ({label}): {e}")
        return [], {}

# 데이터 병합 및 리포트 생성
def make_report_section(title, url_metro, url_nation, session):
    # 1. 수도권 데이터 (기준)
    metro_list, _ = fetch_raw_data(session, url_metro, f"{title}-수도권")
    time.sleep(1) # 매너 딜레이
    
    # 2. 전국 데이터 (참조용)
    _, nation_map = fetch_raw_data(session, url_nation, f"{title}-전국")
    time.sleep(1)
    
    txt = f"📡 {title} (Top 10)\n"
    
    if not metro_list:
        txt += "(데이터 없음)\n\n"
        return txt
        
    # 3. 병합 및 출력 (상위 10개만, 원하시면 20개로 수정 가능)
    count = 0
    for item in metro_list:
        if count >= 10: break 
        
        t_title = item['title']
        t_channel = item['channel']
        r_metro = item['rating']
        
        # 전국 시청률 찾기 (없으면 - 표시)
        r_nation = nation_map.get(t_title, "-")
        
        # [출력 포맷] 1위 마리와별난아빠들 | (KBS1) | 수도권 9.2 | 전국 8.5
        txt += f"{item['rank']}위 {t_title} | ({t_channel}) | 수도권 {r_metro} | 전국 {r_nation}\n"
        count += 1
        
    return txt + "\n"

# 메인 실행
def main():
    try:
        kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        yesterday = kst_now - datetime.timedelta(days=1)
        days_str = ["월", "화", "수", "목", "금", "토", "일"]
        date_str = yesterday.strftime(f"%Y-%m-%d({days_str[yesterday.weekday()]})")
        
        print(f"--- 실행 시작 ({date_str}) ---")
        
        session = requests.Session()
        
        # 리포트 헤더
        full_report = f"📺 {date_str} 시청률 랭킹\n(닐슨코리아 / 수도권 기준 정렬)\n━━━━━━━━━━━━━━━━━━\n\n"
        
        # 1. 지상파 (수도권 vs 전국)
        full_report += make_report_section(
            "지상파",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01", # 수도권
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00", # 전국
            session
        )
        
        # 2. 종편
        full_report += make_report_section(
            "종편",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=2_1&area=01",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=2_1&area=00",
            session
        )
        
        # 3. 케이블
        full_report += make_report_section(
            "케이블",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=3_1&area=01",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=3_1&area=00",
            session
        )
        
        full_report += "🔗 정보: 닐슨코리아\nhttps://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01"
        
        send_telegram(full_report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 에러: {err}")
        send_telegram(f"🚨 에러 발생: {e}")

if __name__ == "__main__":
    main()
