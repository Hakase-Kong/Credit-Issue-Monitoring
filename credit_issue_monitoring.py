import streamlit as st

# 스타일 개선
st.markdown("""
    <style>
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        .stButton button {margin-top: 6px; margin-bottom: 6px; border-radius: 8px;}
        .stTextInput > div > div > input {font-size: 16px;}
    </style>
""", unsafe_allow_html=True)

# 1. 키워드 입력 및 버튼
col1, col2, col3 = st.columns([6, 1, 1])
with col1:
    keywords_input = st.text_input("🔍 키워드 (예: 삼성, 한화)", value="")
with col2:
    search_clicked = st.button("검색", use_container_width=True)
with col3:
    fav_add_clicked = st.button("⭐ 즐겨찾기 추가", use_container_width=True)

# 2. 날짜 입력
date_col1, date_col2 = st.columns([1, 1])
with date_col1:
    start_date = st.date_input("시작일")
with date_col2:
    end_date = st.date_input("종료일")

# 3. 필터 옵션
with st.expander("🛡️ 신용위험 필터 옵션"):
    enable_credit_filter = st.checkbox("신용위험 뉴스만 필터링", value=True)
    credit_filter_keywords = st.multiselect(
        "신용위험 관련 키워드 (하나 이상 선택)",
        options=["신용등급", "신용평가", "하향", "상향", "강등", "조정", "부도", "파산", "디폴트", "채무불이행", "적자", "영업손실", "현금흐름", "자금난", "재무위험", "부정적 전망", "긍정적 전망", "기업회생", "워크아웃", "구조조정", "자본잠식"],
        default=["신용등급", "신용평가", "하향", "상향", "강등", "조정", "부도", "파산", "디폴트", "채무불이행", "적자", "영업손실", "현금흐름", "자금난", "재무위험", "부정적 전망", "긍정적 전망", "기업회생", "워크아웃", "구조조정", "자본잠식"]
    )

# 4. 뉴스 카드 및 더보기 버튼 (위 render_articles_columnwise 함수 참고)
