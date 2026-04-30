import streamlit as st
from datetime import datetime, timedelta
import urllib.parse
import requests
import re
import json
import os
from deep_translator import GoogleTranslator

# --- 0. API 키 소진 관리 ---
STATUS_FILE = "api_status.json"

def get_api_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    return {"exhausted_month": None}

def set_api_exhausted():
    current_month = datetime.today().strftime("%Y-%m")
    with open(STATUS_FILE, "w") as f:
        json.dump({"exhausted_month": current_month}, f)

api_status = get_api_status()
current_month = datetime.today().strftime("%Y-%m")
is_exhausted = (api_status.get("exhausted_month") == current_month)

def ensure_korean_name(name):
    if not name:
        return name
    # 한글이 포함되어 있으면 원본 반환
    if re.search(r'[가-힣]', name):
        return name
    # 한글이 없는 경우(현지어 또는 영문) 한국어로 번역
    try:
        translated = GoogleTranslator(source='auto', target='ko').translate(name)
        return translated if translated else name
    except Exception:
        return name

# 페이지 기본 설정
st.set_page_config(page_title="글로벌 최저가 숙소 검색", page_icon="🏨", layout="centered")

# 세션 상태 초기화
if "search_results" not in st.session_state:
    st.session_state["search_results"] = None
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 1
if "key_validation_msg" not in st.session_state:
    st.session_state["key_validation_msg"] = None
if "searched_region" not in st.session_state:
    st.session_state["searched_region"] = ""
if "searched_dates" not in st.session_state:
    st.session_state["searched_dates"] = (None, None)

@st.cache_data(ttl=3600, show_spinner=False)
def check_image_valid(url):
    try:
        resp = requests.get(url, timeout=0.5, stream=True)
        return resp.status_code == 200
    except Exception:
        return False

# --- 사이드바: API 설정 ---
with st.sidebar:
    st.header("⚙️ API 설정")
    
    # 동적 렌더링을 위한 공간 확보
    quota_placeholder = st.empty()
    status_placeholder = st.empty()
        
    st.markdown("**개인 SerpApi Key 입력 (선택)**")
    col_k1, col_k2 = st.columns([3, 1])
    with col_k1:
        user_api_key = st.text_input("개인 SerpApi Key 입력", type="password", placeholder="여기에 키를 입력하세요", label_visibility="collapsed")
    with col_k2:
        apply_btn = st.button("적용", use_container_width=True)
        
    validation_placeholder = st.empty()
    
    if apply_btn:
        if not user_api_key:
            st.session_state["key_validation_msg"] = ("error", "키를 입력해 주세요.")
        else:
            try:
                test_resp = requests.get(f"https://serpapi.com/account.json?api_key={user_api_key}", timeout=3)
                if test_resp.status_code == 200 and "error" not in test_resp.json():
                    st.session_state["key_validation_msg"] = ("success", "✅ 개인 키가 정상적으로 활성화되었습니다!")
                else:
                    st.session_state["key_validation_msg"] = ("error", "올바르지 않은 키입니다. 다시 확인해 주세요.")
            except Exception:
                st.session_state["key_validation_msg"] = ("error", "API 연결 오류가 발생했습니다.")
                
    if st.session_state["key_validation_msg"]:
        msg_type, msg_text = st.session_state["key_validation_msg"]
        if msg_type == "success":
            validation_placeholder.success(msg_text)
        else:
            validation_placeholder.error(msg_text)
            
    st.markdown("---")
    st.markdown("""
💡 **Tips**
- 기본 키 잔여량이 모두 소진되면 검색이 일시 중지됩니다.
- [SerpApi](https://serpapi.com/) 무료 회원가입 시 매월 **250건의 무료 검색**이 제공됩니다.
- **키 발급 방법**: 가입 후 대시보드의 **'Your Account'** 탭에서 `Your Private API Key`를 복사할 수 있습니다.
- 매월 1일이 되면 기본 키(250건)로 자동 전환되며, 소진 시 개인 키를 입력하면 계속 검색 가능합니다.
""")

# --- API 키 결정 및 잔여량 확인 ---
active_api_key = user_api_key
sys_api_key = None

try:
    sys_api_key = st.secrets.get("SERPAPI_KEY")
except FileNotFoundError:
    pass
    
if not active_api_key and not is_exhausted:
    active_api_key = sys_api_key

# 잔여 횟수 조회 (무료로 호출됨)
searches_left = None
if active_api_key:
    try:
        acc_resp = requests.get(f"https://serpapi.com/account.json?api_key={active_api_key}", timeout=3)
        if acc_resp.status_code == 200:
            searches_left = acc_resp.json().get("total_searches_left")
    except Exception:
        pass

# 상태 및 잔여 횟수 렌더링
if searches_left is not None:
    quota_placeholder.info(f"🔎 **현재 남은 검색 횟수**: {searches_left}회")

if is_exhausted:
    status_placeholder.error("⚠️ 기본 키 할당량이 모두 소진되었습니다. 개인 키를 아래에 입력해 주세요.")
else:
    status_placeholder.success("✅ 시스템 기본 키 작동 중입니다.")

st.title("🏨 최저가 숙소 통합 검색")
st.markdown("글로벌(Agoda, Booking.com) 및 국내 플랫폼의 최저가를 비교하고 숨겨진 할인을 찾아보세요.")

# --- 1. 검색 조건 입력 영역 ---
st.subheader("🔍 검색 조건")

col1, col2 = st.columns(2)
with col1:
    region = st.text_input("지역명 또는 도시명", placeholder="예: 오사카, 제주도")
with col2:
    today = datetime.today()
    default_checkin = today + timedelta(days=7)
    default_checkout = default_checkin + timedelta(days=2)
    
    dates = st.date_input(
        "체크인 / 체크아웃",
        value=(default_checkin, default_checkout),
        min_value=today,
        format="YYYY.MM.DD"
    )

col3, col4, col5 = st.columns(3)
with col3:
    adults = st.number_input("성인 인원수", min_value=1, value=2)
with col4:
    children = st.number_input("아동 인원수", min_value=0, value=0)
with col5:
    rooms = st.number_input("객실 수", min_value=1, value=1)

child_ages = []
if children > 0:
    st.markdown("**아동 나이 입력 (만 나이)**")
    cols = st.columns(children)
    for i in range(children):
        with cols[i]:
            age = st.number_input(f"아동 {i+1}", min_value=0, max_value=17, value=7, key=f"child_age_{i}")
            child_ages.append(age)

# --- 2. 필터 영역 ---
with st.expander("⚙️ 상세 필터 (선택)"):
    budget = st.slider("1박당 예산 범위 (원)", min_value=10000, max_value=1000000, value=(50000, 300000), step=10000)
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        acc_type = st.multiselect(
            "숙소 유형",
            options=["호텔", "리조트", "펜션/풀빌라", "게스트하우스/호스텔", "모텔"],
            placeholder="선택하지 않으면 전체 조회"
        )
    with col_f2:
        options = st.multiselect(
            "필수 옵션",
            options=["조식 포함", "무료 취소 가능", "수영장", "반려동물 동반"],
            placeholder="선택하지 않으면 전체 조회"
        )

# --- 3. 검색 로직 ---
st.markdown("---")

def fetch_hotels(api_key, query, check_in, check_out, adults, children_count, child_ages_list, max_pages=3):
    params = {
        "engine": "google_hotels",
        "q": query,
        "check_in_date": check_in.strftime("%Y-%m-%d"),
        "check_out_date": check_out.strftime("%Y-%m-%d"),
        "adults": adults,
        "currency": "KRW",
        "gl": "kr",
        "hl": "ko",
        "api_key": api_key
    }
    if children_count > 0:
        params["children"] = children_count
        params["children_ages"] = ",".join(map(str, child_ages_list))

    url = "https://serpapi.com/search"
    all_properties = []
    seen_names = set() # 중복 제거용
    is_quota_error = False
    error_msg = ""
    
    for _ in range(max_pages):
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                # 에러 응답인데 200 OK 로 올 수도 있음
                error_msg = data["error"]
                if "quota" in error_msg.lower() or "limit" in error_msg.lower() or "searches" in error_msg.lower():
                    is_quota_error = True
                break
                
            props = data.get("properties", [])
            for p in props:
                name = p.get("name")
                if name:
                    # 해외 언어일 경우 한글로 번역 처리
                    translated_name = ensure_korean_name(name)
                    p["name"] = translated_name
                    
                    if translated_name not in seen_names:
                        seen_names.add(translated_name)
                        all_properties.append(p)
            
            next_page_token = data.get("serpapi_pagination", {}).get("next_page_token")
            if next_page_token:
                params["next_page_token"] = next_page_token
            else:
                break
        elif response.status_code in [400, 429]:
            # 할당량 초과 에러일 확률 높음
            data = response.json()
            error_msg = data.get("error", response.text)
            is_quota_error = True
            break
        else:
            error_msg = response.text
            break
            
    return all_properties, error_msg, is_quota_error

if st.button("🚀 최저가 검색하기", use_container_width=True):
    if not region:
        st.warning("지역명을 입력해주세요!")
    elif len(dates) != 2:
        st.warning("체크인과 체크아웃 날짜를 모두 선택해주세요!")
    else:
        check_in, check_out = dates
        st.session_state["current_page"] = 1 # 검색 시 1페이지로 초기화
        
        if not active_api_key:
            if is_exhausted:
                st.error("기본 키의 할당량이 모두 소진되었습니다. 좌측 사이드바에 개인 API 키를 입력해 주세요.")
            else:
                st.error("시스템에 기본 API 키가 등록되지 않았습니다. 개인 키를 입력해 주세요.")
        else:
            with st.spinner("구글 호텔 데이터를 수집 및 중복 제거 중입니다..."):
                results, error_msg, is_quota_error = fetch_hotels(active_api_key, region, check_in, check_out, adults, children, child_ages, max_pages=3)
                
                if is_quota_error:
                    if active_api_key == sys_api_key:
                        # 기본 시스템 키가 소진된 경우
                        set_api_exhausted()
                        st.rerun() # 즉시 새로고침하여 사이드바 상태 전환 유도
                    else:
                        st.error("입력하신 개인 API 키의 할당량이 소진되었거나 잘못되었습니다.")
                elif error_msg:
                    st.error(f"API 요청 실패: {error_msg}")
                else:
                    st.session_state["search_results"] = results
                    st.session_state["searched_region"] = region
                    st.session_state["searched_dates"] = dates

# --- 4. 결과 출력 및 정렬/페이징 ---
if st.session_state["search_results"] is not None:
    # 1. 예산(budget) 필터 실제 적용
    min_budget, max_budget = budget
    filtered_results = []
    for r in st.session_state["search_results"]:
        price = (r.get("rate_per_night") or {}).get("extracted_lowest")
        if not isinstance(price, (int, float)) or (min_budget <= price <= max_budget):
            filtered_results.append(r)
            
    results = filtered_results
    
    # 2. 박제된 검색 시점의 조건 불러오기
    searched_dates = st.session_state["searched_dates"]
    check_in, check_out = searched_dates if isinstance(searched_dates, tuple) and len(searched_dates) == 2 else (None, None)
    searched_region = st.session_state["searched_region"]
    
    if not results:
        st.warning("검색 결과가 없습니다.")
    else:
        st.success(f"총 {len(results)}개의 중복 없는 숙소를 찾았습니다!")
        
        # 정렬 기능 (검색 결과 상단에 배치)
        sort_method = st.selectbox(
            "📋 결과 정렬", 
            ["추천순 (기본)", "평점 높은순", "가격 낮은순", "가격 높은순"],
            key="sort_selectbox"
        )
        
        if sort_method == "평점 높은순":
            results = sorted(results, key=lambda x: x.get('overall_rating', 0) if isinstance(x.get('overall_rating'), (int, float)) else 0, reverse=True)
        elif sort_method == "가격 낮은순":
            results = sorted(results, key=lambda x: (x.get('rate_per_night') or {}).get('extracted_lowest') if isinstance((x.get('rate_per_night') or {}).get('extracted_lowest'), (int, float)) else float('inf'))
        elif sort_method == "가격 높은순":
            results = sorted(results, key=lambda x: (x.get('rate_per_night') or {}).get('extracted_lowest') if isinstance((x.get('rate_per_night') or {}).get('extracted_lowest'), (int, float)) else 0, reverse=True)

        st.markdown("---")
        
        # 페이징 계산
        items_per_page = 8
        total_pages = max(1, (len(results) - 1) // items_per_page + 1)
        
        # 현재 페이지가 전체 페이지 수를 초과하지 않도록 보정
        if st.session_state["current_page"] > total_pages:
            st.session_state["current_page"] = total_pages
            
        current_page = st.session_state["current_page"]
        
        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_results = results[start_idx:end_idx]
        
        # 상단 페이징 UI
        col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
        with col_p1:
            if st.button("⬅️ 이전 페이지", disabled=(current_page == 1)):
                st.session_state["current_page"] -= 1
                st.rerun()
        with col_p2:
            st.markdown(f"<div style='text-align: center;'><b>페이지 {current_page} / {total_pages}</b></div>", unsafe_allow_html=True)
        with col_p3:
            if st.button("다음 페이지 ➡️", disabled=(current_page == total_pages)):
                st.session_state["current_page"] += 1
                st.rerun()
                
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 리스트 렌더링
        for res in page_results:
            with st.container():
                rc1, rc2 = st.columns([1, 2])
                with rc1:
                    # 이미지 추출
                    placeholder_path = os.path.join(os.path.dirname(__file__), "placeholder.png")
                    img_url = placeholder_path
                    if "images" in res and len(res["images"]) > 0:
                        first_img = res["images"][0]
                        if isinstance(first_img, dict):
                            img_url = first_img.get("thumbnail") or first_img.get("original_image") or img_url
                        elif isinstance(first_img, str):
                            img_url = first_img
                    
                    # 브라우저 엑박(깨진 이미지) 방지: 캐싱된 함수 적용 (성능 획기적 개선)
                    if isinstance(img_url, str) and img_url.startswith("http"):
                        if not check_image_valid(img_url):
                            img_url = placeholder_path
                    else:
                        img_url = placeholder_path
                    
                    try:
                        st.image(img_url, use_container_width=True)
                    except Exception:
                        st.image(placeholder_path, use_container_width=True)
                with rc2:
                    hotel_name = res.get("name", "이름 없음")
                    st.subheader(hotel_name)
                    st.write(f"⭐ 평점: {res.get('overall_rating', 'N/A')} / 5.0")
                    
                    # 최저가 표시
                    price_info = res.get("rate_per_night", {})
                    lowest_price = price_info.get("lowest", "가격 정보 없음")
                    st.markdown(f"**구글 통합 최저가**: {lowest_price}")
                    
                    # 거리 정보 표시 (공항, 역 등)
                    nearby = res.get("nearby_places", [])
                    if nearby:
                        closest_airport = None
                        closest_station = None
                        
                        for place in nearby:
                            name = place.get("name", "")
                            name_lower = name.lower()
                            
                            # 거리(distance)와 소요시간(transportations) 합치기
                            dist = place.get("distance", "")
                            duration_str = ""
                            transports = place.get("transportations", [])
                            if transports:
                                t_type = transports[0].get("type", "")
                                t_dur = transports[0].get("duration", "")
                                if t_type == "Taxi" or t_type == "Driving":
                                    t_kor = "차량"
                                elif t_type == "Public transport":
                                    t_kor = "대중교통"
                                elif t_type == "Walking":
                                    t_kor = "도보"
                                else:
                                    t_kor = "이동"
                                
                                if t_dur:
                                    duration_str = f"({t_kor} {t_dur})"
                            
                            final_info = ""
                            if dist and duration_str:
                                final_info = f"{dist} {duration_str}"
                            elif dist:
                                final_info = dist
                            elif duration_str:
                                final_info = duration_str.replace("(", "").replace(")", "")
                                
                            if not final_info:
                                continue
                                
                            # 공항 찾기 (✈️)
                            if not closest_airport and ("공항" in name_lower or "airport" in name_lower):
                                clean_name = name.replace("국제공항", "").replace("국제 공항", "").replace("공항", "")
                                clean_name = clean_name.replace("International Airport", "").replace("Airport", "").strip()
                                closest_airport = f"✈️ {clean_name}: {final_info}"
                            # 역, 터미널 찾기 (🚉)
                            elif not closest_station and any(x in name_lower for x in ["역", "station", "터미널", "terminal"]):
                                closest_station = f"🚉 {name}: {final_info}"
                                
                        distance_texts = []
                        if closest_airport:
                            distance_texts.append(closest_airport)
                        if closest_station:
                            distance_texts.append(closest_station)
                            
                        # 공항이나 역이 아예 없다면 가장 가까운 명소 하나 표시
                        if not distance_texts and nearby:
                            place = nearby[0]
                            name = place.get("name", "")
                            dist = place.get("distance", "")
                            duration_str = ""
                            transports = place.get("transportations", [])
                            if transports:
                                t_type = transports[0].get("type", "")
                                t_dur = transports[0].get("duration", "")
                                if t_type == "Taxi" or t_type == "Driving":
                                    t_kor = "차량"
                                elif t_type == "Public transport":
                                    t_kor = "대중교통"
                                elif t_type == "Walking":
                                    t_kor = "도보"
                                else:
                                    t_kor = "이동"
                                if t_dur:
                                    duration_str = f"({t_kor} {t_dur})"
                                    
                            final_info = ""
                            if dist and duration_str:
                                final_info = f"{dist} {duration_str}"
                            elif dist:
                                final_info = dist
                            elif duration_str:
                                final_info = duration_str.replace("(", "").replace(")", "")
                                
                            if final_info:
                                distance_texts.append(f"📍 {name}: {final_info}")
                                
                        if distance_texts:
                            st.caption(" | ".join(distance_texts))
                    
                    # 구글 호텔 전용 딥링크 (SerpApi 제공 링크 사용 - 날짜, 인원 자동 적용됨)
                    google_link = res.get("link")
                    # 만약 링크가 google.com이 아닌 공식 홈페이지(마리오트 등)로 곧바로 빠지는 경우, 구글 검색으로 우회
                    if not google_link or "google.com" not in google_link:
                        if check_in and check_out:
                            check_in_str = check_in.strftime('%Y-%m-%d')
                            check_out_str = check_out.strftime('%Y-%m-%d')
                            query_str = f"{searched_region} {hotel_name} {check_in_str} {check_out_str}"
                        else:
                            query_str = f"{searched_region} {hotel_name}"
                        encoded_query = urllib.parse.quote(query_str)
                        google_link = f"https://www.google.com/search?q={encoded_query}"
                    
                    # 네이버 호텔 대신 네이버 지도 검색 딥링크 사용 (네이버는 자체 ID가 없으면 날짜/인원 딥링크 연동 거부)
                    naver_query = f"{searched_region} {hotel_name}"
                    encoded_naver_query = urllib.parse.quote(naver_query)
                    naver_link = f"https://map.naver.com/p/search/{encoded_naver_query}"
                    
                    # 버튼 레이아웃
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        st.markdown(
                            f'''<a href="{google_link}" target="_blank">
                            <button style="width:100%; background-color:#4285F4; color:white; border:none; padding:8px 16px; border-radius:4px; cursor:pointer;">
                            🔍 구글 가격비교 리스트
                            </button></a>''',
                            unsafe_allow_html=True
                        )
                    with col_b2:
                        st.markdown(
                            f'''<a href="{naver_link}" target="_blank">
                            <button style="width:100%; background-color:#03C75A; color:white; border:none; padding:8px 16px; border-radius:4px; cursor:pointer;">
                            🟢 네이버 지도에서 확인
                            </button></a>''',
                            unsafe_allow_html=True
                        )
            st.markdown("---")
            
        # 하단 페이징 UI (상단과 동일하게 제공하여 편의성 향상)
        col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
        with col_b1:
            if st.button("⬅️ 이전 페이지 ", key="btn_prev_bot", disabled=(current_page == 1)):
                st.session_state["current_page"] -= 1
                st.rerun()
        with col_b2:
            st.markdown(f"<div style='text-align: center;'><b>페이지 {current_page} / {total_pages}</b></div>", unsafe_allow_html=True)
        with col_b3:
            if st.button("다음 페이지 ➡️ ", key="btn_next_bot", disabled=(current_page == total_pages)):
                st.session_state["current_page"] += 1
                st.rerun()
