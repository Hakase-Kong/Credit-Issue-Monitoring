import nltk

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

import streamlit as st
import pandas as pd
from io import BytesIO
import requests
import re
import os
from datetime import datetime
import telepot
from openai import OpenAI
import newspaper  # newspaper3k

# --- CSS 스타일 ---
st.markdown("""
<style>
[data-testid="column"] > div { gap: 0rem !important; }
.stMultiSelect [data-baseweb="tag"] { background-color: #ff5c5c !important; color: white !important; border: none !important; font-weight: bold; }
.sentiment-badge { display: inline-block; padding: 0.08em 0.6em; margin-left: 0.2em; border-radius: 0.8em; font-size: 0.85em; font-weight: bold; vertical-align: middle; }
.sentiment-positive { background: #2ecc40; color: #fff; }
.sentiment-negative { background: #ff4136; color: #fff; }
.stBox { background: #fcfcfc; border-radius: 0.7em; border: 1.5px solid #e0e2e6; margin-bottom: 1.2em; padding: 1.1em 1.2em 1.2em 1.2em; box-shadow: 0 2px 8px 0 rgba(0,0,0,0.03); }
.flex-row-bottom { display: flex; align-items: flex-end; gap: 0.5rem; margin-bottom: 0.5rem; }
.flex-grow { flex: 1 1 0%; }
.flex-btn { min-width: 90px; }
</style>
""", unsafe_allow_html=True)

# --- 제외 키워드 ---
EXCLUDE_TITLE_KEYWORDS = [
    "야구", "축구", "배구", "농구", "골프", "e스포츠", "올림픽", "월드컵", "K리그", "프로야구", "프로축구", "프로배구", "프로농구",
    "부고", "인사", "승진", "임명", "발령", "인사발령", "인사이동",
    "브랜드평판", "브랜드 평판", "브랜드 순위", "브랜드지수",
    "코스피", "코스닥", "주가", "주식", "증시", "시세", "마감", "장중", "장마감", "거래량", "거래대금", "상한가", "하한가"
]

def exclude_by_title_keywords(title, exclude_keywords):
    for word in exclude_keywords:
        if word in title:
            return True
    return False

# --- 세션 상태 변수 초기화 ---
if "favorite_keywords" not in st.session_state:
    st.session_state.favorite_keywords = set()
if "search_results" not in st.session_state:
    st.session_state.search_results = {}
if "show_limit" not in st.session_state:
    st.session_state.show_limit = {}
if "search_triggered" not in st.session_state:
    st.session_state.search_triggered = False
if "selected_articles" not in st.session_state:
    st.session_state.selected_articles = []

# --- 산업별 필터 옵션 ---
industry_filter_categories = {
    "은행 및 금융지주": {
        "keywords": [
            "경영실태평가", "BIS", "CET1", "자본비율", "상각형 조건부자본증권", "자본확충", "자본여력", "자본적정성", "LCR",
            "조달금리", "NIM", "순이자마진", "고정이하여신비율", "대손충당금", "충당금", "부실채권", "연체율", "가계대출", "취약차주"
        ],
        "companies": [
            "신한금융", "하나금융", "KB금융", "농협금융", "우리금융",
            "농협은행", "국민은행", "신한은행", "우리은행", "하나은행"
        ]
    },
    "보험사": {
        "keywords": [
            "보장성보험", "저축성보험", "변액보험", "퇴직연금", "일반보험", "자동차보험", "ALM", "지급여력비율", "K-ICS",
            "보험수익성", "보험손익", "수입보험료", "CSM", "상각", "투자손익", "운용성과", "IFRS4", "IFRS17", "보험부채",
            "장기선도금리", "최종관찰만기", "유동성 프리미엄", "신종자본증권", "후순위채", "위험자산비중", "가중부실자산비율"
        ],
        "companies": [
            "현대해상", "농협생명", "메리츠화재", "교보생명", "삼성화재", "삼성생명",
            "신한라이프", "흥국생명", "동양생명", "미래에셋생명"
        ]
    },
    # ... 이하 동일하게 모든 섹터 추가 ...
}

# --- 공통 필터 옵션(대분류/소분류 없이 모두 적용) ---
common_filter_categories = {
    "신용/등급": [
        "신용등급", "등급전망", "하락", "강등", "하향", "상향", "디폴트", "부실", "부도", "미지급", "수요 미달", "미매각", "제도 개편", "EOD"
    ],
    "수요/공급": [
        "수요", "공급", "수급", "둔화", "위축", "성장", "급등", "급락", "상승", "하락", "부진", "심화"
    ],
    "실적/재무": [
        "실적", "매출", "영업이익", "적자", "손실", "비용", "부채비율", "이자보상배율"
    ],
    "자금/조달": [
        "차입", "조달", "설비투자", "회사채", "발행", "인수", "매각"
    ],
    "구조/조정": [
        "M&A", "합병", "계열 분리", "구조조정", "다각화", "구조 재편"
    ],
    "거시/정책": [
        "금리", "환율", "관세", "무역제재", "보조금", "세액 공제", "경쟁"
    ],
    "지배구조/법": [
        "횡령", "배임", "공정거래", "오너리스크", "대주주", "지배구조"
    ]
}
ALL_COMMON_FILTER_KEYWORDS = []
for keywords in common_filter_categories.values():
    ALL_COMMON_FILTER_KEYWORDS.extend(keywords)

# --- UI 시작 ---
st.set_page_config(layout="wide")
col_title, col_option1, col_option2 = st.columns([0.6, 0.2, 0.2])
with col_title:
    st.markdown("<h1 style='color:#1a1a1a; margin-bottom:0.5rem;'>📊 Credit Issue Monitoring</h1>", unsafe_allow_html=True)
with col_option1:
    show_sentiment_badge = st.checkbox("기사목록에 감성분석 배지 표시", value=False, key="show_sentiment_badge")
with col_option2:
    enable_summary = st.checkbox("요약 기능 적용", value=True, key="enable_summary")

# 1. 키워드 입력/검색 버튼 (한 줄, 버튼 오른쪽)
col_kw_input, col_kw_btn = st.columns([0.8, 0.2])
with col_kw_input:
    keywords_input = st.text_input("키워드 (예: 삼성, 한화)", value="", key="keyword_input", label_visibility="visible")
with col_kw_btn:
    search_clicked = st.button("검색", key="search_btn", help="키워드로 검색", use_container_width=True)

# 날짜 입력
date_col1, date_col2 = st.columns([1, 1])
with date_col1:
    start_date = st.date_input("시작일")
with date_col2:
    end_date = st.date_input("종료일")

# --- 공통 필터 옵션 (항상 적용, 전체 키워드 가시적으로 표시) ---
with st.expander("🧩 공통 필터 옵션 (항상 적용됨)"):
    for major, subs in common_filter_categories.items():
        st.markdown(f"**{major}**: {', '.join(subs)}")

# --- 산업별 필터 옵션 (메인 검색 트리거) ---
with st.expander("🏭 산업별 필터 옵션"):
    sector_options = list(industry_filter_categories.keys())
    selected_sectors = st.multiselect(
        "대분류(섹터) 선택 (복수 선택 가능, 엔터로 검색)",
        sector_options,
        key="industry_majors"
    )

    selected_keywords = sorted(set(
        kw
        for sector in selected_sectors
        for kw in industry_filter_categories[sector]["keywords"]
    )) if selected_sectors else []

    # 섹터 선택이 바뀌면 바로 검색 트리거
    if selected_sectors:
        st.session_state["use_industry_filter"] = True
        st.session_state["industry_sub"] = selected_keywords
        st.session_state["search_triggered"] = True
    else:
        st.session_state["use_industry_filter"] = False
        st.session_state["industry_sub"] = []
        st.session_state["search_triggered"] = False

# --- 키워드 필터 옵션 (하단으로 이동) ---
with st.expander("🔍 키워드 필터 옵션"):
    require_keyword_in_title = st.checkbox("기사 제목에 키워드가 포함된 경우만 보기", value=False, key="require_keyword_in_title")
    require_exact_keyword_in_title_or_content = st.checkbox("키워드가 온전히 제목 또는 본문에 포함된 기사만 보기", value=False, key="require_exact_keyword_in_title_or_content")

# --- 본문 추출 함수 ---
def extract_article_text(url):
    try:
        article = newspaper.article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        return f"본문 추출 오류: {e}"

# --- OpenAI 요약/감성분석 함수 ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def detect_lang(text):
    return "ko" if re.search(r"[가-힣]", text) else "en"

def summarize_and_sentiment_with_openai(text, do_summary=True):
    if not OPENAI_API_KEY:
        return "OpenAI API 키가 설정되지 않았습니다.", None, None, None
    lang = detect_lang(text)
    if lang == "ko":
        prompt = (
            ("아래 기사 본문을 감성분석(긍정/부정만)하고" +
             ("\n- [한 줄 요약]: 기사 전체 내용을 한 문장으로 요약" if do_summary else "") +
             "\n- [감성]: 기사 전체의 감정을 긍정/부정 중 하나로만 답해줘. 중립은 절대 답하지 마. 파산, 자금난 등 부정적 사건이 중심이면 반드시 '부정'으로 답해줘.\n\n"
             "아래 포맷으로 답변해줘:\n" +
             ("[한 줄 요약]: (여기에 한 줄 요약)\n" if do_summary else "") +
             "[감성]: (긍정/부정 중 하나만)\n\n"
             "[기사 본문]\n" + text)
        )
    else:
        prompt = (
            ("Analyze the following news article for sentiment (positive/negative only)." +
             ("\n- [One-line Summary]: Summarize the entire article in one sentence." if do_summary else "") +
             "\n- [Sentiment]: Classify the overall sentiment as either positive or negative ONLY. Never answer 'neutral'. If the article is about bankruptcy, crisis, etc., answer 'negative'.\n\n"
             "Respond in this format:\n" +
             ("[One-line Summary]: (your one-line summary)\n" if do_summary else "") +
             "[Sentiment]: (positive/negative only)\n\n"
             "[ARTICLE]\n" + text)
        )
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt}
        ],
        max_tokens=1024,
        temperature=0.3
    )
    answer = response.choices[0].message.content.strip()
    if lang == "ko":
        m1 = re.search(r"\[한 줄 요약\]:\s*(.+)", answer)
        m3 = re.search(r"\[감성\]:\s*(.+)", answer)
    else:
        m1 = re.search(r"\[One-line Summary\]:\s*(.+)", answer)
        m3 = re.search(r"\[Sentiment\]:\s*(.+)", answer)
    one_line = m1.group(1).strip() if (do_summary and m1) else ""
    summary = ""  # 상세 요약은 생략
    sentiment = m3.group(1).strip() if m3 else ""
    # 후처리: 중립 등 들어오면 부정으로 강제
    if sentiment.lower() in ['neutral', '중립', '']:
        sentiment = '부정' if lang == "ko" else 'negative'
    if lang == "en":
        sentiment = '긍정' if sentiment.lower() == 'positive' else '부정'
    return one_line, summary, sentiment, text

NAVER_CLIENT_ID = "_qXuzaBGk_jQesRRPRvu"
NAVER_CLIENT_SECRET = "lZc2gScgNq"
TELEGRAM_TOKEN = "7033950842:AAFk4pSb5qtNj435Gf2B5-rPlFrlNqhZFuQ"
TELEGRAM_CHAT_ID = "-1002404027768"

class Telegram:
    def __init__(self):
        self.bot = telepot.Bot(TELEGRAM_TOKEN)
        self.chat_id = TELEGRAM_CHAT_ID

    def send_message(self, message):
        self.bot.sendMessage(self.chat_id, message, parse_mode="Markdown", disable_web_page_preview=True)

def filter_by_issues(title, desc, selected_keywords, require_keyword_in_title=False):
    if require_keyword_in_title and selected_keywords:
        if not any(kw.lower() in title.lower() for kw in selected_keywords):
            return False
    return True

def fetch_naver_news(query, start_date=None, end_date=None, limit=1000, require_keyword_in_title=False):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    articles = []
    for start in range(1, 1001, 100):
        if len(articles) >= limit:
            break
        params = {
            "query": query,
            "display": 100,
            "start": start,
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
            if not filter_by_issues(title, desc, [query], require_keyword_in_title):
                continue
            if exclude_by_title_keywords(re.sub("<.*?>", "", title), EXCLUDE_TITLE_KEYWORDS):
                continue
            articles.append({
                "title": re.sub("<.*?>", "", title),
                "link": item["link"],
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "Naver"
            })
        if len(items) < 100:
            break
    return articles[:limit]

def fetch_gnews_news(query, start_date=None, end_date=None, limit=100, require_keyword_in_title=False):
    GNEWS_API_KEY = "b8c6d82bbdee9b61d2b9605f44ca8540"
    articles = []
    try:
        url = f"https://gnews.io/api/v4/search"
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
            if not filter_by_issues(title, desc, [query], require_keyword_in_title):
                continue
            if exclude_by_title_keywords(title, EXCLUDE_TITLE_KEYWORDS):
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

def is_english(text):
    return all(ord(c) < 128 for c in text if c.isalpha())

# --- 중복 기사 제거 함수 ---
def remove_duplicate_articles(articles):
    seen = set()
    unique_articles = []
    for article in articles:
        link = article.get("link")
        if link and link not in seen:
            unique_articles.append(article)
            seen.add(link)
    return unique_articles

def process_keywords(keyword_list, start_date, end_date, require_keyword_in_title=False):
    for k in keyword_list:
        if is_english(k):
            articles = fetch_gnews_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        else:
            articles = fetch_naver_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        articles = remove_duplicate_articles(articles)
        st.session_state.search_results[k] = articles
        if k not in st.session_state.show_limit:
            st.session_state.show_limit[k] = 5

def detect_lang_from_title(title):
    return "ko" if re.search(r"[가-힣]", title) else "en"

def summarize_article_from_url(article_url, title, do_summary=True):
    try:
        full_text = extract_article_text(article_url)
        if full_text.startswith("본문 추출 오류"):
            return full_text, None, None, None
        one_line, summary, sentiment, _ = summarize_and_sentiment_with_openai(full_text, do_summary=do_summary)
        return one_line, summary, sentiment, full_text
    except Exception as e:
        return f"요약 오류: {e}", None, None, None

def or_keyword_filter(article, *keyword_lists):
    text = (article.get("title", "") + " " + article.get("description", "") + " " + article.get("full_text", ""))
    for keywords in keyword_lists:
        if any(kw in text for kw in keywords if kw):
            return True
    return False

def article_contains_exact_keyword(article, keywords):
    title = article.get("title", "")
    content = ""
    cache_key = article.get("link", "")
    summary_cache_key = None
    for key in st.session_state.keys():
        if key.startswith("summary_") and cache_key in key:
            summary_cache_key = key
            break
    if summary_cache_key and isinstance(st.session_state[summary_cache_key], tuple):
        _, _, _, content = st.session_state[summary_cache_key]
    for kw in keywords:
        if kw and (kw in title or (content and kw in content)):
            return True
    return False

search_clicked = False
if keywords_input:
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        search_clicked = True

# --- 검색 트리거: 키워드 입력 or 산업별 필터 선택 시 ---
if search_clicked or st.session_state.get("search_triggered"):
    # 키워드 입력이 있으면 해당 키워드로, 없으면 산업별 필터 키워드로 검색
    if keywords_input:
        keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    else:
        keyword_list = st.session_state.get("industry_sub", [])
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    elif keyword_list:
        with st.spinner("뉴스 검색 중..."):
            process_keywords(keyword_list, start_date, end_date, require_keyword_in_title=st.session_state.get("require_keyword_in_title", False))
    st.session_state.search_triggered = False

# --- 기사 필터링 함수 ---
def article_passes_all_filters(article):
    filters = []
    # 공통 필터 항상 적용
    filters.append(ALL_COMMON_FILTER_KEYWORDS)
    # 산업별 필터 사용 시 적용
    if st.session_state.get("use_industry_filter", False):
        filters.append(st.session_state.get("industry_sub", []))
    # 제외 키워드
    if exclude_by_title_keywords(article.get('title', ''), EXCLUDE_TITLE_KEYWORDS):
        return False
    # 키워드 정확 포함 옵션
    if st.session_state.get("require_exact_keyword_in_title_or_content", False):
        all_keywords = []
        if keywords_input:
            all_keywords.extend([k.strip() for k in keywords_input.split(",") if k.strip()])
        if st.session_state.get("industry_sub"):
            all_keywords.extend(st.session_state["industry_sub"])
        if not article_contains_exact_keyword(article, all_keywords):
            return False
    return or_keyword_filter(article, *filters)

def safe_title(val):
    if pd.isnull(val) or str(val).strip() == "" or str(val).lower() == "nan" or str(val) == "0":
        return "제목없음"
    return str(val)

def get_excel_download_with_favorite_and_excel_company_col(summary_data, favorite_categories, excel_company_categories):
    # ... (생략, 기존 코드 동일) ...
    return output

def render_articles_with_single_summary_and_telegram(results, show_limit, show_sentiment_badge=True, enable_summary=True):
    # ... (생략, 기존 코드 동일) ...
    pass

if st.session_state.search_results:
    filtered_results = {}
    for keyword, articles in st.session_state.search_results.items():
        filtered_articles = [a for a in articles if article_passes_all_filters(a)]
        if filtered_articles:
            filtered_results[keyword] = filtered_articles
    render_articles_with_single_summary_and_telegram(
        filtered_results,
        st.session_state.show_limit,
        show_sentiment_badge=st.session_state.get("show_sentiment_badge", False),
        enable_summary=st.session_state.get("enable_summary", True)
    )
