import requests
from bs4 import BeautifulSoup
import datetime
import os

# 텔레그램 전송 함수
def send_telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    
    if token and chat_id and len(text) > 0:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        except Exception as e:
            print(f"전송 실패: {e}")

# 네이버 시청률 크롤링 함수
def fetch_naver_ratings(category):
    # 검색어: "지상파 드라마 시청률", "종편 드라마 시청률" 등
    query = f"{category} 드라마 시청률"
    url = f"https://search.naver.com/search.naver?where=nexearch&sm=tab_etc&query={query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        results = []
        
        # 네이버 시청률 리스트 영역 선택
        # 구조: div.rating_list > ul > li
        rows = soup.select("div.rating_list > ul > li")
        
        # 최대 10위까지 수집
        for row in rows[:10]:
            try:
                # 1. 순위
                rank = row.select_one(".rank").get_text(strip=True)
                
                # 2. 제목
                title_tag = row.select_one(".proc_tit") or row.select_one(".title") # 클래스명 변동 대비
                title = title_tag.get_text(strip=True) if title_tag else "제목없음"
                
                # 3. 방송사
                # 네이버는 방송사가 별도 태그로 잘 안나오고 텍스트 뭉치에 있거나 생략됨
                # 드라마 탭 특성상 제목 옆이나 아래 sub_text 활용
                channel = ""
                sub_text = row.select_one(".sub_text")
                if sub_text:
                    channel = f"({sub_text.get_text(strip=True)})"
                
                # 4. 시청률
                rating_tag = row.select_one(".rating_val") or row.select_one(".score")
                rating = rating_tag.get_text(strip=True) if rating_tag else ""
                
                # 5. 변동폭
                change = "-"
                change_area = row.select_one(".fluctuation")
                if change_area:
                    # up, down, same 클래스 확인
                    txt = change_area.get_text(strip=True)
                    cls = change_area.get('class', [])
                    
                    if any("up" in c for c in cls):
                        change = f"▲{txt}"
                    elif any("down" in c for c in cls):
                        change = f"▼{txt}"
                    elif any("same" in c for c in cls):
                        change = "-"
                
                # 결과 포맷팅: "1위 제목 | (방송사) | 12.8% | ▲0.3%"
                line = f"{rank}위 {title} | {channel} | {rating} | {change}"
                results.append(line)
                
            except Exception as e:
                continue
                
        return results
            
    except Exception as e:
        print(f"[{category}] 파싱 에러: {e}")
        return []

# 메인 실행 로직
def main():
    # 요일 구하기
    now = datetime.datetime.now()
    days = ["월", "화", "수", "목", "금", "토", "일"]
    day_str = days[now.weekday()]
    date_str = now.strftime(f"%Y-%m-%d({day_str})")
    
    # 리포트 헤더
    report = f"📺 {date_str} 드라마 시청률 랭킹\n━━━━━━━━━━━━━━━━━━\n\n"
    
    # 1. 지상파
    report += "📡 지상파 (KBS/MBC/SBS)\n"
    k_items = fetch_naver_ratings("지상파")
    if k_items:
        report += "\n".join(k_items)
    else:
        report += " (어제 방영된 드라마 없음 또는 집계 중)"
    report += "\n\n"
    
    # 2. 종편
    report += "📡 종편 (JTBC/MBN/TV조선/채널A)\n"
    j_items = fetch_naver_ratings("종편")
    if j_items:
        report += "\n".join(j_items)
    else:
        report += " (어제 방영된 드라마 없음)"
    report += "\n\n"
    
    # 3. 케이블
    report += "📡 케이블 (tvN/ENA)\n"
    c_items = fetch_naver_ratings("케이블")
    if c_items:
        report += "\n".join(c_items)
    else:
        report += " (어제 방영된 드라마 없음)"
    report += "\n\n"
    
    report += "🔗 상세정보: 네이버 시청률 검색"
    
    # 전송
    send_telegram(report)

if __name__ == "__main__":
    main()
