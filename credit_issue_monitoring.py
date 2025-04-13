# 파일명: app.py

import streamlit as st
from datetime import datetime
from search_api import search_news  # 뉴스 검색 함수
from telegram_bot import send_telegram_message  # 텔레그램 전송 함수

# 상태 변수 초기화
if "results" not in st.session_state:
    st.session_state.results = {}
if "visible_count" not in st.session_state:
    st.session_state.visible_count = {}
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "search_mode" not in st.session_state:
    st.session_state.search_mode = None

# 기본 설정
st.set_page_config(page_title="Credit Issue Monitoring", layout="wide")
st.title("📊 Credit Issue Monitoring")

# --- 입력 영역 ---
api_type = st.selectbox("API 선택", ["Naver", "Daum", "Google"])

col1, col2, col3 = st.columns([5, 1, 1])
with col1:
    keyword_input = st.text_input("🔍 키워드 (예: 삼성, 한화)")
with col2:
    search_clicked = st.button("🔎 검색")
with col3:
    add_favorite_clicked = st.button("⭐ 즐겨찾기 추가")

col4, col5 = st.columns(2)
with col4:
    start_date = st.date_input("시작일", value=datetime.today())
with col5:
    end_date = st.date_input("종료일", value=datetime.today())

filter_keyword = st.selectbox("⭐ 필터링 키워드 선택", options=st.session_state.favorites if st.session_state.favorites else [])

col6, col7 = st.columns([5, 1])
with col6:
    favorite_selected = st.selectbox("⭐ 즐겨찾기에서 검색", options=st.session_state.favorites if st.session_state.favorites else [])
with col7:
    search_favorite_clicked = st.button("즐겨찾기로 검색")

# --- 즐겨찾기 추가 ---
if add_favorite_clicked:
    new_keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]
    st.session_state.favorites = list(set(st.session_state.favorites + new_keywords))

# --- 키워드 검색 ---
if search_clicked and keyword_input:
    keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]
    st.session_state.results = {}
    st.session_state.visible_count = {}

    for keyword in keywords:
        news_items = search_news(api_type, keyword, start_date, end_date)
        st.session_state.results[keyword] = news_items
        st.session_state.visible_count[keyword] = 5

        # 텔레그램 전송
        summary = "\n".join([f"{item['title']}\n{item['date']} | {item['link']}" for item in news_items[:5]])
        send_telegram_message(f"[{keyword}] 검색 결과 상위 5건:\n{summary}")

    st.session_state.search_mode = "keyword"

# --- 즐겨찾기 검색 ---
if search_favorite_clicked and favorite_selected:
    keyword = favorite_selected
    news_items = search_news(api_type, keyword, start_date, end_date)
    st.session_state.results = {keyword: news_items}
    st.session_state.visible_count = {keyword: 5}

    # 텔레그램 전송
    summary = "\n".join([f"{item['title']}\n{item['date']} | {item['link']}" for item in news_items[:5]])
    send_telegram_message(f"[{keyword}] 즐겨찾기 검색 결과 상위 5건:\n{summary}")

    st.session_state.search_mode = "favorite"

# --- 검색 결과 표시 ---
if st.session_state.results:
    st.markdown("## 🔎 검색 결과")
    cols = st.columns(len(st.session_state.results))

    for i, (keyword, news_list) in enumerate(st.session_state.results.items()):
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"### 📁 {keyword}")
                display_count = st.session_state.visible_count.get(keyword, 5)

                for news in news_list[:display_count]:
                    st.markdown(
                        f"""
                        <div style='margin-bottom: 3px;'>
                            <a href="{news['link']}" target="_blank">[{keyword}] {news['title']}</a><br>
                            <span style='font-size: 0.8em; color: gray;'>{news['date']} | {news['source']}</span>
                        </div>
                        """, unsafe_allow_html=True
                    )

                if display_count < len(news_list):
                    if st.button("더보기", key=f"more_{keyword}"):
                        st.session_state.visible_count[keyword] += 10
