import streamlit as st
from datetime import datetime
import requests

# --- Telegram 설정 ---
TELEGRAM_TOKEN = "7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ"
TELEGRAM_CHAT_ID = "-1002404027768"

# --- 뉴스 수집 모듈 ---
def get_news(keyword, start_date, end_date, api):
    # 실제 API 호출 대신 예시 데이터 반환
    return [
        {
            "title": f"[{keyword}] 예시 뉴스 제목 {i+1}",
            "link": f"https://example.com/{keyword}/{i}",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Naver"
        }
        for i in range(25)
    ]

# --- Telegram 메시지 전송 ---
def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, data=data)

# --- 즐겨찾기 키워드 저장용 ---
if "favorites" not in st.session_state:
    st.session_state.favorites = []

# --- 검색 결과 저장용 ---
if "results" not in st.session_state:
    st.session_state.results = {}

if "display_count" not in st.session_state:
    st.session_state.display_count = {}

# --- UI 시작 ---
st.title("📊 Credit Issue Monitoring")

api = st.selectbox("API 선택", ["Naver", "Daum"])
keywords_input_col, search_btn_col, fav_btn_col = st.columns([6, 1, 1.5])

with keywords_input_col:
    keywords_input = st.text_input("🔍 키워드 (예: 삼성, 한화)", "")

with search_btn_col:
    if st.button("🔎 검색"):
        st.session_state.results.clear()
        st.session_state.display_count.clear()
        keywords = [kw.strip() for kw in keywords_input.split(",") if kw.strip()]
        for kw in keywords:
            news = get_news(kw, None, None, api)
            st.session_state.results[kw] = news
            st.session_state.display_count[kw] = 5

with fav_btn_col:
    if st.button("⭐ 즐겨찾기 추가"):
        for kw in keywords_input.split(","):
            clean_kw = kw.strip()
            if clean_kw and clean_kw not in st.session_state.favorites:
                st.session_state.favorites.append(clean_kw)

# --- 날짜 선택 ---
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("시작일", format="YYYY-MM-DD")
with col2:
    end_date = st.date_input("종료일", format="YYYY-MM-DD")

# --- 필터링 키워드 ---
filter_keyword = st.selectbox("⭐ 필터링 키워드 선택", options=[""] + st.session_state.favorites)

# --- 즐겨찾기에서 검색 ---
fav_col, fav_search_btn_col = st.columns([6, 1.5])
with fav_col:
    fav_selected = st.selectbox("⭐ 즐겨찾기에서 검색", options=[""] + st.session_state.favorites)
with fav_search_btn_col:
    if st.button("즐겨찾기로 검색"):
        if fav_selected:
            news = get_news(fav_selected, None, None, api)
            st.session_state.results[fav_selected] = news
            st.session_state.display_count[fav_selected] = 5

# --- 결과 출력 ---
if st.session_state.results:
    st.markdown("### 🔍 검색 결과")
    cols = st.columns(len(st.session_state.results))
    for i, (keyword, articles) in enumerate(st.session_state.results.items()):
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"#### 📁 {keyword}")
                count = st.session_state.display_count[keyword]
                for article in articles[:count]:
                    st.markdown(
                        f"<div style='margin-bottom:4px;'>"
                        f"<a href='{article['link']}' target='_blank'><b>{article['title']}</b></a><br>"
                        f"<span style='font-size: 12px; color: grey;'>{article['date']} | {article['source']}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                if len(articles) > count:
                    if st.button("더보기", key=f"more_{keyword}"):
                        st.session_state.display_count[keyword] += 10

                # Telegram 전송
                msg = f"<b>{keyword} 뉴스 상위 5개</b>\n"
                for article in articles[:5]:
                    msg += f"<a href='{article['link']}'>{article['title']}</a>\n"
                send_to_telegram(msg)
