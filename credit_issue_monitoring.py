import streamlit as st
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# Telegram 설정
TELEGRAM_BOT_TOKEN = '7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ'
TELEGRAM_CHAT_ID = '-1002404027768'

# 뉴스 검색 함수 (예시용 - 실제 API로 교체 가능)
def search_news(keyword, start_date=None, end_date=None, max_results=5):
    # 예시 데이터
    dummy_data = [
        {
            "title": f"[{keyword}] 예시 뉴스 제목 {i+1}",
            "link": "https://news.naver.com",
            "pubDate": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "source": "Naver"
        } for i in range(max_results)
    ]
    return dummy_data

# 텔레그램 전송 함수
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=payload)

# 즐겨찾기 저장용
if "favorites" not in st.session_state:
    st.session_state.favorites = []

# 기사 저장 상태
if "results" not in st.session_state:
    st.session_state.results = {}

# Streamlit 구성 시작
st.set_page_config(layout="wide")
st.title("📊 Credit Issue Monitoring")

# --- 검색 조건 입력 ---
api_option = st.selectbox("API 선택", ["Naver"], key="api")

# 키워드 및 버튼 정렬
col1, col2, col3 = st.columns([6, 1, 1.5])
with col1:
    keywords_input = st.text_input("🔍 키워드 (예: 삼성, 한화)", "")
with col2:
    search_button = st.button("검색", use_container_width=True)
with col3:
    add_fav_button = st.button("⭐ 즐겨찾기 추가", use_container_width=True)

col_date1, col_date2 = st.columns(2)
with col_date1:
    start_date = st.date_input("시작일", value=None)
with col_date2:
    end_date = st.date_input("종료일", value=None)

# 필터링 키워드 선택
filter_keyword = st.selectbox("📌 필터링 키워드 선택", st.session_state.favorites)

# 즐겨찾기 검색
col4, col5 = st.columns([6, 1.5])
with col4:
    fav_search_keyword = st.selectbox("⭐ 즐겨찾기에서 검색", options=st.session_state.favorites)
with col5:
    fav_search_button = st.button("즐겨찾기로 검색", use_container_width=True)

# 즐겨찾기 추가 기능
if add_fav_button and keywords_input:
    for k in [k.strip() for k in keywords_input.split(",") if k.strip()]:
        if k not in st.session_state.favorites:
            st.session_state.favorites.append(k)

# 검색 실행 함수
def run_search(keywords_str):
    st.session_state.results = {}
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    for kw in keywords:
        news_list = search_news(kw, start_date, end_date, max_results=5)
        st.session_state.results[kw] = {
            "articles": news_list,
            "visible_count": 5
        }
        # 텔레그램 전송
        message = f"<b>[{kw}] 뉴스 요약 상위 5건</b>\n"
        for a in news_list:
            message += f"- <a href='{a['link']}'>{a['title']}</a>\n"
        send_telegram_message(message)

# 검색 버튼
if search_button and keywords_input:
    run_search(keywords_input)

# 즐겨찾기에서 검색
if fav_search_button and fav_search_keyword:
    run_search(fav_search_keyword)

# --- 검색 결과 ---
if st.session_state.results:
    st.markdown("### 🔍 검색 결과")
    col_count = len(st.session_state.results)
    result_cols = st.columns(col_count)

    for idx, (kw, data) in enumerate(st.session_state.results.items()):
        with result_cols[idx]:
            with st.container():
                st.markdown(
                    f"""
                    <div style='border: 2px solid #bbb; border-radius: 10px; padding: 10px; margin-bottom: 20px;'>
                        <h5>📁 {kw}</h5>
                """, unsafe_allow_html=True)
                for article in data["articles"][:data["visible_count"]]:
                    st.markdown(
                        f"""
                        <div style='margin-bottom: 5px;'>
                            <a href="{article['link']}" target="_blank"><b>{article['title']}</b></a><br>
                            <small>{article['pubDate']} | {article['source']}</small>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                if data["visible_count"] < len(data["articles"]):
                    if st.button("더보기", key=f"more_{kw}"):
                        st.session_state.results[kw]["visible_count"] += 10
                st.markdown("</div>", unsafe_allow_html=True)
