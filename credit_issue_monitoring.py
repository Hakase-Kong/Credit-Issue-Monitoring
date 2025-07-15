def render_articles_with_single_summary_and_telegram(
    results, show_limit, show_sentiment_badge=True, enable_summary=True
):
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
                        key = f"{keyword}_{idx}_{article_global_idx}"
                        checkbox_key = f"news_{key}"

                        checked = st.checkbox(
                            "선택",
                            value=st.session_state.article_checked.get(checkbox_key, False),
                            key=checkbox_key
                        )
                        st.session_state.article_checked[checkbox_key] = checked

                        st.markdown(
                            f"**[{article['title']}]({article['link']})**",
                            unsafe_allow_html=True
                        )
                        st.markdown(f"{article['date']} | {article['source']}")

                        cache_key = f"summary_{key}"
                        if cache_key in st.session_state:
                            _, _, sentiment, _ = st.session_state[cache_key]
                            if show_sentiment_badge and sentiment:
                                sentiment_class = SENTIMENT_CLASS.get(sentiment, "sentiment-negative")
                                st.markdown(
                                    f"<span class='sentiment-badge {sentiment_class}'>({sentiment})</span>",
                                    unsafe_allow_html=True
                                )
                        article_global_idx += 1

            if limit < len(articles):
                if st.button(f"더보기 ({keyword})", key=f"show_more_{keyword}"):
                    st.session_state.show_limit[keyword] = limit + 5
                    st.rerun()

    # --- 선택된 기사 카드형 요약/감성분석 ---
    with col_summary:
        st.markdown("### 선택된 기사 요약/감성분석")
        selected_articles = []
        for keyword, articles in results.items():
            limit = st.session_state.show_limit.get(keyword, 5)
            for idx, article in enumerate(articles[:limit]):
                key = f"{keyword}_{idx}_{idx}"
                checkbox_key = f"news_{key}"
                if st.session_state.article_checked.get(checkbox_key, False):
                    cache_key = f"summary_{key}"
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
                    # --- 카드형 요약 ---
                    with st.container(border=True):
                        st.markdown(
                            f"**[{article['title']}]({article['link']})**",
                            unsafe_allow_html=True
                        )
                        st.markdown(f"- 날짜/출처: {article['date']} | {article['source']}")
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
                label="엑셀 다운로드 (선택 기사 요약)",
                data=excel_bytes,
                file_name="news_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
