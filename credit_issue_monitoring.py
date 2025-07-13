import os
import streamlit as st
import pandas as pd
from io import BytesIO
import requests
import re
from datetime import datetime, date, timedelta
import telepot
from openai import OpenAI
import newspaper  # newspaper3k
import difflib

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

# 경고 메시지(Warning, Exception 등) 영역을 CSS로 숨기기
st.markdown("""
<style>
    .stAlert, .stException, .stWarning {
        display: none !important;
    }
    [data-testid="stNotification"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 제외 키워드 ---
EXCLUDE_TITLE_KEYWORDS = [
    "야구", "축구", "배구", "농구", "골프", "e스포츠", "올림픽", "월드컵", "K리그", "프로야구", "프로축구", "프로배구", "프로농구", "우승", "무승부", "경기", "패배", "스포츠", "스폰서",
    "부고", "인사", "승진", "임명", "발령", "인사발령", "인사이동",
    "브랜드평판", "브랜드 평판", "브랜드 순위", "브랜드지수", "지속가능", "ESG", "스타트업",
    "코스피", "코스닥", "주가", "주식", "증시", "시세", "마감", "장중", "장마감", "거래량", "거래대금", "상한가", "하한가",
    "봉사", "후원", "기부", "혜택", "땡처리", "세일", "이벤트"
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
if "filtered_results" not in st.session_state:
    st.session_state.filtered_results = {}

# 최초 실행 시에만 session_state 값 세팅
if "end_date" not in st.session_state:
    st.session_state["end_date"] = date.today()
if "start_date" not in st.session_state:
    st.session_state["start_date"] = st.session_state["end_date"] - timedelta(days=7)
    
# --- 즐겨찾기 카테고리(변경 금지, UI 미노출) ---
favorite_categories = {
    "국/공채": [],
    "공공기관": [],
    "보험사": ["현대해상", "농협생명", "메리츠화재", "교보생명", "삼성화재", "삼성생명", "신한라이프", "흥국생명", "동양생명", "미래에셋생명"],
    "5대금융지주": ["신한금융", "하나금융", "KB금융", "농협금융", "우리금융"],
    "5대시중은행": ["농협은행", "국민은행", "신한은행", "우리은행", "하나은행"],
    "카드사": ["KB국민카드", "현대카드", "신한카드", "비씨카드", "삼성카드"],
    "캐피탈": ["한국캐피탈", "현대캐피탈"],
    "지주사": ["SK이노베이션", "GS에너지", "SK", "GS"],
    "에너지": ["SK가스", "GS칼텍스", "S-Oil", "SK에너지", "SK앤무브", "코리아에너지터미널"],
    "발전": ["GS파워", "GSEPS", "삼천리"],
    "자동차": ["LG에너지솔루션", "한온시스템", "포스코퓨처엠", "한국타이어"],
    "전기/전자": ["SK하이닉스", "LG이노텍", "LG전자", "LS일렉트릭"],
    "소비재": ["이마트", "LF", "CJ제일제당", "SK네트웍스", "CJ대한통운"],
    "비철/철강": ["포스코", "현대제철", "고려아연"],
    "석유화학": ["LG화학", "SK지오센트릭"],
    "건설": ["포스코이앤씨"],
    "특수채": ["주택도시보증공사", "기업은행"]
}

# ---- 대분류별 기업/이슈 분리 및 통합 ----
# 1. 은행 및 금융지주
industry_filter_categories = {}
industry_filter_categories["은행 및 금융지주"] = [
    "경영실태평가", "BIS", "CET1", "자본비율", "상각형 조건부자본증권", "자본확충", "자본여력", "자본적정성", "LCR",
    "조달금리", "NIM", "순이자마진", "고정이하여신비율", "대손충당금", "충당금", "부실채권", "연체율", "가계대출", "취약차주"
]
favorite_categories["은행 및 금융지주"] = favorite_categories["5대금융지주"] + favorite_categories["5대시중은행"]

# 2. 전기전자
industry_filter_categories["전기전자"] = [
    "CHIPS 보조금", "중국", "DRAM", "HBM", "광할솔루션", "아이폰", "HVAC", "HVTR"
]
favorite_categories["전기전자"] = favorite_categories["전기/전자"]

# 3. 철강/비철 통합
industry_filter_categories["철강/비철"] = [
    # 철강 이슈
    "철광석", "후판", "강판", "철근", "스프레드", "철강", "가동률", "제철소", "셧다운", "중국산 저가",
    "중국 수출 감소", "건설경기", "조선 수요", "파업",
    # 비철 이슈
    "연", "아연", "니켈", "안티모니", "경영권 분쟁", "MBK", "영풍"
]
favorite_categories["철강/비철"] = favorite_categories["비철/철강"]

# 기존 "철강", "비철", "전기/전자", "5대금융지주", "5대시중은행", "비철/철강" 대분류는 industry_filter_categories에서 사용하지 않음
# 나머지 대분류는 기존대로 추가
industry_filter_categories.update({
    "보험사": [
        "보장성보험", "저축성보험", "변액보험", "퇴직연금", "일반보험", "자동차보험", "ALM", "지급여력비율", "K-ICS",
        "보험수익성", "보험손익", "수입보험료", "CSM", "상각", "투자손익", "운용성과", "IFRS4", "IFRS17", "보험부채",
        "장기선도금리", "최종관찰만기", "유동성 프리미엄", "신종자본증권", "후순위채", "위험자산비중", "가중부실자산비율"
    ],
    "카드사": [
        "민간소비지표", "대손준비금", "가계부채", "연체율", "가맹점카드수수료", "대출성자산", "신용판매자산", "고정이하여신", "레버리지배율",
        "건전성", "케이뱅크", "이탈"
    ],
    "캐피탈": [
        "충당금커버리지비율", "고정이하여신", "PF구조조정", "리스자산", "손실흡수능력", "부동산PF연체채권", "자산포트폴리오", "건전성",
        "조정총자산수익률", "군인공제회"
    ],
    "지주사": [
        "SK지오센트릭", "SK에너지", "SK엔무브", "SK인천석유화학", "GS칼텍스", "GS파워", "SK이노베이션", "SK텔레콤", "SK온",
        "GS에너지", "GS리테일", "GS E&C", "2차전지", "석유화학", "윤활유", "전기차", "배터리", "정유", "이동통신"
    ],
    "에너지": [
        "정유", "유가", "정제마진", "스프레드", "가동률", "재고 손실", "중국 수요", "IMO 규제", "저유황 연료", "LNG",
        "터미널", "윤활유"
    ],
    "발전": [
        "LNG", "천연가스", "유가", "SMP", "REC", "계통시장", "탄소세", "탄소배출권", "전력시장 개편", "전력 자율화",
        "가동률", "도시가스"
    ],
    "자동차": [
        "AMPC 보조금", "IRA 인센티브", "중국 배터리", "EV 수요", "전기차", "ESS수요", "리튬", "타이어"
    ],
    "소비재": [
        "내수부진", "시장지배력", "SK텔레콤", "SK매직", "CLS", "HMR", "라이신", "아미노산", "슈완스컴퍼니",
        "의류", "신세계", "대형마트 의무휴업", "G마켓", "W컨셉", "스타필드"
    ],
    "석유화학": [
        "석유화학", "석화", "유가", "증설", "스프레드", "가동률", "PX", "벤젠", "중국 증설", "중동 COTC",
        "LG에너지솔루션", "전기차", "배터리", "리튬", "IRA", "AMPC"
    ],
    "건설": [
        "철근 가격", "시멘트 가격", "공사비", "SOC 예산", "도시정비 지원", "우발채무", "수주", "주간사", "사고",
        "시공능력순위", "미분양", "대손충당금"
    ],
    "특수채": [
        "자본확충", "HUG", "전세사기", "보증사고", "보증료율", "회수율", "보증잔액", "대위변제액",
        "중소기업대출", "대손충당금", "부실채권", "불법", "구속"
    ]
})

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

# --- 산업별 필터 옵션 + 즐겨찾기 기업명 포함 ---
industry_filter_categories = {
    "은행 및 금융지주": [
        "경영실태평가", "BIS", "CET1", "자본비율", "상각형 조건부자본증권", "자본확충", "자본여력", "자본적정성", "LCR",
        "조달금리", "NIM", "순이자마진", "고정이하여신비율", "대손충당금", "충당금", "부실채권", "연체율", "가계대출", "취약차주"
    ] + favorite_categories["5대금융지주"] + favorite_categories["5대시중은행"],
    "보험사": [
        "보장성보험", "저축성보험", "변액보험", "퇴직연금", "일반보험", "자동차보험", "ALM", "지급여력비율", "K-ICS",
        "보험수익성", "보험손익", "수입보험료", "CSM", "상각", "투자손익", "운용성과", "IFRS4", "IFRS17", "보험부채",
        "장기선도금리", "최종관찰만기", "유동성 프리미엄", "신종자본증권", "후순위채", "위험자산비중", "가중부실자산비율"
    ] + favorite_categories["보험사"],
    "카드사": [
        "민간소비지표", "대손준비금", "가계부채", "연체율", "가맹점카드수수료", "대출성자산", "신용판매자산", "고정이하여신", "레버리지배율",
        "건전성", "케이뱅크", "이탈"
    ] + favorite_categories["카드사"],
    "캐피탈": [
        "충당금커버리지비율", "고정이하여신", "PF구조조정", "리스자산", "손실흡수능력", "부동산PF연체채권", "자산포트폴리오", "건전성",
        "조정총자산수익률", "군인공제회"
    ] + favorite_categories["캐피탈"],
    "지주사": [
        "SK지오센트릭", "SK에너지", "SK엔무브", "SK인천석유화학", "GS칼텍스", "GS파워", "SK이노베이션", "SK텔레콤", "SK온",
        "GS에너지", "GS리테일", "GS E&C", "2차전지", "석유화학", "윤활유", "전기차", "배터리", "정유", "이동통신"
    ] + favorite_categories["지주사"],
    "에너지": [
        "정유", "유가", "정제마진", "스프레드", "가동률", "재고 손실", "중국 수요", "IMO 규제", "저유황 연료", "LNG",
        "터미널", "윤활유"
    ] + favorite_categories["에너지"],
    "발전": [
        "LNG", "천연가스", "유가", "SMP", "REC", "계통시장", "탄소세", "탄소배출권", "전력시장 개편", "전력 자율화",
        "가동률", "도시가스"
    ] + favorite_categories["발전"],
    "자동차": [
        "AMPC 보조금", "IRA 인센티브", "중국 배터리", "EV 수요", "전기차", "ESS수요", "리튬", "타이어"
    ] + favorite_categories["자동차"],
    "전기전자": [
        "CHIPS 보조금", "중국", "DRAM", "HBM", "광할솔루션", "아이폰", "HVAC", "HVTR"
    ] + favorite_categories["전기/전자"],
    "철강": [
        "철광석", "후판", "강판", "철근", "스프레드", "철강", "가동률", "제철소", "셧다운", "중국산 저가",
        "중국 수출 감소", "건설경기", "조선 수요", "파업"
    ] + favorite_categories["비철/철강"],
    "비철": [
        "연", "아연", "니켈", "안티모니", "경영권 분쟁", "MBK", "영풍"
    ],
    "소비재": [
        "내수부진", "시장지배력", "SK텔레콤", "SK매직", "CLS", "HMR", "라이신", "아미노산", "슈완스컴퍼니",
        "의류", "신세계", "대형마트 의무휴업", "G마켓", "W컨셉", "스타필드"
    ] + favorite_categories["소비재"],
    "석유화학": [
        "석유화학", "석화", "유가", "증설", "스프레드", "가동률", "PX", "벤젠", "중국 증설", "중동 COTC",
        "LG에너지솔루션", "전기차", "배터리", "리튬", "IRA", "AMPC"
    ] + favorite_categories["석유화학"],
    "건설": [
        "철근 가격", "시멘트 가격", "공사비", "SOC 예산", "도시정비 지원", "우발채무", "수주", "주간사", "사고",
        "시공능력순위", "미분양", "대손충당금"
    ] + favorite_categories["건설"],
    "특수채": [
        "자본확충", "HUG", "전세사기", "보증사고", "보증료율", "회수율", "보증잔액", "대위변제액",
        "중소기업대출", "대손충당금", "부실채권", "불법", "구속"
    ] + favorite_categories["특수채"]
}

KOREAN_STOPWORDS = {
    '의', '이', '가', '은', '는', '을', '를', '에', '에서', '으로', '와', '과', '도', '로', '및', '한', '하다', '되다',
    '…', '“', '”', '‘', '’', '등', '및', '그', '저', '더', '또', '것', '수', '등', '및', '로', '에서', '까지', '부터'
}
ENGLISH_STOPWORDS = {
    "the", "and", "is", "in", "to", "of", "a", "on", "for", "with", "as", "by", "at", "an", "be", "from", "it", "that",
    "this", "are", "was", "but", "or", "not", "has", "have", "had", "will", "would", "can", "could", "should"
}

def extract_keywords(text):
    if re.search(r"[가-힣]", text):
        words = re.findall(r"[가-힣]{2,}", text)
        keywords = [w for w in words if w not in KOREAN_STOPWORDS]
        return set(keywords)
    else:
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        keywords = [w for w in words if w not in ENGLISH_STOPWORDS]
        return set(keywords)

def remove_duplicate_articles_by_title_and_keywords(articles, title_threshold=0.75, keyword_threshold=0.6):
    unique_articles = []
    seen_titles = set()
    seen_keywords_hash = set()
    for article in articles:
        title = article.get("title", "")
        full_text = article.get("title", "") + " " + article.get("description", "")
        keywords = extract_keywords(full_text)
        title_key = title.strip().lower()
        kw_hash = hash(frozenset(keywords))
        if title_key in seen_titles or kw_hash in seen_keywords_hash:
            continue
        unique_articles.append(article)
        seen_titles.add(title_key)
        seen_keywords_hash.add(kw_hash)
    return unique_articles

# UI 시작
st.set_page_config(layout="wide")
col_title, col_option1, col_option2 = st.columns([0.6, 0.2, 0.2])
with col_title:
    st.markdown("<h1 style='color:#1a1a1a; margin-bottom:0.5rem;'>📊 Credit Issue Monitoring</h1>", unsafe_allow_html=True)
with col_option1:
    show_sentiment_badge = st.checkbox("기사목록에 감성분석 배지 표시", value=False, key="show_sentiment_badge")
with col_option2:
    enable_summary = st.checkbox("요약 기능 적용", value=False, key="enable_summary")

# 1. 키워드 입력/검색 버튼 (한 줄, 버튼 오른쪽)
col_kw_input, col_kw_btn = st.columns([0.8, 0.2])
with col_kw_input:
    keywords_input = st.text_input("키워드 (예: 삼성, 한화)", value="", key="keyword_input", label_visibility="visible")
with col_kw_btn:
    search_clicked = st.button("검색", key="search_btn", help="키워드로 검색", use_container_width=True)

# 2. 산업별 검색 (키워드 검색란 바로 아래, 대분류-기업-이슈 3단계)
st.markdown("### 🏭 산업별 검색")
col_major, col_company, col_issue, col_btn = st.columns([0.25, 0.25, 0.30, 0.20])

with col_major:
    selected_industry = st.selectbox(
        "대분류(산업)",
        list(industry_filter_categories.keys()),
        key="industry_major"
    )

# 해당 산업군의 기업/이슈 분리
industry_companies = favorite_categories.get(selected_industry, [])
industry_issues = [k for k in industry_filter_categories[selected_industry] if k not in industry_companies]

with col_company:
    # 대분류 선택 시 기업 자동 전체 선택
    selected_companies = st.multiselect(
        "기업",
        industry_companies,
        default=industry_companies,
        key="industry_companies"
    )

with col_issue:
    selected_issues = st.multiselect(
        "소분류(이슈)",
        industry_issues,
        default=industry_issues,
        key="industry_issues"
    )

with col_btn:
    industry_search_clicked = st.button("검색", key="industry_search_btn", use_container_width=True)

# 3. 날짜 위젯
def on_date_change():
    filter_articles_by_date()

date_col1, date_col2 = st.columns([1, 1])
with date_col2:
    st.date_input(
        "종료일",
        value=st.session_state["end_date"],
        key="end_date",
        on_change=on_date_change
    )
with date_col1:
    st.date_input(
        "시작일",
        value=st.session_state["start_date"],
        key="start_date",
        on_change=on_date_change
    )
    
# --- 공통 필터 옵션 (항상 적용, 전체 키워드 가시적으로 표시) ---
with st.expander("🧩 공통 필터 옵션 (필터별 적용/해제 가능)"):
    common_filter_active = {}
    for major, subs in common_filter_categories.items():
        active = st.checkbox(f"{major} 필터 적용", value=True, key=f"common_filter_{major}")
        common_filter_active[major] = active
        st.markdown(f"- {', '.join(subs)}")

# 필터링 시 적용할 키워드만 모음
active_common_keywords = []
for major, active in common_filter_active.items():
    if active:
        active_common_keywords.extend(common_filter_categories[major])

# --- 키워드 필터 옵션 (하단으로 이동) ---
with st.expander("🔍 키워드 필터 옵션"):
    require_keyword_in_title = st.checkbox("기사 제목에 키워드가 포함된 경우만 보기", value=False, key="require_keyword_in_title")
    require_exact_keyword_in_title_or_content = st.checkbox("키워드가 온전히 제목 또는 본문에 포함된 기사만 보기", value=False, key="require_exact_keyword_in_title_or_content")

# --- 본문 추출 함수 (캐싱) ---
@st.cache_data(show_spinner=False)
def extract_article_text_cached(url):
    try:
        article = newspaper.Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        return f"본문 추출 오류: {e}"

# --- OpenAI 요약/감성분석 함수 (캐싱) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def detect_lang(text):
    return "ko" if re.search(r"[가-힣]", text) else "en"

@st.cache_data(show_spinner=False)
def summarize_and_sentiment_with_openai_cached(text, title=None, do_summary=True):
    if not OPENAI_API_KEY:
        return "OpenAI API 키가 설정되지 않았습니다.", None, None, None

    # 본문이 너무 짧거나 오류일 때 요약 시도 금지
    if not text or "본문 추출 오류" in text or len(text.strip()) < 50:
        return "기사 본문 추출 실패로 요약 불가", None, None, None

    lang = detect_lang(text)
    title = title or ""
    if lang == "ko":
        prompt = (
            f"아래 기사 제목, 본문, 그리고 검색 키워드 '{title}'를 참고해, 반드시 한 줄 요약에 '{title}'가 포함되도록 해줘. "
            "만약 키워드와 관련 없는 기사라면 '키워드와 관련된 내용이 기사에 없음'이라고 답해줘.\n"
            "- [한 줄 요약]: 기사 제목, 본문, 키워드를 바탕으로, 반드시 키워드가 포함된 한 문장으로 요약\n"
            "- [감성]: 기사 전체의 감정을 긍정/부정 중 하나로만 답해줘. 중립은 절대 답하지 마. 파산, 자금난 등 부정적 사건이 중심이면 반드시 '부정'으로 답해줘.\n\n"
            "아래 포맷으로 답변해줘:\n"
            "[한 줄 요약]: (여기에 한 줄 요약)\n"
            "[감성]: (긍정/부정 중 하나만)\n\n"
            f"[검색 키워드]\n{title}\n[기사 제목]\n{title}\n[기사 본문]\n{text}"
        )
    else:
        prompt = (
        f"Summarize the following article in one sentence, and make sure the summary includes the keyword '{title}'. "
        "If the keyword is not relevant to the article, answer: 'No content related to the keyword.'\n"
        "- [One-line Summary]: Summarize with the keyword included.\n"
        "- [Sentiment]: positive or negative only.\n\n"
        "Respond in this format:\n"
        "[One-line Summary]: (your one-line summary)\n"
        "[Sentiment]: (positive/negative only)\n\n"
        f"[KEYWORD]\n{title}\n[TITLE]\n{title}\n[ARTICLE]\n{text}"
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

def summarize_article_from_url(article_url, title, do_summary=True):
    try:
        full_text = extract_article_text_cached(article_url)
        if full_text.startswith("본문 추출 오류"):
            return full_text, None, None, None
        one_line, summary, sentiment, _ = summarize_and_sentiment_with_openai_cached(full_text, title=title, do_summary=do_summary)
        return one_line, summary, sentiment, full_text
    except Exception as e:
        return f"요약 오류: {e}", None, None, None

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
                "description": re.sub("<.*?>", "", desc),
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
                "description": desc,
                "link": item.get("url", ""),
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "GNews"
            })
    except Exception as e:
        st.warning(f"⚠️ GNews 접근 오류: {e}")
    return articles

def is_english(text):
    return all(ord(c) < 128 for c in text if c.isalpha())

def process_keywords(keyword_list, start_date, end_date, require_keyword_in_title=False):
    for k in keyword_list:
        if is_english(k):
            articles = fetch_gnews_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        else:
            articles = fetch_naver_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        articles = remove_duplicate_articles_by_title_and_keywords(articles, title_threshold=0.75, keyword_threshold=0.6)
        st.session_state.search_results[k] = articles
        if k not in st.session_state.show_limit:
            st.session_state.show_limit[k] = 5

def detect_lang_from_title(title):
    return "ko" if re.search(r"[가-힣]", title) else "en"

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

if search_clicked or st.session_state.get("search_triggered"):
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        with st.spinner("뉴스 검색 중..."):
            process_keywords(keyword_list, st.session_state["start_date"], st.session_state["end_date"], require_keyword_in_title=st.session_state.get("require_keyword_in_title", False))
    st.session_state.search_triggered = False

# 산업별 검색 버튼 동작 (대분류-기업-이슈 구조)
if industry_search_clicked and selected_companies:
    with st.spinner("뉴스 검색 중..."):
        process_keywords(
            selected_companies,
            st.session_state["start_date"],
            st.session_state["end_date"],
            require_keyword_in_title=st.session_state.get("require_keyword_in_title", False)
        )
    # 이슈는 후처리 필터에서 적용

def article_passes_all_filters(article):
    filters = []
    filters.append(ALL_COMMON_FILTER_KEYWORDS)
    # 산업별 검색에서 이슈(OR) 필터 적용
    industry_issues_filter = st.session_state.get("industry_issues", [])
    if industry_issues_filter:
        filters.append(industry_issues_filter)
    # 활성화된 공통 필터만 적용
    if active_common_keywords:
        filters.append(active_common_keywords)
    if exclude_by_title_keywords(article.get('title', ''), EXCLUDE_TITLE_KEYWORDS):
        return False
    if st.session_state.get("require_exact_keyword_in_title_or_content", False):
        all_keywords = []
        if keywords_input:
            all_keywords.extend([k.strip() for k in keywords_input.split(",") if k.strip()])
        if not article_contains_exact_keyword(article, all_keywords):
            return False
    return or_keyword_filter(article, *filters)

def safe_title(val):
    if pd.isnull(val) or str(val).strip() == "" or str(val).lower() == "nan" or str(val) == "0":
        return "제목없음"
    return str(val)

def get_excel_download_with_favorite_and_excel_company_col(summary_data, favorite_categories, excel_company_categories):
    company_order = []
    for cat in [
        "국/공채", "공공기관", "보험사", "5대금융지주", "5대시중은행", "카드사", "캐피탈",
        "지주사", "에너지", "발전", "자동차", "전기/전자", "소비재", "비철/철강", "석유화학", "건설", "특수채"
    ]:
        company_order.extend(favorite_categories.get(cat, []))

    excel_company_order = []
    for cat in [
        "국/공채", "공공기관", "보험사", "5대금융지주", "5대시중은행", "카드사", "캐피탈",
        "지주사", "에너지", "발전", "자동차", "전기/전자", "소비재", "비철/철강", "석유화학", "건설", "특수채"
    ]:
        excel_company_order.extend(excel_company_categories.get(cat, []))

    df_articles = pd.DataFrame(summary_data)
    result_rows = []
    for idx, company in enumerate(company_order):
        excel_company_name = excel_company_order[idx] if idx < len(excel_company_order) else ""

        comp_articles = df_articles[df_articles["키워드"] == company]
        pos_news = comp_articles[comp_articles["감성"] == "긍정"].sort_values(by="날짜", ascending=False)
        neg_news = comp_articles[comp_articles["감성"] == "부정"].sort_values(by="날짜", ascending=False)

        if not pos_news.empty:
            pos_date = pos_news.iloc[0]["날짜"]
            pos_title = pos_news.iloc[0]["기사제목"]
            pos_link = pos_news.iloc[0]["링크"]
            pos_display = f'({pos_date}) {pos_title}'
            pos_hyperlink = f'=HYPERLINK("{pos_link}", "{pos_display}")'
        else:
            pos_hyperlink = ""

        if not neg_news.empty:
            neg_date = neg_news.iloc[0]["날짜"]
            neg_title = neg_news.iloc[0]["기사제목"]
            neg_link = neg_news.iloc[0]["링크"]
            neg_display = f'({neg_date}) {neg_title}'
            neg_hyperlink = f'=HYPERLINK("{neg_link}", "{neg_display}")'
        else:
            neg_hyperlink = ""

        result_rows.append({
            "기업명": company,
            "표기명": excel_company_name,
            "긍정 뉴스": pos_hyperlink,
            "부정 뉴스": neg_hyperlink
        })

    df_result = pd.DataFrame(result_rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_result.to_excel(writer, index=False, sheet_name='뉴스요약')
    output.seek(0)
    return output

def render_articles_with_single_summary_and_telegram(results, show_limit, show_sentiment_badge=True, enable_summary=True):
    SENTIMENT_CLASS = {
        "긍정": "sentiment-positive",
        "부정": "sentiment-negative"
    }

    if "article_checked" not in st.session_state:
        st.session_state.article_checked = {}

    col_list, col_summary = st.columns([1, 1])

    with col_list:
        st.markdown("### 기사 요약 결과")
        for keyword, articles in results.items():
            with st.container(border=True):
                st.markdown(f"**[{keyword}]**")
                limit = st.session_state.show_limit.get(keyword, 5)
                for idx, article in enumerate(articles[:limit]):
                    unique_id = re.sub(r'\W+', '', article['link'])[-16:]
                    key = f"{keyword}_{idx}_{unique_id}"
                    sentiment_label = ""
                    sentiment_class = ""
                    sentiment_html = ""
                    if show_sentiment_badge:
                        if f"summary_{key}" in st.session_state:
                            _, _, sentiment, _ = st.session_state[f"summary_{key}"]
                            sentiment_label = sentiment if sentiment else "분석중"
                            sentiment_class = SENTIMENT_CLASS.get(sentiment_label, "sentiment-negative")
                            sentiment_html = f"<span class='sentiment-badge {sentiment_class}'>({sentiment_label})</span>"
                    md_line = (
                        f"[{article['title']}]({article['link']}) "
                        f"{sentiment_html} "
                        f"{article['date']} | {article['source']}"
                    )
                    cols = st.columns([0.04, 0.96])
                    with cols[0]:
                        checked = st.checkbox("", value=st.session_state.article_checked.get(key, False), key=f"news_{key}")
                    with cols[1]:
                        st.markdown(md_line, unsafe_allow_html=True)
                    st.session_state.article_checked[key] = checked

                if limit < len(articles):
                    if st.button("더보기", key=f"more_{keyword}"):
                        st.session_state.show_limit[keyword] += 10
                        st.rerun()

    with col_summary:
        st.markdown("### 선택된 기사 요약/감성분석")
        with st.container(border=True):
            selected_articles = []
            def safe_title_for_append(val):
                if val is None or str(val).strip() == "" or str(val).lower() == "nan" or str(val) == "0":
                    return "제목없음"
                return str(val)
            for keyword, articles in results.items():
                limit = st.session_state.show_limit.get(keyword, 5)
                for idx, article in enumerate(articles[:limit]):
                    unique_id = re.sub(r'\W+', '', article['link'])[-16:]
                    key = f"{keyword}_{idx}_{unique_id}"
                    cache_key = f"summary_{key}"
                    if st.session_state.article_checked.get(key, False):
                        if cache_key in st.session_state:
                            one_line, summary, sentiment, full_text = st.session_state[cache_key]
                        else:
                            one_line, summary, sentiment, full_text = summarize_article_from_url(
                                article['link'], article['title'], do_summary=enable_summary
                            )
                            st.session_state[cache_key] = (one_line, summary, sentiment, full_text)
                        selected_articles.append({
                            "키워드": keyword,
                            "기사제목": safe_title_for_append(article.get('title')),
                            "요약": one_line,
                            "요약본": summary,
                            "감성": sentiment,
                            "링크": article['link'],
                            "날짜": article['date'],
                            "출처": article['source']
                        })
                        if show_sentiment_badge:
                            st.markdown(
                                f"#### [{article['title']}]({article['link']}) "
                                f"<span class='sentiment-badge {SENTIMENT_CLASS.get(sentiment, 'sentiment-negative')}'>({sentiment})</span>",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(f"#### [{article['title']}]({article['link']})", unsafe_allow_html=True)
                        st.markdown(f"- **날짜/출처:** {article['date']} | {article['source']}")
                        if enable_summary:
                            st.markdown(f"- **한 줄 요약:** {one_line}")
                        st.markdown(f"- **감성분석:** `{sentiment}`")
                        st.markdown("---")

            st.session_state.selected_articles = selected_articles
            st.write(f"선택된 기사 개수: {len(selected_articles)}")

            excel_company_order = []
            for cat in ["국/공채", "공공기관", "보험사", "5대금융지주", "5대시중은행", "카드사", "캐피탈", "지주사", "에너지", "발전", "자동차", "전기/전자", "소비재", "비철/철강", "석유화학", "건설", "특수채"]:
                excel_company_order.extend(excel_company_categories.get(cat, []))

            if st.session_state.selected_articles:
                excel_bytes = get_excel_download_with_favorite_and_excel_company_col(
                    st.session_state.selected_articles,
                    favorite_categories,
                    excel_company_categories
                )
                st.download_button(
                    label="📥 맞춤 엑셀 다운로드",
                    data=excel_bytes.getvalue(),
                    file_name="뉴스요약_맞춤형.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# 날짜 변경 시 필터링
def filter_articles_by_date():
    st.session_state.filtered_results = {}
    for keyword, articles in st.session_state.search_results.items():
        filtered = [
            a for a in articles
            if st.session_state["start_date"] <= datetime.strptime(a['date'], "%Y-%m-%d").date() <= st.session_state["end_date"]
        ]
        if filtered:
            st.session_state.filtered_results[keyword] = filtered

# 날짜 위젯 값이 바뀌면 자동 필터링
if st.session_state.search_results:
    filter_articles_by_date()
    filtered_results = {}
    for keyword, articles in st.session_state.filtered_results.items():
        filtered_articles = [a for a in articles if article_passes_all_filters(a)]
        if filtered_articles:
            filtered_results[keyword] = filtered_articles
    render_articles_with_single_summary_and_telegram(
        filtered_results,
        st.session_state.show_limit,
        show_sentiment_badge=st.session_state.get("show_sentiment_badge", False),
        enable_summary=st.session_state.get("enable_summary", True)
    )

# --- 본문 추출 함수 (캐싱) ---
@st.cache_data(show_spinner=False)
def extract_article_text_cached(url):
    try:
        article = newspaper.Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        return f"본문 추출 오류: {e}"

# --- OpenAI 요약/감성분석 함수 (캐싱) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def detect_lang(text):
    return "ko" if re.search(r"[가-힣]", text) else "en"

@st.cache_data(show_spinner=False)
def summarize_and_sentiment_with_openai_cached(text, title=None, do_summary=True):
    if not OPENAI_API_KEY:
        return "OpenAI API 키가 설정되지 않았습니다.", None, None, None

    # 본문이 너무 짧거나 오류일 때 요약 시도 금지
    if not text or "본문 추출 오류" in text or len(text.strip()) < 50:
        return "기사 본문 추출 실패로 요약 불가", None, None, None

    lang = detect_lang(text)
    title = title or ""
    if lang == "ko":
        prompt = (
            f"아래 기사 제목, 본문, 그리고 검색 키워드 '{title}'를 참고해, 반드시 한 줄 요약에 '{title}'가 포함되도록 해줘. "
            "만약 키워드와 관련 없는 기사라면 '키워드와 관련된 내용이 기사에 없음'이라고 답해줘.\n"
            "- [한 줄 요약]: 기사 제목, 본문, 키워드를 바탕으로, 반드시 키워드가 포함된 한 문장으로 요약\n"
            "- [감성]: 기사 전체의 감정을 긍정/부정 중 하나로만 답해줘. 중립은 절대 답하지 마. 파산, 자금난 등 부정적 사건이 중심이면 반드시 '부정'으로 답해줘.\n\n"
            "아래 포맷으로 답변해줘:\n"
            "[한 줄 요약]: (여기에 한 줄 요약)\n"
            "[감성]: (긍정/부정 중 하나만)\n\n"
            f"[검색 키워드]\n{title}\n[기사 제목]\n{title}\n[기사 본문]\n{text}"
        )
    else:
        prompt = (
        f"Summarize the following article in one sentence, and make sure the summary includes the keyword '{title}'. "
        "If the keyword is not relevant to the article, answer: 'No content related to the keyword.'\n"
        "- [One-line Summary]: Summarize with the keyword included.\n"
        "- [Sentiment]: positive or negative only.\n\n"
        "Respond in this format:\n"
        "[One-line Summary]: (your one-line summary)\n"
        "[Sentiment]: (positive/negative only)\n\n"
        f"[KEYWORD]\n{title}\n[TITLE]\n{title}\n[ARTICLE]\n{text}"
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

def summarize_article_from_url(article_url, title, do_summary=True):
    try:
        full_text = extract_article_text_cached(article_url)
        if full_text.startswith("본문 추출 오류"):
            return full_text, None, None, None
        one_line, summary, sentiment, _ = summarize_and_sentiment_with_openai_cached(full_text, title=title, do_summary=do_summary)
        return one_line, summary, sentiment, full_text
    except Exception as e:
        return f"요약 오류: {e}", None, None, None

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
                "description": re.sub("<.*?>", "", desc),
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
                "description": desc,
                "link": item.get("url", ""),
                "date": pub_date.strftime("%Y-%m-%d"),
                "source": "GNews"
            })
    except Exception as e:
        st.warning(f"⚠️ GNews 접근 오류: {e}")
    return articles

def is_english(text):
    return all(ord(c) < 128 for c in text if c.isalpha())

def process_keywords(keyword_list, start_date, end_date, require_keyword_in_title=False):
    for k in keyword_list:
        if is_english(k):
            articles = fetch_gnews_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        else:
            articles = fetch_naver_news(k, start_date, end_date, require_keyword_in_title=require_keyword_in_title)
        articles = remove_duplicate_articles_by_title_and_keywords(articles, title_threshold=0.75, keyword_threshold=0.6)
        st.session_state.search_results[k] = articles
        if k not in st.session_state.show_limit:
            st.session_state.show_limit[k] = 5

def detect_lang_from_title(title):
    return "ko" if re.search(r"[가-힣]", title) else "en"

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

if search_clicked or st.session_state.get("search_triggered"):
    keyword_list = [k.strip() for k in keywords_input.split(",") if k.strip()]
    if len(keyword_list) > 10:
        st.warning("키워드는 최대 10개까지 입력 가능합니다.")
    else:
        with st.spinner("뉴스 검색 중..."):
            process_keywords(keyword_list, st.session_state["start_date"], st.session_state["end_date"], require_keyword_in_title=st.session_state.get("require_keyword_in_title", False))
    st.session_state.search_triggered = False

# 산업별 검색 버튼 동작 (대분류-기업-이슈 구조)
if industry_search_clicked and selected_companies:
    with st.spinner("뉴스 검색 중..."):
        process_keywords(
            selected_companies,
            st.session_state["start_date"],
            st.session_state["end_date"],
            require_keyword_in_title=st.session_state.get("require_keyword_in_title", False)
        )
    # 이슈는 후처리 필터에서 적용

def article_passes_all_filters(article):
    filters = []
    filters.append(ALL_COMMON_FILTER_KEYWORDS)
    # 산업별 검색에서 이슈(OR) 필터 적용
    industry_issues_filter = st.session_state.get("industry_issues", [])
    if industry_issues_filter:
        filters.append(industry_issues_filter)
    # 활성화된 공통 필터만 적용
    if active_common_keywords:
        filters.append(active_common_keywords)
    if exclude_by_title_keywords(article.get('title', ''), EXCLUDE_TITLE_KEYWORDS):
        return False
    if st.session_state.get("require_exact_keyword_in_title_or_content", False):
        all_keywords = []
        if keywords_input:
            all_keywords.extend([k.strip() for k in keywords_input.split(",") if k.strip()])
        if not article_contains_exact_keyword(article, all_keywords):
            return False
    return or_keyword_filter(article, *filters)

def safe_title(val):
    if pd.isnull(val) or str(val).strip() == "" or str(val).lower() == "nan" or str(val) == "0":
        return "제목없음"
    return str(val)

def get_excel_download_with_favorite_and_excel_company_col(summary_data, favorite_categories, excel_company_categories):
    company_order = []
    for cat in [
        "국/공채", "공공기관", "보험사", "5대금융지주", "5대시중은행", "카드사", "캐피탈",
        "지주사", "에너지", "발전", "자동차", "전기/전자", "소비재", "비철/철강", "석유화학", "건설", "특수채"
    ]:
        company_order.extend(favorite_categories.get(cat, []))

    excel_company_order = []
    for cat in [
        "국/공채", "공공기관", "보험사", "5대금융지주", "5대시중은행", "카드사", "캐피탈",
        "지주사", "에너지", "발전", "자동차", "전기/전자", "소비재", "비철/철강", "석유화학", "건설", "특수채"
    ]:
        excel_company_order.extend(excel_company_categories.get(cat, []))

    df_articles = pd.DataFrame(summary_data)
    result_rows = []
    for idx, company in enumerate(company_order):
        excel_company_name = excel_company_order[idx] if idx < len(excel_company_order) else ""

        comp_articles = df_articles[df_articles["키워드"] == company]
        pos_news = comp_articles[comp_articles["감성"] == "긍정"].sort_values(by="날짜", ascending=False)
        neg_news = comp_articles[comp_articles["감성"] == "부정"].sort_values(by="날짜", ascending=False)

        if not pos_news.empty:
            pos_date = pos_news.iloc[0]["날짜"]
            pos_title = pos_news.iloc[0]["기사제목"]
            pos_link = pos_news.iloc[0]["링크"]
            pos_display = f'({pos_date}) {pos_title}'
            pos_hyperlink = f'=HYPERLINK("{pos_link}", "{pos_display}")'
        else:
            pos_hyperlink = ""

        if not neg_news.empty:
            neg_date = neg_news.iloc[0]["날짜"]
            neg_title = neg_news.iloc[0]["기사제목"]
            neg_link = neg_news.iloc[0]["링크"]
            neg_display = f'({neg_date}) {neg_title}'
            neg_hyperlink = f'=HYPERLINK("{neg_link}", "{neg_display}")'
        else:
            neg_hyperlink = ""

        result_rows.append({
            "기업명": company,
            "표기명": excel_company_name,
            "긍정 뉴스": pos_hyperlink,
            "부정 뉴스": neg_hyperlink
        })

    df_result = pd.DataFrame(result_rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_result.to_excel(writer, index=False, sheet_name='뉴스요약')
    output.seek(0)
    return output

def render_articles_with_single_summary_and_telegram(results, show_limit, show_sentiment_badge=True, enable_summary=True):
    SENTIMENT_CLASS = {
        "긍정": "sentiment-positive",
        "부정": "sentiment-negative"
    }

    if "article_checked" not in st.session_state:
        st.session_state.article_checked = {}

    col_list, col_summary = st.columns([1, 1])

    with col_list:
        st.markdown("### 기사 요약 결과")
        for keyword, articles in results.items():
            with st.container(border=True):
                st.markdown(f"**[{keyword}]**")
                limit = st.session_state.show_limit.get(keyword, 5)
                for idx, article in enumerate(articles[:limit]):
                    unique_id = re.sub(r'\W+', '', article['link'])[-16:]
                    key = f"{keyword}_{idx}_{unique_id}"
                    sentiment_label = ""
                    sentiment_class = ""
                    sentiment_html = ""
                    if show_sentiment_badge:
                        if f"summary_{key}" in st.session_state:
                            _, _, sentiment, _ = st.session_state[f"summary_{key}"]
                            sentiment_label = sentiment if sentiment else "분석중"
                            sentiment_class = SENTIMENT_CLASS.get(sentiment_label, "sentiment-negative")
                            sentiment_html = f"<span class='sentiment-badge {sentiment_class}'>({sentiment_label})</span>"
                    md_line = (
                        f"[{article['title']}]({article['link']}) "
                        f"{sentiment_html} "
                        f"{article['date']} | {article['source']}"
                    )
                    cols = st.columns([0.04, 0.96])
                    with cols[0]:
                        checked = st.checkbox("", value=st.session_state.article_checked.get(key, False), key=f"news_{key}")
                    with cols[1]:
                        st.markdown(md_line, unsafe_allow_html=True)
                    st.session_state.article_checked[key] = checked

                if limit < len(articles):
                    if st.button("더보기", key=f"more_{keyword}"):
                        st.session_state.show_limit[keyword] += 10
                        st.rerun()

    with col_summary:
        st.markdown("### 선택된 기사 요약/감성분석")
        with st.container(border=True):
            selected_articles = []
            def safe_title_for_append(val):
                if val is None or str(val).strip() == "" or str(val).lower() == "nan" or str(val) == "0":
                    return "제목없음"
                return str(val)
            for keyword, articles in results.items():
                limit = st.session_state.show_limit.get(keyword, 5)
                for idx, article in enumerate(articles[:limit]):
                    unique_id = re.sub(r'\W+', '', article['link'])[-16:]
                    key = f"{keyword}_{idx}_{unique_id}"
                    cache_key = f"summary_{key}"
                    if st.session_state.article_checked.get(key, False):
                        if cache_key in st.session_state:
                            one_line, summary, sentiment, full_text = st.session_state[cache_key]
                        else:
                            one_line, summary, sentiment, full_text = summarize_article_from_url(
                                article['link'], article['title'], do_summary=enable_summary
                            )
                            st.session_state[cache_key] = (one_line, summary, sentiment, full_text)
                        selected_articles.append({
                            "키워드": keyword,
                            "기사제목": safe_title_for_append(article.get('title')),
                            "요약": one_line,
                            "요약본": summary,
                            "감성": sentiment,
                            "링크": article['link'],
                            "날짜": article['date'],
                            "출처": article['source']
                        })
                        if show_sentiment_badge:
                            st.markdown(
                                f"#### [{article['title']}]({article['link']}) "
                                f"<span class='sentiment-badge {SENTIMENT_CLASS.get(sentiment, 'sentiment-negative')}'>({sentiment})</span>",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(f"#### [{article['title']}]({article['link']})", unsafe_allow_html=True)
                        st.markdown(f"- **날짜/출처:** {article['date']} | {article['source']}")
                        if enable_summary:
                            st.markdown(f"- **한 줄 요약:** {one_line}")
                        st.markdown(f"- **감성분석:** `{sentiment}`")
                        st.markdown("---")

            st.session_state.selected_articles = selected_articles
            st.write(f"선택된 기사 개수: {len(selected_articles)}")

            excel_company_order = []
            for cat in ["국/공채", "공공기관", "보험사", "5대금융지주", "5대시중은행", "카드사", "캐피탈", "지주사", "에너지", "발전", "자동차", "전기/전자", "소비재", "비철/철강", "석유화학", "건설", "특수채"]:
                excel_company_order.extend(excel_company_categories.get(cat, []))

            if st.session_state.selected_articles:
                excel_bytes = get_excel_download_with_favorite_and_excel_company_col(
                    st.session_state.selected_articles,
                    favorite_categories,
                    excel_company_categories
                )
            st.download_button(
                label="📥 맞춤 엑셀 다운로드",
                data=excel_bytes.getvalue(),
                file_name="뉴스요약_맞춤형.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# 날짜 변경 시 필터링
def filter_articles_by_date():
    st.session_state.filtered_results = {}
    for keyword, articles in st.session_state.search_results.items():
        filtered = [
            a for a in articles
            if st.session_state["start_date"] <= datetime.strptime(a['date'], "%Y-%m-%d").date() <= st.session_state["end_date"]
        ]
        if filtered:
            st.session_state.filtered_results[keyword] = filtered

# 날짜 위젯 값이 바뀌면 자동 필터링
if st.session_state.search_results:
    filter_articles_by_date()
    filtered_results = {}
    for keyword, articles in st.session_state.filtered_results.items():
        filtered_articles = [a for a in articles if article_passes_all_filters(a)]
        if filtered_articles:
            filtered_results[keyword] = filtered_articles
    render_articles_with_single_summary_and_telegram(
        filtered_results,
        st.session_state.show_limit,
        show_sentiment_badge=st.session_state.get("show_sentiment_badge", False),
        enable_summary=st.session_state.get("enable_summary", True)
    )
