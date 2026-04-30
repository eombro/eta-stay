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
            searches_left = acc_resp.json().get("total_sear
