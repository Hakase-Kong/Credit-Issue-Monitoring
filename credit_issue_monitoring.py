# 기존 코드와 통합되도록 전체 구성된 코드 (GNews 연동 + 더보기 문제 해결)

import streamlit as st
import requests
import re
from datetime import datetime
import telepot

# --- API 키 설정 ---
NAVER_CLIENT_ID = "_qXuzaBGk_jQesRRPRvu"
NAVER_CLIENT_SECRET = "lZc2gScgNq"
GNEWS_API_KEY = "b8c6d82bbdee9b61d2b9605f44ca8540"

# --- 텔레그램 설정 ---
TELEGRAM_TOKEN = "7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ"
TELEGRAM_CHAT_ID = "-1002404027768"

# --- 키워드 ---
credit_keywords = ["신용등급", "신용하향", "신용상향", "등급조정", "부정적", "긍정적", "평가"]
finance_keywords = ["적자", "흑자", "부채", "차입금", "현금흐름", "영업손실", "순이익", "부도", "파산"]
all_filter_keywords = sorted(set(credit_keywords + finance_keywords))
favorite_keywords = set()

# --- 신용위험 키워드 필터 초기값 ---
default_credit_issue_patterns = [
    "신용등급", "신용평가", "하향", "상향", "강등", "조정", "부도",
    "파산", "디폴트", "채무불이행", "적자", "영업손실", "현금흐름", "자금난",
    "재무위험", "부정적 전망", "긍정적 전망", "기업회생", "워크아웃", "구조조정", "자본잠식"
]

class Telegram:
    def __init__(self):
        self.bot = telepot.Bot(token=TELEGRAM_TOKEN)

    def send_message(self, message):
        self.bot.sendMessage(TELEGRAM_CHAT_ID, message, parse_mode="Markdown")

def is_credit_risk_news(text, keywords):
    for word in keywords:
        if re.search(word, text, re.IGNORECASE):
            return True
    return False

def filter_by_issues(title, desc, selected_keywords):
    content = title + " " + desc
    if st.session_state.enable_credit_filter and not is_credit_risk_news(content, st.session_state.credit_filter_keywords):
        return False
    return True

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
            if not filter_by_issues(title, desc, []):
                continue
            articles.append({
                "title": re.sub("<.*?>", "", title),
                "link": item["link"],
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "Naver"
            })
    return articles[:limit]

def fetch_gnews_news(query, limit=100):
    articles = []
    try:
        url = "https://gnews.io/api/v4/search"
        params = {
            "q": query,
            "lang": "en",
            "token": GNEWS_API_KEY,
            "max": limit
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            st.warning(f"❌ GNews 요청 실패 - 상태 코드: {response.status_code}")
            return []

        data = response.json()
        for item in data.get("articles", []):
            title = item.get("title", "")
            desc = item.get("description", "")
            if not filter_by_issues(title, desc, []):
                continue
            pub_date = datetime.strptime(item["publishedAt"][:10], "%Y-%m-%d").date()
            articles.append({
                "title": title,
                "link": item.get("url", ""),
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "GNews"
            })
    except Exception as e:
        st.warning(f"⚠️ GNews 접근 오류: {e}")
    return articles

def render_articles_columnwise(results):
    cols = st.columns(len(results))
    for idx, (keyword, articles) in enumerate(results.items()):
        with cols[idx]:
            st.markdown(f"### 📁 {keyword}")
            show_n = st.session_state.show_limit.get(keyword, 5)
            for article in articles[:show_n]:
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
            if show_n < len(articles):
                if st.button(f"더보기", key=f"more_{keyword}"):
                    st.session_state.show_limit[keyword] += 5

def is_english(text):
    return all(ord(c) < 128 for c in text if c.isalpha())

def send_to_telegram(keyword, articles):
    if articles:
        msg = f"*[{keyword}] 관련 상위 뉴스 5건:*
"
        for a in articles:
            title = re.sub(r"[\U00010000-\U0010ffff]", "", a['title'])
            msg += f"- [{title}]({a['link']})\n"
        try:
            Telegram().send_message(msg)
        except Exception as e:
            st.warning(f"텔레그램 전송 오류: {e}")

def process_keywords(keyword_list, start_date, end_date):
    for k in keyword_list:
        if is_english(k):
            articles = fetch_gnews_news(k)
        else:
            articles = fetch_naver_news(k, start_date, end_date)
        st.session_state.search_results[k] = articles
        st.session_state.show_limit[k] = 5
        send_to_telegram(k, articles[:5])

# --- Streamlit 초기 설정 ---
st.set_page_config(layout="wide")
st.markdown("<h1 style='color:#1a1a1a;'>📊 Credit Issue Monitoring</h1>", unsafe_allow_html=True)

# --- 세션 상태 초기화 ---
for key in ["search_results", "show_limit", "expanded_keywords"]:
    if key not in st.session_state:
        st.session_state[key] = {} if key != "expanded_keywords" else set()

# --- UI 입력 ---
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

with st.expander("🛡️ 신용위험 필터 옵션"):
    st.session_state.enable_credit_filter = st.checkbox("신용위험 뉴스만 필터링", value=True)
    st.session_state.credit_filter_keywords = st.multiselect(
        "신용위험 관련 키워드 (하나 이상 선택)",
        options=default_credit_issue_patterns,
        default=default_credit_issue_patterns
    )

fav_col1, fav_col2 = st.columns([5, 1])
with fav_col1:
    fav_selected = st.multiselect("⭐ 즐겨찾기에서 검색", sorted(favorite_keywords))
with fav_col2:
    fav_search_clicked = st.button("즐겨찾기로 검색")

if search_clicked and keywords_input:
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        with st.spinner("뉴스 검색 중..."):
            process_keywords(keyword_list, start_date, end_date)

if fav_search_clicked and fav_selected:
    with st.spinner("뉴스 검색 중..."):
        process_keywords(fav_selected, start_date, end_date)

if st.session_state.search_results:
    render_articles_columnwise(st.session_state.search_results)
