import streamlit as st
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
import concurrent.futures
import telepot

# --- API 키 설정 ---
NAVER_CLIENT_ID = "_qXuzaBGk_jQesRRPRvu"
NAVER_CLIENT_SECRET = "lZc2gScgNq"
NEWS_API_KEY = "3a33b7b756274540926aeea8df60637c"
TELEGRAM_TOKEN = "7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ"
TELEGRAM_CHAT_ID = "-1002404027768"

credit_keywords = ["신용등급", "신용하향", "신용상향", "등급조정", "부정적", "긍정적", "평가"]
finance_keywords = ["적자", "흑자", "부채", "차입금", "현금흐름", "영업손실", "순이익", "부도", "파산"]
all_filter_keywords = sorted(set(credit_keywords + finance_keywords))

favorite_keywords = set()

class Telegram:
    def __init__(self):
        self.bot = telepot.Bot(token=TELEGRAM_TOKEN)

    def sendMessage(self, message):
        self.bot.sendMessage(TELEGRAM_CHAT_ID, message, parse_mode="Markdown")

def filter_by_issues(title, desc, selected_keywords):
    content = title + " " + desc
    return all(re.search(k, content) for k in selected_keywords)

def fetch_naver_news(query, start_date=None, end_date=None, filters=None):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    articles = []
    for page in range(1, 6):
        params = {
            "query": query,
            "display": 10,
            "start": (page - 1) * 10 + 1,
            "sort": "date"
        }
        response = requests.get("https://openapi.naver.com/v1/search/news.json", headers=headers, params=params)
        if response.status_code != 200:
            break
        items = response.json().get("items", [])
        for item in items:
            title, desc = item["title"], item["description"]
            pub_date_obj = datetime.strptime(item["pubDate"], "%a, %d %b %Y %H:%M:%S %z")
            if start_date and pub_date_obj.date() < start_date:
                continue
            if end_date and pub_date_obj.date() > end_date:
                continue
            if not re.search(rf"\b{re.escape(query)}\b", title + desc):
                continue
            if filters and not filter_by_issues(title, desc, filters):
                continue
            articles.append({
                "title": title,
                "link": item["link"],
                "pubDate": pub_date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Naver"
            })
    return articles

# Streamlit 세션 상태 초기화
if "results" not in st.session_state:
    st.session_state.results = {}
if "shown_counts" not in st.session_state:
    st.session_state.shown_counts = {}

# --- UI ---
st.title("📊 Credit Issue Monitoring")

api_choice = st.selectbox("API 선택", ["Naver", "NewsAPI"])

col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    keywords_input = st.text_input("🔍 키워드 (예: 삼성, 한화)", key="input_keywords")
with col2:
    if st.button("검색"):
        if not keywords_input:
            st.warning("키워드를 입력해주세요.")
        else:
            keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
            if len(keyword_list) > 10:
                st.error("⚠️ 키워드는 최대 10개까지 입력 가능합니다.")
            else:
                st.session_state.results.clear()
                st.session_state.shown_counts.clear()
                with st.spinner("뉴스 검색 중..."):
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        futures = {
                            k: executor.submit(fetch_naver_news, k)
                            for k in keyword_list
                        }
                        for k, fut in futures.items():
                            articles = fut.result()
                            st.session_state.results[k] = articles
                            st.session_state.shown_counts[k] = 5

                # 텔레그램 전송
                tg = Telegram()
                for k in keyword_list:
                    message = f"*{k} 뉴스 요약 상위 5건*\n"
                    for a in st.session_state.results.get(k, [])[:5]:
                        message += f"- [{a['title']}]({a['link']})\n"
                    tg.sendMessage(message)

with col3:
    if st.button("⭐ 즐겨찾기 추가"):
        new_keywords = {kw.strip() for kw in keywords_input.split(",") if kw.strip()}
        favorite_keywords.update(new_keywords)
        st.success("즐겨찾기에 추가되었습니다.")

start_date = st.date_input("시작일", value=None)
end_date = st.date_input("종료일", value=None)
filters = st.multiselect("📌 필터링 키워드 선택", all_filter_keywords)

fav_col1, fav_col2 = st.columns([4, 1])
with fav_col1:
    fav_selected = st.multiselect("⭐ 즐겨찾기에서 검색", sorted(favorite_keywords), key="fav_keywords")
with fav_col2:
    if st.button("즐겨찾기로 검색"):
        st.session_state.results.clear()
        st.session_state.shown_counts.clear()
        with st.spinner("뉴스 검색 중..."):
            for k in fav_selected:
                articles = fetch_naver_news(k, start_date, end_date, filters)
                st.session_state.results[k] = articles
                st.session_state.shown_counts[k] = 5

# --- 결과 표시 (병렬 카드 스타일, 키워드별 더보기) ---
if st.session_state.results:
    st.markdown("### 🔍 검색 결과")
    keyword_cols = st.columns(len(st.session_state.results))
    for i, (k, articles) in enumerate(st.session_state.results.items()):
        with keyword_cols[i]:
            st.markdown(f"#### 🗂️ {k}")
            for article in articles[:st.session_state.shown_counts[k]]:
                with st.container():
                    st.markdown(f"**[{article['title']}]({article['link']})**")
                    st.caption(f"{article['pubDate']} | {article['source']}")
                    st.markdown("---")
            if len(articles) > st.session_state.shown_counts[k]:
                if st.button(f"더보기 ({k})", key=f"more_{k}"):
                    st.session_state.shown_counts[k] += 10
