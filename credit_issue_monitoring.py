def render_articles_with_single_summary_and_telegram(results, show_limit, show_sentiment_badge=True, enable_summary=True):
    SENTIMENT_CLASS = {
        "긍정": "sentiment-positive",
        "부정": "sentiment-negative"
    }

    # ✅ Show limit 초기화 (검색 후 최초 실행 시에만 init)
    for keyword in results.keys():
        if keyword not in st.session_state.show_limit:
            st.session_state.show_limit[keyword] = 5

    if "article_checked" not in st.session_state:
        st.session_state.article_checked = {}

    col_list, col_summary = st.columns([1, 1])

    with col_list:
        st.markdown("### 기사 요약 결과")

        for keyword, articles in results.items():
            with st.container(border=True):
                st.markdown(f"**[{keyword}]**")
                limit = st.session_state.show_limit[keyword]

                for article in articles[:limit]:
                    link_hash = re.sub(r'\W+', '', article['link'])[-12:]
                    key = f"{keyword}_{link_hash}"
                    cache_key = f"summary_{key}"

                    if cache_key not in st.session_state:
                        one_line, summary, sentiment, full_text = summarize_article_from_url(
                            article['link'], article['title'], do_summary=enable_summary
                        )
                        st.session_state[cache_key] = (one_line, summary, sentiment, full_text)
                    else:
                        one_line, summary, sentiment, full_text = st.session_state[cache_key]

                    sentiment_label = sentiment if sentiment else "분석중"
                    sentiment_class = SENTIMENT_CLASS.get(sentiment_label, "sentiment-negative")

                    # 마크다운 줄 구성
                    if show_sentiment_badge:
                        md_line = (
                            f"[{article['title']}]({article['link']}) "
                            f"<span class='sentiment-badge {sentiment_class}'>({sentiment_label})</span> "
                            f"{article['date']} | {article['source']}"
                        )
                    else:
                        md_line = (
                            f"[{article['title']}]({article['link']}) "
                            f"{article['date']} | {article['source']}"
                        )

                    cols = st.columns([0.04, 0.96])
                    with cols[0]:
                        checked = st.checkbox("", value=st.session_state.article_checked.get(key, False), key=f"news_{key}")
                        st.session_state.article_checked[key] = checked
                    with cols[1]:
                        st.markdown(md_line, unsafe_allow_html=True)

                if limit < len(articles):
                    if st.button("더보기", key=f"more_{keyword}"):
                        st.session_state.show_limit[keyword] += 5
                        st.rerun()

    with col_summary:
        st.markdown("### 선택된 기사 요약/감성분석")
        selected_articles = []

        for keyword, articles in results.items():
            limit = st.session_state.show_limit[keyword]
            for article in articles[:limit]:
                link_hash = re.sub(r'\W+', '', article['link'])[-12:]
                key = f"{keyword}_{link_hash}"
                cache_key = f"summary_{key}"

                if not st.session_state.article_checked.get(key, False):
                    continue

                if cache_key in st.session_state:
                    one_line, summary, sentiment, full_text = st.session_state[cache_key]
                else:
                    one_line, summary, sentiment, full_text = summarize_article_from_url(
                        article['link'], article['title'], do_summary=enable_summary
                    )
                    st.session_state[cache_key] = (one_line, summary, sentiment, full_text)

                selected_articles.append({
                    "키워드": keyword,
                    "기사제목": article["title"],
                    "요약": one_line,
                    "감성": sentiment,
                    "링크": article["link"],
                    "날짜": article["date"],
                    "출처": article["source"]
                })

                # 개별 기사 표시
                st.markdown(f"#### [{article['title']}]({article['link']})", unsafe_allow_html=True)
                st.markdown(f"- **날짜/출처:** {article['date']} | {article['source']}")
                if enable_summary:
                    st.markdown(f"- **한 줄 요약:** {one_line}")
                st.markdown(f"- **감성분석:** `{sentiment}`")
                st.markdown("---")

        st.session_state.selected_articles = selected_articles
        st.write(f"선택된 기사 수: {len(selected_articles)}")

        if selected_articles:
            excel_bytes = get_excel_download_with_favorite_and_excel_company_col(
                selected_articles, favorite_categories, excel_company_categories
            )
            st.download_button(
                label="📥 맞춤 엑셀 다운로드",
                data=excel_bytes.getvalue(),
                file_name="뉴스요약_맞춤형.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
