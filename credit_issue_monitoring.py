import streamlit as st
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

def fetch_newsapi_news(query, start_date=None, end_date=None, filters=None, limit=100):
    articles = []
    page = 1
    page_size = 20
    total_fetched = 0

    while total_fetched < limit:
        params = {
            "q": query,
            "apiKey": NEWS_API_KEY,
            "pageSize": page_size,
            "page": page,
            "sortBy": "publishedAt",
            "language": "ko"
        }

        if start_date:
            params["from"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["to"] = end_date.strftime("%Y-%m-%d")

        response = requests.get("https://newsapi.org/v2/everything", params=params)
        if response.status_code != 200:
            st.warning(f"NewsAPI 요청 실패: {response.status_code} - {response.text}")
            break

        data = response.json()
        if data.get("status") != "ok":
            st.warning(f"NewsAPI 오류: {data.get('message')}")
            break

        items = data.get("articles", [])
        if not items:
            break

        for item in items:
            title = item["title"] or ""
            desc = item["description"] or ""
            pub_date_str = item["publishedAt"]
            try:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%dT%H:%M:%SZ").date()
            except ValueError:
                continue
            if filters and not filter_by_issues(title, desc, filters):
                continue

            articles.append({
                "title": title,
                "link": item["url"],
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": item.get("source", {}).get("name", "NewsAPI")
            })
            total_fetched += 1
            if total_fetched >= limit:
                break
        page += 1

    return articles

def render_articles_columnwise(results, show_limit, expanded_keywords):
    cols = st.columns(len(results))
    for idx, (keyword, articles) in enumerate(results.items()):
        with cols[idx]:
            with st.container():
                st.markdown(f"### 📁 {keyword}")
                articles_to_show = articles[:show_limit.get(keyword, 5)]

                for article in articles_to_show:
                    with st.container():
                        st.markdown(f"""
                            <div style='margin-bottom: 12px; padding: 10px; border: 1px solid #eee; border-radius: 10px; background-color: #fafafa;'>
                                <div style='font-weight: bold; font-size: 15px; margin-bottom: 4px;'>
                                    <a href="{article['link']}" target="_blank" style='text-decoration: none; color: #1155cc;'>
                                        {article['title']}
                                    </a>
                                </div>
                                <div style='
::contentReference[oaicite:11]{index=11}
 
