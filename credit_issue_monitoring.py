    if st.session_state.get("use_industry_filter", False):
        filters.append(st.session_state.get("industry_sub", []))
    if exclude_by_title_keywords(article.get('title', ''), EXCLUDE_TITLE_KEYWORDS):
        return False
    if st.session_state.get("require_exact_keyword_in_title_or_content", False):
        all_keywords = []
        if keywords_input:
            all_keywords.extend([k.strip() for k in keywords_input.split(",") if k.strip()])
        if selected_categories:
            for cat in selected_categories:
                all_keywords.extend(favorite_categories[cat])
        if not article_contains_exact_keyword(article, all_keywords):
            return False
    return or_keyword_filter(article, *filters)

def extract_article_text(url):
    try:
        article = newspaper.Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        return f"본문 추출 오류: {e}"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def detect_lang(text):
    return "ko" if re.search(r"[가-힣]", text) else "en"

@st.cache_data(show_spinner=False, max_entries=1000)
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
    summary = ""
    sentiment = m3.group(1).strip() if m3 else ""
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

def process_keywords_parallel(keyword_list, start_date, end_date, require_keyword_in_title=False):
    progress_placeholder = st.empty()
    st.session_state.raw_articles = {}
    search_results = {}
    def fetch_for_keyword(k):
        if is_english(k):
            articles = fetch_gnews_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        else:
            articles = fetch_naver_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        return k, articles
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_for_keyword, k): k for k in keyword_list}
        for i, future in enumerate(futures):
            k, articles = future.result()
            search_results[k] = articles
            st.session_state.raw_articles[k] = articles
            if k not in st.session_state.show_limit:
                st.session_state.show_limit[k] = 5
            progress_placeholder.info(f"'{k}' 뉴스 {len(articles)}건 수집 완료 ({i+1}/{len(keyword_list)})")
    st.session_state.search_results = search_results
    progress_placeholder.empty()
    render_articles_with_single_summary_and_telegram(
        search_results,
        st.session_state.show_limit,
        show_sentiment_badge=st.session_state.get("show_sentiment_badge", False),
        enable_summary=st.session_state.get("enable_summary", False)
    )

def detect_lang_from_title(title):
    return "ko" if re.search(r"[가-힣]", title) else "en"

def summarize_article_from_url(article_url, title, do_summary=True):
    full_text = extract_article_text(article_url)
    if full_text.startswith("본문 추출 오류"):
        return full_text, None, None, None
    return summarize_and_sentiment_with_openai(full_text, do_summary=do_summary)

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

# --- 체크박스 상태 변화 감지 및 즉시 요약/감성분석 실행용 변수 초기화 ---
if "article_checked_prev" not in st.session_state:
    st.session_state.article_checked_prev = {}

def safe_title(val):
    if pd.isnull(val) or str(val).strip() == "" or str(val).lower() == "nan" or str(val) == "0":
        return "제목없음"
    return str(val)

def get_excel_download_with_favorite_and_excel_company_col(summary_data, favorite_categories, excel_company_categories):
    # ... (동일, 생략)
    pass  # 실제 구현은 기존과 동일

def render_articles_with_single_summary_and_telegram(
    results, show_limit, show_sentiment_badge=True, enable_summary=True
):
    import hashlib

    SENTIMENT_CLASS = {
        "긍정": "sentiment-positive",
        "부정": "sentiment-negative"
    }

    if "article_checked" not in st.session_state:
        st.session_state.article_checked = {}

    if "selected_articles" not in st.session_state:
        st.session_state.selected_articles = []

    col_list, col_summary = st.columns([1, 1])
    article_global_idx = 0

    with col_list:
        st.markdown("### 검색 결과")
        for keyword, articles in results.items():
            limit = st.session_state.show_limit.get(keyword, 5)
            st.markdown(f"**[{keyword}]**")
            card_cols = st.columns(2)

            for idx, article in enumerate(articles[:limit]):
                col = card_cols[idx % 2]
                with col:
                    with st.container(border=True):
                        link_hash = hashlib.md5(article['link'].encode('utf-8')).hexdigest()
                        key = f"{keyword}_{idx}_{link_hash}"
                        checkbox_key = f"news_{key}"
                        cache_key = f"summary_{key}"

                        # 체크박스
                        checked = st.checkbox(
                            "선택",
                            value=st.session_state.article_checked.get(checkbox_key, False),
                            key=checkbox_key
                        )
                        prev_checked = st.session_state.article_checked_prev.get(checkbox_key, False)
                        st.session_state.article_checked[checkbox_key] = checked

                        # 체크박스가 False→True로 바뀌는 순간에만 요약/감성분석 실행
                        if checked and not prev_checked:
                            one_line, summary, sentiment, full_text = summarize_article_from_url(
                                article['link'], article['title'], do_summary=enable_summary
                            )
                            st.session_state[cache_key] = (one_line, summary, sentiment, full_text)

                        st.session_state.article_checked_prev[checkbox_key] = checked

                        # 기사 정보
                        st.markdown(
                            f"**[{article['title']}]({article['link']})**",
                            unsafe_allow_html=True
                        )
                        st.markdown(f"{article['date']} | {article['source']}")

                        # 감성 배지 표시
                        if cache_key in st.session_state:
                            _, _, sentiment, _ = st.session_state[cache_key]
                            if show_sentiment_badge and sentiment:
                                sentiment_class = SENTIMENT_CLASS.get(sentiment, "sentiment-negative")
                                st.markdown(
                                    f"<span class='sentiment-badge {sentiment_class}'>({sentiment})</span>",
                                    unsafe_allow_html=True
                                )

                        article_global_idx += 1

            # 더보기 버튼
            if limit < len(articles):
                if st.button(f"더보기 ({keyword})", key=f"show_more_{keyword}"):
                    st.session_state.show_limit[keyword] = limit + 5
                    st.rerun()

    with col_summary:
        st.markdown("### 선택된 기사 요약/감성분석")
        selected_articles = []

        for keyword, articles in results.items():
            limit = st.session_state.show_limit.get(keyword, 5)
            for idx, article in enumerate(articles[:limit]):
                link_hash = hashlib.md5(article['link'].encode('utf-8')).hexdigest()
                key = f"{keyword}_{idx}_{link_hash}"
                checkbox_key = f"news_{key}"
                cache_key = f"summary_{key}"

                if st.session_state.article_checked.get(checkbox_key, False):
                    if cache_key not in st.session_state:
                        one_line, summary, sentiment, full_text = summarize_article_from_url(
                            article['link'], article['title'], do_summary=enable_summary
                        )
                        st.session_state[cache_key] = (one_line, summary, sentiment, full_text)
                    else:
                        one_line, summary, sentiment, full_text = st.session_state[cache_key]

                    selected_articles.append({
                        "키워드": keyword,
                        "기사제목": article.get("title", ""),
                        "날짜": article.get("date", ""),
                        "링크": article.get("link", ""),
                        "한줄요약": one_line,
                        "감성": sentiment
                    })

                    with st.container(border=True):
                        st.markdown(
                            f"**[{article['title']}]({article['link']})**",
                            unsafe_allow_html=True
                        )
                        st.markdown(f"- 날짜/출처: {article['date']} | {article['source']}")
                        if enable_summary:
                            st.markdown(f"- 한 줄 요약: {one_line}")
                        st.markdown(
                            f"- 감성분석: <span class='sentiment-badge {SENTIMENT_CLASS.get(sentiment, 'sentiment-negative')}'>({sentiment})</span>",
                            unsafe_allow_html=True
                        )

        st.session_state.selected_articles = selected_articles
        st.write(f"선택된 기사 개수: {len(selected_articles)}")

        if selected_articles:
            excel_bytes = get_excel_download_with_favorite_and_excel_company_col(
                selected_articles, favorite_categories, excel_company_categories
            )
            st.download_button(
                label="📥 엑셀 다운로드 (선택 기사 요약)",
                data=excel_bytes,
                file_name="news_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# --- 검색 트리거 ---
search_clicked = False
if keywords_input:
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        search_clicked = True

if search_clicked or st.session_state.get("search_triggered"):
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        with st.spinner("뉴스 검색 중..."):
            process_keywords_parallel(keyword_list, st.session_state["start_date"], st.session_state["end_date"], require_keyword_in_title=st.session_state.get("require_keyword_in_title", False))
    st.session_state.search_triggered = False

if category_search_clicked and selected_categories:
    with st.spinner("뉴스 검색 중..."):
        keywords = set()
        for cat in selected_categories:
            keywords.update(favorite_categories[cat])
        process_keywords_parallel(
            sorted(keywords),
            st.session_state["start_date"],
            st.session_state["end_date"],
            require_keyword_in_title=st.session_state.get("require_keyword_in_title", False)
        )

if st.session_state.search_results:
    filtered_results = {}
    for keyword, articles in st.session_state.search_results.items():
        filtered_articles = [
            a for a in articles
            if article_passes_all_filters(a)
            and st.session_state["start_date"] <= datetime.strptime(a["date"], "%Y-%m-%d").date() <= st.session_state["end_date"]
        ]
        if filtered_articles:
            filtered_results[keyword] = filtered_articles
    render_articles_with_single_summary_and_telegram(
        filtered_results,
        st.session_state.show_limit,
        show_sentiment_badge=st.session_state.get("show_sentiment_badge", False),
        enable_summary=st.session_state.get("enable_summary", False)
    )
