import streamlit as st
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
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

class Telegram:
    def __init__(self):
        self.bot = telepot.Bot(token=TELEGRAM_TOKEN)

    def send_message(self, message):
        self.bot.sendMessage(TELEGRAM_CHAT_ID, message, parse_mode="Markdown")

def filter_by_issues(title, desc, selected_keywords):
    content = title + " " + desc
    return any(re.search(k, content) for k in selected_keywords) if selected_keywords else True

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
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "Naver"
            })
    return articles[:limit]

def render_articles_columnwise(results):
    cols = st.columns(len(results))
    for idx, (keyword, articles) in enumerate(results.items()):
        with cols[idx]:
            with st.container():
                st.markdown(f"### \ud83d\udcc1 {keyword}")
                articles_to_show = articles[:st.session_state.show_limit.get(keyword, 5)]

                for article in articles_to_show:
                    with st.container():
                        st.markdown(f"""
                            <div style='margin-bottom: 12px; padding: 10px; border: 1px solid #eee; border-radius: 10px; background-color: #fafafa;'>
                                <div style='font-weight: bold; font-size: 15px; margin-bottom: 4px;'>
                                    <a href="{article['link']}" target="_blank" style='text-decoration: none; color: #1155cc;'>
                                        {article['title']}
                                    </a>
                                </div>
                                <div style='font-size: 12px; color: gray;'>
                                    {article['date']} | {article['source']}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                if len(articles) > st.session_state.show_limit.get(keyword, 5):
                    if st.button(f"더보기", key=f"more_{keyword}"):
                        st.session_state.show_limit[keyword] += 5
                        st.session_state.expanded_keywords.add(keyword)

# --- Streamlit 시작 ---
st.set_page_config(layout="wide")

# --- 스타일 ---
st.markdown("""
    <style>
        .stButton>button {
            height: 3em;
            width: 100%;
            font-size: 1.2em;
            margin: 0.2em 0;
        }
        .stTextInput>div>div>input {
            font-size: 0.9em;
        }
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 1rem;
        }
        .stTextInput {
            margin-bottom: 1em;
        }
        .stMarkdown ul {
            margin-left: 20px;
            margin-bottom: 0.5em;
        }
        .stMarkdown {
            margin-top: 0.5em;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='color:#1a1a1a;'>\ud83d\udcca Credit Issue Monitoring</h1>", unsafe_allow_html=True)

# --- 세션 상태 초기화 ---
if "show_limit" not in st.session_state:
    st.session_state.show_limit = {}
if "expanded_keywords" not in st.session_state:
    st.session_state.expanded_keywords = set()
if "search_results" not in st.session_state:
    st.session_state.search_results = {}

# --- UI 입력 ---
api_choice = st.selectbox("API 선택", ["Naver", "NewsAPI"])
col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    keywords_input = st.text_input("\ud83d\udd0d \ud0a4\uc6cc\ub4dc (예: 삼성, 한화)", value="")
with col2:
    search_clicked = st.button("검색")
with col3:
    if st.button("\u2b50 \uc990\uaca8\ucc45\uae30 \ucd94\uac00"):
        new_keywords = {kw.strip() for kw in keywords_input.split(",") if kw.strip()}
        favorite_keywords.update(new_keywords)
        st.success("\uc990\uaca8\ucc45\uc5d0 \ucd94\uac00\ub418\uc5c8\uc2b5\ub2c8\ub2e4.")

start_date = st.date_input("시작일")
end_date = st.date_input("종료일")
filters = st.multiselect("\u2b50 \ud544\ud130\ub9c1 \ud0a4\uc6cc\ub4dc \uc120\ud0dd", all_filter_keywords)

fav_col1, fav_col2 = st.columns([5, 1])
with fav_col1:
    fav_selected = st.multiselect("\u2b50 \uc990\uaca8\ucc45\uae30\uc5d0\uc11c \uac80\uc0c9", sorted(favorite_keywords))
with fav_col2:
    fav_search_clicked = st.button("\uc990\uaca8\ucc45\uae30\ub85c \uac80\uc0c9")

# --- 텔레그램 전송 함수 ---
def send_to_telegram(keyword, articles):
    if articles:
        msg = f"*[{keyword}] 관련 상위 뉴스 5건:*\n"
        for a in articles:
            title = re.sub(r"[\U00010000-\U0010ffff]", "", a['title'])  # 이모지 제거
            msg += f"- [{title}]({a['link']})\n"
        try:
            Telegram().send_message(msg)
        except Exception as e:
            st.warning(f"텔레그램 전송 오류: {e}")

# --- 뉴스 검색 및 처리 ---
def process_keywords(keyword_list):
    for k in keyword_list:
        if api_choice == "Naver":
            articles = fetch_naver_news(k, start_date, end_date, filters)
        else:
            articles = []
        st.session_state.search_results[k] = articles
        st.session_state.show_limit[k] = 5
        send_to_telegram(k, articles[:5])

# --- 사용자 입력 처리 ---
if search_clicked and keywords_input:
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        with st.spinner("뉴스 검색 중..."):
            process_keywords(keyword_list)

if fav_search_clicked and fav_selected:
    with st.spinner("뉴스 검색 중..."):
        process_keywords(fav_selected)

# --- 결과 렌더링 ---
if st.session_state.search_results:
    render_articles_columnwise(st.session_state.search_results)
