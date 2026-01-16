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

# 제목 정제 (단순 공백 제거)
def clean_title(text):
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

# 닐슨 데이터 가져오기
def fetch_raw_data(session, url, label):
    print(f"[{label}] 데이터 수집 중...")
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.nielsenkorea.co.kr/',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    data_map = {} 
    data_list = [] 
    
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
                
                if "시청률" in rating or "프로그램" in raw_title: continue
                
                clean_t = clean_title(raw_title)
                
                item = {
                    "rank": rank_cursor,
                    "channel": channel,
                    "title": clean_t,
                    "rating": rating
                }
                
                data_list.append(item)
                data_map[clean_t] = rating 
                rank_cursor += 1
                
            except: continue
            
        return data_list, data_map
        
    except Exception as e:
        print(f"에러 발생 ({label}): {e}")
        return [], {}

# 리포트 섹션 생성 (순위 채널 | 제목 | 수도권 | 전국)
def make_report_section(title, url_metro, url_nation, session):
    # 1. 수도권 데이터 (기준)
    metro_list, _ = fetch_raw_data(session, url_metro, f"{title}-수도권")
    time.sleep(1)
    
    # 2. 전국 데이터 (참조용)
    _, nation_map = fetch_raw_data(session, url_nation, f"{title}-전국")
    time.sleep(1)
    
    txt = f"📡 {title} (Top 10)\n"
    
    if not metro_list:
        txt += "(데이터 없음)\n\n"
        return txt
        
    # 3. 병합 및 출력
    count = 0
    for item in metro_list:
        if count >= 10: break 
        
        t_title = item['title']
        t_channel = item['channel']
        r_metro = item['rating']
        
        # 전국 시청률 매칭 (없으면 - 표시)
        r_nation = nation_map.get(t_title, "-")
        
        # [포맷] 1위 KBS1 | 제목 | 9.2 | 10.7
        txt += f"{item['rank']}위 {t_channel} | {t_title} | {r_metro} | {r_nation}\n"
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
        
        # 헤더 및 범례
        full_report = f"📺 {date_str} 시청률 랭킹\n━━━━━━━━━━━━━━━━━━\n"
        full_report += "순위 채널 | 제목 | 수도권 | 전국\n\n"
        
        # 1. 지상파
        full_report += make_report_section(
            "지상파",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01",
            "https://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=00",
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
        
        full_report += "🔗 닐슨코리아\nhttps://www.nielsenkorea.co.kr/tv_terrestrial_day.asp?menu=Tit_1&sub_menu=1_1&area=01"
        
        send_telegram(full_report)
        print("--- 전송 완료 ---")
        
    except Exception as e:
        err = traceback.format_exc()
        print(f"🔥 에러: {err}")
        send_telegram(f"🚨 에러 발생: {e}")

if __name__ == "__main__":
    main()
