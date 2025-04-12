import streamlit as st
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
import pytz
import time
import concurrent.futures
import telepot

# --- API 키 설정 ---
NAVER_CLIENT_ID = "_qXuzaBGk_jQesRRPRvu"
NAVER_CLIENT_SECRET = "lZc2gScgNq"
NEWS_API_KEY = "3a33b7b756274540926aeea8df60637c"

credit_keywords = ["신용등급", "신용하향", "신용상향", "등급조정", "부정적", "긍정적", "평가"]
finance_keywords = ["적자", "흑자", "부채", "차입금", "현금흐름", "영업손실", "순이익", "부도", "파산"]
all_filter_keywords = sorted(set(credit_keywords + finance_keywords))

favorite_keywords = set()

class Telegram:
    def __init__(self):
        self.bot = telepot.Bot(token="YOUR_TELEGRAM_BOT_TOKEN")

    def sendMessage(self, message):
        self.bot.sendMessage("YOUR_TELEGRAM_CHAT_ID", message, parse_mode="Markdown")

def summarize_article(url):
    try:
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        content = ' '.join([p.get_text() for p in paragraphs])
        sentences = re.split(r'(?<=[.!?]) +', content)
        return ' '.join(sentences[:2]) if sentences else "요약 없음"
    except:
        return "요약 불가"

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
        if not items:
            break

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

            summary = summarize_article(item["link"])
            articles.append({
                "title": title,
                "link": item["link"],
                "pubDate": pub_date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Naver",
                "summary": summary
            })

    return articles

def fetch_newsapi_news(query, start_date=None, end_date=None, filters=None):
    articles = []
    for page in range(1, 6):
        params = {
            "q": query,
            "page": page,
            "pageSize": 20,
            "language": "ko",
            "sortBy": "publishedAt"
        }
        if start_date:
            params["from"] = start_date.isoformat()
        if end_date:
            params["to"] = end_date.isoformat()

        response = requests.get("https://newsapi.org/v2/everything", params=params,
                                headers={"Authorization": f"Bearer {NEWS_API_KEY}"})
        if response.status_code != 200:
            break

        items = response.json().get("articles", [])
        if not items:
            break

        for item in items:
            title, desc = item["title"], item["description"] or ""
            pub_date_obj = datetime.strptime(item["publishedAt"], '%Y-%m-%dT%H:%M:%SZ')
            if start_date and pub_date_obj.date() < start_date:
                continue
            if end_date and pub_date_obj.date() > end_date:
                continue
            if not re.search(rf"\b{re.escape(query)}\b", title + desc):
                continue
            if filters and not filter_by_issues(title, desc, filters):
                continue

            summary = summarize_article(item["url"])
            articles.append({
                "title": title,
                "link": item["url"],
                "pubDate": pub_date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                "source": item["source"]["name"],
                "summary": summary
            })

    return articles

def render_articles(query, articles):
    if not articles:
        st.markdown(f"### ❌ '{query}' 관련 뉴스 없음")
        return
    st.markdown(f"### 🔎 {query} 관련 뉴스")
    for article in articles:
        st.markdown(f"- [{article['title']}]({article['link']})")
        st.caption(f"{article['pubDate']} | {article['source']}")
        st.write(f"_{article['summary']}_")

# --- Streamlit UI 구성 ---
st.title("📊 Credit Issue Monitoring")

api_choice = st.selectbox("API 선택", ["Naver", "NewsAPI"])
keywords_input = st.text_input("🔍 키워드 (예: 삼성, 한화)")
start_date = st.date_input("시작일", value=None)
end_date = st.date_input("종료일", value=None)
filters = st.multiselect("📌 필터링 키워드 선택", all_filter_keywords)

if st.button("검색"):
    if not keywords_input:
        st.warning("키워드를 입력해주세요.")
    else:
        keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
        if len(keyword_list) > 10:
            st.error("⚠️ 키워드는 최대 10개까지 입력 가능합니다.")
        else:
            with st.spinner("뉴스 검색 중..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = []
                    for k in keyword_list:
                        if api_choice == "Naver":
                            futures.append(executor.submit(fetch_naver_news, k, start_date, end_date, filters))
                        else:
                            futures.append(executor.submit(fetch_newsapi_news, k, start_date, end_date, filters))

                    for k, future in zip(keyword_list, futures):
                        render_articles(k, future.result())

# 즐겨찾기 추가 기능
if st.button("⭐ 즐겨찾기 추가"):
    new_keywords = {kw.strip() for kw in keywords_input.split(",") if kw.strip()}
    favorite_keywords.update(new_keywords)
    st.success("즐겨찾기에 추가되었습니다.")

fav_selected = st.multiselect("⭐ 즐겨찾기에서 검색", sorted(favorite_keywords))
if st.button("즐겨찾기로 검색") and fav_selected:
    with st.spinner("뉴스 검색 중..."):
        for k in fav_selected:
            articles = fetch_naver_news(k, start_date, end_date, filters) if api_choice == "Naver" else fetch_newsapi_news(k, start_date, end_date, filters)
            render_articles(k, articles)
