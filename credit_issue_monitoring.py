import streamlit as st
from newsapi import NewsApiClient
import requests
import re
from datetime import datetime
import telepot

# --- API 키 설정 ---
NAVER_CLIENT_ID = "_qXuzaBGk_jQesRRPRvu"
NAVER_CLIENT_SECRET = "lZc2gScgNq"
NEWS_API_KEY = "3a33b7b756274540926aeea8df60637c"

# --- 텔레그램 설정 ---
TELEGRAM_TOKEN = "7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ"
TELEGRAM_CHAT_ID = "-1002404027768"

# --- 키워드 ---
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
    return all(re.search(k, content) for k in selected_keywords)

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

def fetch_newsapi_news(query, start_date=None, end_date=None, filters=None, limit=100, language="en"):
    newsapi = NewsApiClient(api_key=NEWS_API_KEY)
    articles = []
    try:
        data = newsapi.get_everything(
            q=query,
            from_param=start_date.strftime("%Y-%m-%d") if start_date else None,
            to=end_date.strftime("%Y-%m-%d") if end_date else None,
            language=language,
            sort_by="publishedAt",
            page_size=100
        )
        for item in data.get("articles", []):
            title = item.get("title", "")
            desc = item.get("description", "")
            if filters and not filter_by_issues(title, desc, filters):
                continue
            pub_date = datetime.strptime(item["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").date()
            articles.append({
                "title": title,
                "link": item.get("url", ""),
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "NewsAPI"
            })
    except Exception as e:
        st.warning(f"NewsAPI 접근 오류: {e}")
    return articles[:limit]

def render_articles_columnwise(results, show_limit, expanded_keywords):
    cols = st.columns(len(results))
    for idx, (keyword, articles) in enumerate(results.items()):
        with cols[idx]:
            st.markdown(f"### 📁 {keyword}")
            articles_to_show = articles[:show_limit.get(keyword, 5)]
            for article in articles_to_show:
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
            if len(articles) > show_limit.get(keyword, 5):
                if st.button(f"더보기", key=f"more_{keyword}"):
                    expanded_keywords.add(keyword)
                    show_limit[keyword] += 5

st.set_page_config(layout="wide")

st.markdown("<h1 style='color:#1a1a1a;'>📊 Credit Issue Monitoring</h1>", unsafe_allow_html=True)

api_choice = st.selectbox("API 선택", ["Naver", "NewsAPI"])
language = st.selectbox("뉴스 언어 설정 (NewsAPI만 해당)", ["en", "de", "fr", "it", "es", "ru", "zh"])

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

search_results = {}
show_limit = {}
expanded_keywords = set()

def send_to_telegram(keyword, articles):
    if articles:
        msg = f"*[{keyword}] 관련 상위 뉴스 5건:*\n"
        for a in articles:
            title = re.sub(r"[\U00010000-\U0010ffff]", "", a['title'])
            msg += f"- [{title}]({a['link']})\n"
        try:
            Telegram().send_message(msg)
        except Exception as e:
            st.warning(f"텔레그램 전송 오류: {e}")

def process_keywords(keyword_list):
    for k in keyword_list:
        if api_choice == "Naver":
            articles = fetch_naver_news(k, start_date, end_date, filters)
        else:
            articles = fetch_newsapi_news(k, start_date, end_date, filters, language=language)
        search_results[k] = articles
        show_limit[k] = 5
        st.session_state.show_limit[k] = 5
        send_to_telegram(k, articles[:5])

if "show_limit" not in st.session_state:
    st.session_state.show_limit = {}
if "expanded_keywords" not in st.session_state:
    st.session_state.expanded_keywords = set()

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

for keyword in st.session_state.expanded_keywords:
    if keyword in show_limit:
        show_limit[keyword] += 10

if search_results:
    render_articles_columnwise(search_results, show_limit, st.session_state.expanded_keywords)
