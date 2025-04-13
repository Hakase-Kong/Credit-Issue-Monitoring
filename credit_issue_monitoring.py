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

# --- 텔레그램 설정 ---
TELEGRAM_TOKEN = "7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ"
TELEGRAM_CHAT_ID = "-1002404027768"

credit_keywords = ["신용등급", "신용하향", "신용상향", "등급조정", "부정적", "긍정적", "평가"]
finance_keywords = ["적자", "흑자", "부채", "차입금", "현금흐름", "영업손실", "순이익", "부도", "파산"]
all_filter_keywords = sorted(set(credit_keywords + finance_keywords))
favorite_keywords = set()

# --- 텔레그램 클래스 ---
class Telegram:
    def __init__(self):
        self.bot = telepot.Bot(token=TELEGRAM_TOKEN)

    def send_message(self, message):
        self.bot.sendMessage(TELEGRAM_CHAT_ID, message, parse_mode="Markdown")

# --- 필터 검사 ---
def filter_by_issues(title, desc, selected_keywords):
    content = title + " " + desc
    return all(re.search(k, content) for k in selected_keywords)

# --- 뉴스 수집 함수 ---
def fetch_naver_news(query, start_date=None, end_date=None, filters=None, limit=100):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    articles = []
    for page in range(1, 6):
        if len(articles) >= limit:
            break
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
            pub_date = datetime.strptime(item["pubDate"], "%a, %d %b %Y %H:%M:%S %z").date()
            if start_date and pub_date < start_date:
                continue
            if end_date and pub_date > end_date:
                continue
            if filters and not filter_by_issues(title, desc, filters):
                continue

            articles.append({
                "title": re.sub("<.*?>", "", title),
                "link": item["link"],
                "pubDate": pub_date.strftime("%Y-%m-%d"),
                "source": "Naver"
            })
    return articles[:limit]

# --- UI에 기사 출력 ---
def render_articles_columnwise(results, show_limit, expanded_keywords):
    st.markdown("### 🔍 검색 결과")
    cols = st.columns(len(results))
    for col, (keyword, articles) in zip(cols, results.items()):
        with col:
            with st.container():
                st.markdown(f"#### 📂 {keyword}")
                st.markdown('<div style="border: 1px solid #ddd; padding: 10px; border-radius: 8px;">', unsafe_allow_html=True)
                for i, article in enumerate(articles[:show_limit[keyword]]):
                    st.markdown(f"- [{article['title']}]({article['link']})")
                    st.caption(f"{article['pubDate']} | {article['source']}")
                    if i < len(articles[:show_limit[keyword]]) - 1:
                        st.markdown("---")
                st.markdown('</div>', unsafe_allow_html=True)

                if show_limit[keyword] < len(articles):
                    if st.button("더보기", key=f"more_{keyword}"):
                        expanded_keywords.add(keyword)

# --- Streamlit 시작 ---
st.set_page_config(layout="wide")
st.markdown("<h1 style='color:#1a1a1a;'>📊 Credit Issue Monitoring</h1>", unsafe_allow_html=True)

# --- 스타일 개선 (CSS) ---
st.markdown("""
    <style>
        .stButton>button {
            height: 3em;
            width: 6em;
            font-size: 0.9em;
            margin: 0.2em;
        }
        .stTextInput>div>div>input {
            font-size: 0.9em;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- 기본 UI ---
api_choice = st.selectbox("API 선택", ["Naver", "NewsAPI"])

col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    keywords_input = st.text_input("🔍 키워드 (예: 삼성, 한화)", value="")
with col2:
    search_clicked = st.button("검색")
with col3:
    if st.button("⭐ 즐겨찾기 추가"):
        new_keywords = {kw.strip() for kw in keywords_input.split(",") if kw.strip()}
        favorite_keywords.update(new_keywords)
        st.success("즐겨찾기에 추가되었습니다.")

start_date = st.date_input("시작일")
end_date = st.date_input("종료일")
filters = st.multiselect("⭐ 필터링 키워드 선택", all_filter_keywords)

fav_col1, fav_col2 = st.columns([5, 1])
with fav_col1:
    fav_selected = st.multiselect("⭐ 즐겨찾기에서 검색", sorted(favorite_keywords))
with fav_col2:
    fav_search_clicked = st.button("즐겨찾기로 검색")

# --- 검색 결과 처리 ---
search_results = {}
show_limit = {}
expanded_keywords = set()

def process_keywords(keyword_list):
    for k in keyword_list:
        if api_choice == "Naver":
            articles = fetch_naver_news(k, start_date, end_date, filters)
        else:
            articles = []  # NewsAPI 비활성 처리 중
        search_results[k] = articles
        show_limit[k] = 5
        send_to_telegram(k, articles[:5])

def send_to_telegram(keyword, articles):
    if articles:
        msg = f"*🔔 {keyword} 관련 상위 뉴스 5건:*\n"
        for a in articles:
            msg += f"- [{a['title']}]({a['link']})\n"
        Telegram().send_message(msg)

# --- 직접 검색 ---
if search_clicked and keywords_input:
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        with st.spinner("뉴스 검색 중..."):
            process_keywords(keyword_list)

# --- 즐겨찾기 검색 ---
if fav_search_clicked and fav_selected:
    with st.spinner("뉴스 검색 중..."):
        process_keywords(fav_selected)

# --- 더보기 동작 처리 ---
for keyword in expanded_keywords:
    show_limit[keyword] += 10

if search_results:
    render_articles_columnwise(search_results, show_limit, expanded_keywords)
