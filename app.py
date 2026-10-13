import streamlit as st
import pandas as pd
import os
import json
import plotly.express as px
import plotly.graph_objects as go
import duckdb
import time
import re
from datetime import datetime, timedelta
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))

from extractor import process_pdf
from banker import run_ai_audit
from llm_router import invoke_llm, parse_json_safely, get_engine_options, is_google_available, is_groq_available
from chat_engine import ask_financial_data, search_vault
from dashboard_logic import build_dashboard_sections, validate_categorisation
from report_generator import generate_summary_pdf, generate_chat_pdf, generate_anonymized_csv

st.set_page_config(page_title="Pulse AI", page_icon="🏦", layout="wide")

st.markdown("""
<style>
    /* Force a sleek, zoomed-out look */
    html, body, [class*="css"] { font-size: 14px !important; }
    /* Generous bottom padding so footer chat input never obscures messages or tables */
    .block-container { padding-top: 2rem !important; padding-bottom: 7rem !important; max-width: 95% !important; }
    /* Make expanders and tables slightly tighter */
    .streamlit-expanderHeader { font-size: 14px !important; padding: 0.5rem !important; }
    
    /* Fix text and background in the password input box */
    div[data-testid="stTextInput"] input { color: #111827 !important; background-color: #F9FAFB !important; font-weight: bold; }
    /* Fix placeholder text color so it's readable but muted */
    div[data-testid="stTextInput"] input::placeholder { color: #9CA3AF !important; font-weight: normal; }
    
    /* Force the Unlock button to have high contrast (Blue with White text) when enabled */
    div[data-testid="stButton"] button:not(:disabled) { background-color: #2563eb !important; color: #ffffff !important; border: none !important; font-weight: 600 !important; }
    div[data-testid="stButton"] button:not(:disabled):hover { background-color: #1d4ed8 !important; color: #ffffff !important; border: none !important; }
    div[data-testid="stButton"] button:disabled { background-color: #9CA3AF !important; color: #E5E7EB !important; cursor: not-allowed !important; border: none !important; opacity: 0.65 !important; }

    /* High contrast chat bubbles: pure white text */
    [data-testid="stChatMessage"] { background-color: #1E293B !important; }
    [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] span, [data-testid="stChatMessage"] li, [data-testid="stChatMessage"] strong,
    [data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h2, [data-testid="stChatMessage"] h3, [data-testid="stChatMessage"] h4,
    [data-testid="stChatMessage"] h5, [data-testid="stChatMessage"] h6, [data-testid="stChatMessage"] b, [data-testid="stChatMessage"] em { color: #FFFFFF !important; }
    [data-testid="stChatMessage"] code { color: #93C5FD !important; background-color: #0F172A !important; }
    [data-testid="stChatMessage"] div[data-testid="stDataFrame"] * { color: #111827 !important; }

    /* Chat input bar styling: Pure white text */
    div[data-testid="stChatInput"], div[data-testid="stChatInput"] > div {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 24px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15) !important;
    }
    div[data-testid="stChatInput"] textarea,
    div[data-testid="stChatInput"] input,
    div[data-testid="stChatInput"] [contenteditable="true"] {
        color: #FFFFFF !important;
        background-color: transparent !important;
        font-size: 14px !important;
    }
    div[data-testid="stChatInput"] textarea::placeholder,
    div[data-testid="stChatInput"] input::placeholder {
        color: #94A3B8 !important;
    }
    div[data-testid="stChatInput"] button {
        color: #38BDF8 !important;
    }
</style>
""", unsafe_allow_html=True)

try:
    with open("style.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

AUTH_FILE = "auth.json"
MASTER_PASS = os.getenv("MASTER_PASSWORD", "").strip()
raw_passes = os.getenv("RECRUITER_PASSES", "")
INITIAL_PASSES = [p.strip() for p in raw_passes.split(",") if p.strip()]

# Detect if running in local development mode
IS_LOCAL_DEV = os.getenv("DEV_MODE", "").lower() in ("1", "true")

GLOBAL_STATS_FILE = "global_stats.json"
MAX_GLOBAL_AUDITS = 500 if IS_LOCAL_DEV else 50 # Generous limit on localhost

# --- ROLLING 36-HOUR RATE LIMIT LOGIC ---
if not os.path.exists(GLOBAL_STATS_FILE):
    with open(GLOBAL_STATS_FILE, "w") as f:
        json.dump({"audit_timestamps": []}, f, indent=4)

def get_global_audits():
    if not os.path.exists(GLOBAL_STATS_FILE): return 0
    with open(GLOBAL_STATS_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {"audit_timestamps": []}
    
    if "audit_timestamps" not in data:
        data = {"audit_timestamps": []}
        
    now = datetime.now()
    cutoff_time = now - timedelta(hours=36)
    
    valid_timestamps = []
    for ts_str in data["audit_timestamps"]:
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts > cutoff_time:
                valid_timestamps.append(ts_str)
        except ValueError:
            pass
            
    with open(GLOBAL_STATS_FILE, "w") as f:
        json.dump({"audit_timestamps": valid_timestamps}, f, indent=4)
        
    return len(valid_timestamps)

def increment_global_audits():
    if not os.path.exists(GLOBAL_STATS_FILE):
        data = {"audit_timestamps": []}
    else:
        with open(GLOBAL_STATS_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {"audit_timestamps": []}
    
    if "audit_timestamps" not in data:
        data["audit_timestamps"] = []
        
    data["audit_timestamps"].append(datetime.now().isoformat())
    with open(GLOBAL_STATS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def log_app_stat(metric_name):
    """Tracks visits and API calls."""
    if not os.path.exists(GLOBAL_STATS_FILE):
        data = {"audit_timestamps": [], "visits": 0, "gemini": 0, "groq": 0}
    else:
        with open(GLOBAL_STATS_FILE, "r") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {"audit_timestamps": [], "visits": 0, "gemini": 0, "groq": 0}
    
    for k in ["visits", "gemini", "groq"]:
        if k not in data: data[k] = 0
        
    if metric_name in data:
        data[metric_name] += 1
        
    with open(GLOBAL_STATS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_auth_data():
    default_data = {"valid_passes": [p.strip() for p in INITIAL_PASSES if p.strip()], "used_passes": []}
    if not os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "w") as f:
            json.dump(default_data, f, indent=4)
        return default_data

    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        data = default_data

    if "valid_passes" not in data or not isinstance(data["valid_passes"], list):
        data["valid_passes"] = []
    if "used_passes" not in data or not isinstance(data["used_passes"], list):
        data["used_passes"] = []

    # Sync any INITIAL_PASSES from env that are not yet tracked in valid or used
    dirty = False
    used_lower = {u.lower() for u in data["used_passes"]}
    valid_lower = {v.lower() for v in data["valid_passes"]}
    for p in INITIAL_PASSES:
        p_clean = p.strip()
        if p_clean and p_clean.lower() not in valid_lower and p_clean.lower() not in used_lower:
            data["valid_passes"].append(p_clean)
            valid_lower.add(p_clean.lower())
            dirty = True

    if dirty:
        with open(AUTH_FILE, "w") as f:
            json.dump(data, f, indent=4)
    return data

# Initialize auth on startup
auth_state = load_auth_data()

# --- VISITOR TRACKING ---
if "has_been_counted" not in st.session_state:
    st.session_state.has_been_counted = True
    log_app_stat("visits")

if "audit_complete" not in st.session_state:
    st.session_state.audit_complete = False
if "api_calls_used" not in st.session_state:
    st.session_state.api_calls_used = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_authorized" not in st.session_state:
    st.session_state.chat_authorized = False
if "auth_role" not in st.session_state:
    st.session_state.auth_role = None 
if "chat_allowance" not in st.session_state:
    st.session_state.chat_allowance = 3
if "base_chats_used" not in st.session_state:
    st.session_state.base_chats_used = 0
if "byok_keys" not in st.session_state:
    st.session_state.byok_keys = None
if "master_pdf_dict" not in st.session_state:
    st.session_state.master_pdf_dict = {} 
if "failed_filenames" not in st.session_state:
    st.session_state.failed_filenames = set()
if "upload_banned" not in st.session_state:
    st.session_state.upload_banned = False
if "locked_add_more" not in st.session_state:
    st.session_state.locked_add_more = False
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "📊 Overview Dashboard"

st.sidebar.markdown("<h1 style='color: white; font-weight: 800; font-size: 1.8rem;'>🏦 Pulse AI</h1>", unsafe_allow_html=True)

# --- 1. GLOBAL TRACKER & ACCESS LEVEL ---
current_global = get_global_audits()
st.sidebar.markdown(f"<div style='color: #9CA3AF; font-size: 13px;'>🌐 Global Audits: <b>{current_global} / {MAX_GLOBAL_AUDITS}</b></div>", unsafe_allow_html=True)

role = st.session_state.auth_role

# --- 1. ACCESS LEVEL & CODE ENTRY ---
if role == "master":
    st.sidebar.markdown("<div style='color: #10B981; font-size: 14px; margin-top: 5px; margin-bottom: 5px;'>🔓 <b>Access Level:</b> Master</div>", unsafe_allow_html=True)
elif role == "recruiter":
    st.sidebar.markdown("<div style='color: #F59E0B; font-size: 14px; margin-top: 5px; margin-bottom: 5px;'>🔓 <b>Access Level:</b> Code User</div>", unsafe_allow_html=True)
else:
    pwd = st.sidebar.text_input("Enter Access Code:", type="password", key="sidebar_pwd")
    if st.sidebar.button("Unlock", use_container_width=True):
        pwd = pwd.strip() 
        if pwd == MASTER_PASS and pwd != "":
            st.session_state.chat_authorized = True
            st.session_state.auth_role = "master"
            st.session_state.chat_allowance = 9999
            st.rerun()
        else:
            auth_data = load_auth_data()
            used_passes = auth_data.get("used_passes", [])
            valid_passes = auth_data.get("valid_passes", [])

            is_used = any(pwd.lower() == u.lower() for u in used_passes)
            matched_pass = next((v for v in valid_passes if v.lower() == pwd.lower()), None)

            if is_used:
                st.sidebar.error("❌ This code has already been redeemed (single-use only).")
            elif matched_pass:
                st.session_state.chat_authorized = True
                st.session_state.auth_role = "recruiter"
                st.session_state.chat_allowance = 10
                auth_data["valid_passes"].remove(matched_pass)
                auth_data["used_passes"].append(matched_pass)
                with open(AUTH_FILE, "w") as f:
                    json.dump(auth_data, f, indent=4)
                st.rerun()
            else:
                st.sidebar.error("Invalid Code.")

# --- 2. BRING YOUR OWN KEY (BYOK) DIRECTLY BELOW CODE ENTRY ---
with st.sidebar.expander("🔑 Custom API Keys (BYOK)", expanded=False):
    st.markdown("<p style='font-size: 12px; color: #94A3B8; margin-bottom: 8px;'>Optional: Enter personal keys to bypass limits. Stored strictly in-memory.</p>", unsafe_allow_html=True)
    byok_g = st.text_input("Gemini API Key", type="password", key="byok_gemini_input", placeholder="AIzaSy...")
    byok_q = st.text_input("Groq API Key", type="password", key="byok_groq_input", placeholder="gsk_...")
    byok_c = st.text_input("Claude API Key", type="password", key="byok_claude_input", placeholder="sk-ant-...")
    if byok_g or byok_q or byok_c:
        st.session_state.byok_keys = {
            "google": byok_g.strip() if byok_g else None,
            "groq": byok_q.strip() if byok_q else None,
            "anthropic": byok_c.strip() if byok_c else None
        }
        st.caption("🔒 BYOK active for this session only.")
    else:
        st.session_state.byok_keys = None

st.sidebar.write("---")

# Engine options from router
available_engines = get_engine_options()

# --- 3. NAVIGATION & CHAT QUOTAS ---
if st.session_state.audit_complete:
    nav_options = ["📊 Overview Dashboard", "💬 AI Chat Assistant", "📁 Add More Statements"]
    if st.session_state.nav_page not in nav_options:
        st.session_state.nav_page = "📊 Overview Dashboard"
        
    default_idx = nav_options.index(st.session_state.nav_page)
    page_selection = st.sidebar.radio("Navigation", nav_options, index=default_idx)
    
    if page_selection != st.session_state.nav_page:
        st.session_state.nav_page = page_selection
        st.rerun()
        
    st.sidebar.write("---")
    
    if role == "recruiter":
        st.sidebar.markdown(f"<div style='color: #F59E0B; font-size: 14px;'>💬 Chats Remaining: <b>{st.session_state.chat_allowance} / 10</b></div>", unsafe_allow_html=True)
        st.session_state.ai_choice = available_engines[0]
    elif role == "master":
        st.sidebar.markdown("<div style='color: #10B981; font-size: 14px;'>💬 Chats Remaining: <b>Unlimited</b></div>", unsafe_allow_html=True)
        st.sidebar.write("<br>", unsafe_allow_html=True)
        st.session_state.ai_choice = st.sidebar.radio("🧠 Select AI Engine", available_engines)
    else:
        st.sidebar.markdown(f"<div style='color: #EF4444; font-size: 14px;'>💬 Chats Remaining: <b>{st.session_state.chat_allowance} / 3</b></div>", unsafe_allow_html=True)
        st.session_state.ai_choice = available_engines[0]
else:
    page_selection = "Setup"
    st.sidebar.markdown("<div style='color: #9CA3AF; font-size: 14px;'>Upload statements to unlock navigation.</div>", unsafe_allow_html=True)
    if "ai_choice" not in st.session_state:
        st.session_state.ai_choice = available_engines[0]

def draw_horizontal_grid(summary_chunk, master_df):
    cols = st.columns(len(summary_chunk))
    for col, (index, row) in zip(cols, summary_chunk.iterrows()):
        cat_name = row['Category']
        cat_total = row['Total_Spent']
        tx_cnt = row.get('Tx_Count')
        pct = row.get('Percentage')
        cnt_info = f" • {int(tx_cnt)} txns" if pd.notna(tx_cnt) and tx_cnt else ""
        pct_info = f" ({pct:.1f}%)" if pd.notna(pct) and pct else ""

        is_two_way = row.get('Is_Two_Way', False)
        received = row.get('Total_Received', 0.0)
        net_flow = row.get('Net_Flow', 0.0)
        total_tx = row.get('Total_Tx', tx_cnt)

        with col:
            if is_two_way and received > 0:
                net_sign = "+" if net_flow >= 0 else ""
                title = f"🔄 {str(cat_name).upper()} | Out: £{cat_total:,.2f} • In: £{received:,.2f} • Net: {net_sign}£{net_flow:,.2f} • {int(total_tx)} txns"
                with st.expander(title):
                    filtered_df = master_df[master_df['Category'] == cat_name].copy()
                    rename_map = {'Clean_Description': 'Counterparty / Description', 'Direction': 'Flow'}
                    cols_to_view = [c for c in ['Date', 'Bank', 'Clean_Description', 'Direction', 'Amount'] if c in filtered_df.columns]
                    display_df = filtered_df[cols_to_view].rename(columns=rename_map)
                    st.dataframe(display_df, hide_index=True, column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")}, use_container_width=True)
            else:
                title = f"📁 {str(cat_name).upper()} | £{cat_total:,.2f}{pct_info}{cnt_info}"
                with st.expander(title):
                    filtered_df = master_df[(master_df['Category'] == cat_name) & (master_df['Direction'] == 'Out')].copy()
                    rename_map = {'Clean_Description': 'Merchant / Description'}
                    cols_to_view = [c for c in ['Date', 'Bank', 'Clean_Description', 'Amount'] if c in filtered_df.columns]
                    display_df = filtered_df[cols_to_view].rename(columns=rename_map)
                    st.dataframe(display_df, hide_index=True, column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")}, use_container_width=True)

def draw_inflows_grid(inflow_chunk, cat_df):
    cols = st.columns(len(inflow_chunk))
    for col, (index, row) in zip(cols, inflow_chunk.iterrows()):
        cat_name = row['Category']
        cat_total = row['Total_Inflow']
        tx_cnt = row.get('Tx_Count')
        pct = row.get('Percentage')
        cnt_info = f" • {int(tx_cnt)} txns" if pd.notna(tx_cnt) and tx_cnt else ""
        pct_info = f" ({pct:.1f}%)" if pd.notna(pct) and pct else ""
        
        with col:
            with st.expander(f"📥 {str(cat_name).upper()} | £{cat_total:,.2f}{pct_info}{cnt_info}"):
                filtered_df = cat_df[(cat_df['Category'] == cat_name) & (cat_df['Direction'] == 'In')].copy()
                rename_map = {'Clean_Description': 'Payer / Source'}
                cols_to_view = [c for c in ['Date', 'Bank', 'Clean_Description', 'Amount'] if c in filtered_df.columns]
                display_df = filtered_df[cols_to_view].rename(columns=rename_map)
                st.dataframe(display_df, hide_index=True, column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")}, use_container_width=True)

# ==========================================
# PAGE: SETUP / ADD MORE
# ==========================================
if page_selection == "Setup" or page_selection == "📁 Add More Statements":
    current_audits = get_global_audits()
    if current_audits >= MAX_GLOBAL_AUDITS and not IS_LOCAL_DEV:
        st.error("🚨 **GLOBAL CREDIT LIMIT REACHED**")
        st.markdown(f"""
            <div style="background-color: #FEE2E2; padding: 20px; border-radius: 12px; border: 2px solid #EF4444; text-align: center; margin-bottom: 25px;">
                <h3 style="color: #991B1B; margin: 0;">System Paused</h3>
                <p style="color: #B91C1C; font-size: 15px; margin-top: 10px;">
                    The global demo limit of <b>{MAX_GLOBAL_AUDITS} audits</b> has been reached for this billing cycle to prevent API overages. 
                </p>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<h1 style='color: #111827; font-weight: 800;'>Welcome to Pulse ⚡</h1>", unsafe_allow_html=True)

    showcase_url = os.getenv("SHOWCASE_VIDEO_URL")
    if showcase_url:
        with st.expander("📺 Watch the 60-Second Showcase"):
            st.video(showcase_url)
    
    if page_selection == "Setup" and not st.session_state.chat_authorized:
        st.info("ℹ️ **Basic Demo Mode:** Limited to 100 transactions. AI Chat and appending statements are locked. Use the sidebar to enter an Access Code.")

    if page_selection == "Setup":
        st.markdown("""
        <div style='background-color: #F3F4F6; padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #10B981;'>
            <h4 style='color: #111827; margin-top: 0; margin-bottom: 10px;'>🔒 100% Privacy Guaranteed</h4>
            <ul style='color: #4B5563; font-size: 14px; margin-bottom: 0;'>
                <li><b>Volatile Memory Only:</b> Your PDFs are processed in temporary RAM and instantly wiped when you leave.</li>
                <li><b>Exact Math Reconciliation:</b> Transaction amounts and directions (In/Out) are verified against the bank's own printed summaries.</li>
                <li><b>Anonymized AI:</b> Personal identifiers and human names are automatically redacted to initials before audit.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    if "processed_filenames" not in st.session_state:
        st.session_state.processed_filenames = set()
        
    role = st.session_state.auth_role
    max_allowed_files = 100 if role == "master" else (7 if role == "recruiter" else 3)
    
    current_file_count = len(st.session_state.processed_filenames)
    files_remaining = max_allowed_files - current_file_count

    is_locked = False
    if st.session_state.upload_banned and role != "master" and not IS_LOCAL_DEV:
        st.error("🚫 **Upload Banned:** You have uploaded 3 invalid/non-statement files. This feature is now locked to prevent abuse.")
        is_locked = True
    elif page_selection == "📁 Add More Statements":
        if role == "master":
            st.info("ℹ️ **Master Access:** You can append unlimited statements.")
        elif files_remaining <= 0:
            role_label = "Code User (7)" if role == "recruiter" else "Base User (3)"
            st.error(f"🔒 **{role_label} Limit:** You have reached the maximum limit of {max_allowed_files} statements.")
            is_locked = True
        elif st.session_state.locked_add_more and role != "master" and not IS_LOCAL_DEV:
            st.warning("⚠️ This feature is locked. You've already appended your data once.")
            is_locked = True
        else:
            role_label = "Code User" if role == "recruiter" else "Base User"
            st.markdown(f"""
            <div style="background-color: #FEF3C7; border: 1.5px solid #F59E0B; border-radius: 10px; padding: 12px 16px; margin-bottom: 16px;">
                <span style="color: #92400E; font-size: 14px; font-weight: 700;">
                    ⚠️ {role_label}: You can append {files_remaining} more statement(s) (Maximum: {max_allowed_files}).
                </span>
            </div>
            """, unsafe_allow_html=True)

    if not is_locked and files_remaining > 0:
        uploaded_files = st.file_uploader(f"Drop your HSBC, Santander, Starling, Revolut, or Nationwide PDFs here ({files_remaining} valid file(s) remaining)", accept_multiple_files=True, type=['pdf'])

        if uploaded_files:
            st.write("---")
            st.markdown("<h3 style='color: #111827;'>🕵️‍♂️ Extraction Log</h3>", unsafe_allow_html=True)
            
            for file in uploaded_files:
                if (max_allowed_files - len(st.session_state.processed_filenames)) <= 0 and role != "master":
                    st.warning("⚠️ Successful statement limit reached. Ignoring any remaining files.")
                    break
                
                if st.session_state.upload_banned and role != "master" and not IS_LOCAL_DEV:
                    break

                if file.name in st.session_state.processed_filenames or file.name in st.session_state.failed_filenames:
                    continue 

                # Security: Max file size validation (10MB limit)
                if hasattr(file, 'size') and file.size > 10 * 1024 * 1024:
                    st.error(f"🚨 {file.name}: Exceeds 10MB safety limit. File rejected.")
                    st.session_state.failed_filenames.add(file.name)
                    continue
                    
                df, message = process_pdf(file, file.name)
                if df is not None:
                    if len(df) > 500 and role != "master" and not IS_LOCAL_DEV:
                        df = df.head(500)
                        message += " (Capped at 500 rows for statement safety)"
                    st.success(f"{message}")
                    st.session_state.master_pdf_dict[file.name] = df
                    st.session_state.processed_filenames.add(file.name)
                else:
                    st.warning(f"{message}")
                    st.session_state.failed_filenames.add(file.name) 
                    
                    if role != "master" and not IS_LOCAL_DEV:
                        if len(st.session_state.failed_filenames) >= 3:
                            st.session_state.upload_banned = True
                            st.error("🚫 You have uploaded 3 invalid files. Uploads are now locked.")
                            break

        # --- TEST STATEMENT LOADER (RESTRICTED STRICTLY TO MASTER ACCESS) ---
        has_statements = bool(st.session_state.master_pdf_dict)
        if role == "master":
            with st.expander("🧪 Master Dev: Load Sample Statement (100 Transactions)", expanded=not has_statements):
                st.markdown(
                    """
                    <p style='color: #4B5563; font-size: 13px;'>
                    Quickly load 1 standard sample statement (100 transactions: salary, commute, utilities, groceries, and dining) to verify analytics and categorization.
                    </p>
                    """,
                    unsafe_allow_html=True
                )

                col_btn1, col_btn2 = st.columns([2, 1])
                with col_btn1:
                    load_clicked = st.button("🚀 Load Sample Statement (100 Txns)", type="primary", use_container_width=True)
                with col_btn2:
                    if has_statements and st.button("🗑️ Reset / Clear Data", type="secondary", use_container_width=True):
                        st.session_state.master_pdf_dict = {}
                        st.session_state.processed_filenames = set()
                        st.session_state.failed_filenames = set()
                        st.session_state.audit_complete = False
                        st.session_state.analyzed_df = None
                        st.session_state.summary_df = None
                        st.session_state.roast_text = None
                        st.session_state.audit_running = False
                        if os.path.exists("memory.json"):
                            try:
                                os.remove("memory.json")
                            except Exception:
                                pass
                        st.rerun()

                if load_clicked:
                    if os.path.exists("memory.json"):
                        try:
                            os.remove("memory.json")
                        except Exception:
                            pass
                    
                    st.session_state.master_pdf_dict = {}
                    st.session_state.processed_filenames = set()
                    st.session_state.failed_filenames = set()
                    st.session_state.audit_complete = False
                    st.session_state.analyzed_df = None
                    st.session_state.summary_df = None
                    st.session_state.roast_text = None
                    st.session_state.audit_running = False

                    sample_pdf_path = os.path.join("pdfs", "synthetic_barclays_current.pdf")
                    if os.path.exists(sample_pdf_path):
                        with open(sample_pdf_path, "rb") as f:
                            df, message = process_pdf(f, "sample_current_statement.pdf")
                            if df is not None:
                                st.session_state.master_pdf_dict["sample_current_statement.pdf"] = df
                                st.session_state.processed_filenames.add("sample_current_statement.pdf")
                                st.session_state.virtual_generated = True
                                st.success("✅ Successfully loaded sample test statement (100 transactions).")
                                st.rerun()
                            else:
                                st.error(f"Error loading statement: {message}")
                    else:
                        st.error("Sample statement file not found in pdfs/ directory.")
        elif has_statements:
            if st.button("🗑️ Reset / Clear Statements", type="secondary"):
                st.session_state.master_pdf_dict = {}
                st.session_state.processed_filenames = set()
                st.session_state.failed_filenames = set()
                st.session_state.audit_complete = False
                st.session_state.analyzed_df = None
                st.session_state.summary_df = None
                st.session_state.roast_text = None
                st.session_state.audit_running = False
                st.rerun()


    if st.session_state.master_pdf_dict:
        st.write("---")
        master_df = pd.concat(list(st.session_state.master_pdf_dict.values()), ignore_index=True)
        
        # Format and sort
        master_df['Original_Order'] = range(len(master_df))
        master_df['Date_Sorter'] = pd.to_datetime(master_df['Date'], format='mixed', errors='coerce')
        master_df = master_df.sort_values(by=['Date_Sorter', 'Original_Order'], ascending=[True, True]).reset_index(drop=True)
        master_df['Timeline_ID'] = range(1, len(master_df) + 1)
        master_df['Amount'] = pd.to_numeric(master_df['Amount'], errors='coerce').fillna(0.0)
        
        if 'Direction' not in master_df.columns:
            master_df['Direction'] = 'Out'

        if role == "master" or IS_LOCAL_DEV:
            limit = None
        elif role == "recruiter":
            limit = 3500
        else:
            limit = 1500

        if limit and len(master_df) > limit:
            st.warning(f"⚠️ Combined analysis is capped at {limit} transactions for safety.")
            master_df = master_df.head(limit)
            
        if page_selection == "📁 Add More Statements" and st.session_state.get("locked_add_more", False) and role != "master" and not IS_LOCAL_DEV:
            st.info("ℹ️ Your additional statements have already been merged and audited into your dashboard.")
        elif st.session_state.get("is_processing", False):
            # --- PROCESSING SCREEN (ISOLATED VIEW TO PREVENT DUPLICATION) ---
            with st.status("🧠 Running AI Financial Audit...", expanded=True) as status_box:
                st.write("🔍 Anonymizing & categorizing transactions across taxonomy...")
                ai_choice = st.session_state.get("ai_choice", available_engines[0])
                try:
                    categorized_df, summary_df, roast = run_ai_audit(master_df, ai_choice)
                    increment_global_audits()
                    log_app_stat("gemini" if "Gemini" in ai_choice else "groq")
                    
                    st.session_state.categorized_df = categorized_df
                    st.session_state.summary_df = summary_df
                    st.session_state.roast = roast
                    st.session_state.audit_complete = True
                    
                    if page_selection == "📁 Add More Statements":
                        st.session_state.locked_add_more = True
                    
                    st.session_state.nav_page = "📊 Overview Dashboard"
                    status_box.update(label="✅ Audit Complete! Loading Dashboard...", state="complete")
                except Exception as e:
                    st.error(f"🚨 Audit failed to complete: {e}. Please try again.")
                finally:
                    st.session_state.is_processing = False
                st.rerun()
        else:
            display_cols = [c for c in ['Date', 'Bank', 'Description', 'Direction', 'Amount'] if c in master_df.columns]
            st.dataframe(master_df[display_cols], use_container_width=True, hide_index=True, column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")})
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                current_audits = get_global_audits()
                if current_audits >= MAX_GLOBAL_AUDITS and not IS_LOCAL_DEV:
                    st.error("🛑 The live demo limit has been reached to prevent API abuse.")
                    st.button("Run AI Categorization (LOCKED)", use_container_width=True, disabled=True, key="locked_audit_btn")
                else:
                    if st.button("🧠 Run AI Categorization & Audit", use_container_width=True, type="primary", key="run_ai_audit_btn"):
                        st.session_state.is_processing = True
                        st.rerun()

# ==========================================
# PAGE: OVERVIEW DASHBOARD
# ==========================================
elif page_selection == "📊 Overview Dashboard":
    st.components.v1.html(
        """
        <script>
            var body = window.parent.document.querySelector(".main");
            if (body) { body.scrollTop = 0; }
            window.parent.scrollTo(0, 0);
        </script>
        """, 
        height=0
    )

    summary_df = st.session_state.summary_df if not st.session_state.summary_df.empty else pd.DataFrame(columns=['Category', 'Total_Spent'])
    
    c_ov_title, c_ov_export = st.columns([2, 1])
    with c_ov_title:
        st.markdown("<h1 style='color: #111827; font-weight: 800;'>📊 Global Overview</h1>", unsafe_allow_html=True)
    with c_ov_export:
        summary_pdf = generate_summary_pdf(st.session_state.categorized_df, summary_df, st.session_state.roast)
        anon_csv = generate_anonymized_csv(st.session_state.categorized_df)
        d_c1, d_c2 = st.columns(2)
        with d_c1:
            st.download_button(
                "📄 PDF Audit",
                data=summary_pdf,
                file_name="pulse_financial_audit.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        with d_c2:
            st.download_button(
                "📥 Clean CSV",
                data=anon_csv,
                file_name="pulse_transactions_clean.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%); padding: 25px; border-radius: 16px; color: white; font-size: 1.1rem; font-weight: 600; text-align: center; box-shadow: 0 10px 25px rgba(255, 65, 108, 0.3); margin-bottom: 30px;">
        🔥 AI Verdict: {st.session_state.roast}
    </div>
    """, unsafe_allow_html=True)
    
    total_spend = summary_df['Total_Spent'].sum() if not summary_df.empty else 0.0
    top_cat_name = summary_df.iloc[0]['Category'] if not summary_df.empty else "N/A"
    top_cat_val = summary_df.iloc[0]['Total_Spent'] if not summary_df.empty else 0.0
    
    # Accurate inflow calculation
    cat_df = st.session_state.categorized_df
    total_income = cat_df[cat_df['Direction'] == 'In']['Amount'].sum() if 'Direction' in cat_df.columns else 0.0
    net_savings = total_income - total_spend

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Spending (Out)", f"£{total_spend:,.2f}")
    m2.metric("Total Income (In)", f"£{total_income:,.2f}")
    m3.metric("Net Cash Flow", f"£{net_savings:,.2f}", delta=f"{'+' if net_savings >= 0 else ''}£{net_savings:,.2f}")
    m4.metric(f"Top Spend: {top_cat_name}", f"£{top_cat_val:,.2f}")
    
    st.write("<br>", unsafe_allow_html=True)
    
    # Visual Spending Breakdown (Ranked Horizontal Bar Chart + Zero-Collision Donut)
    if not summary_df.empty:
        chart_df = summary_df[summary_df['Total_Spent'] > 0].copy()
        
        if not chart_df.empty:
            total_chart_spend = chart_df['Total_Spent'].sum()
            chart_df['Percent'] = (chart_df['Total_Spent'] / total_chart_spend * 100).round(1)
            # Sort ascending so the largest spending bar renders at the very top of the horizontal bar chart
            chart_df_sorted = chart_df.sort_values(by='Total_Spent', ascending=True)
            chart_df_sorted['Bar_Label'] = chart_df_sorted.apply(
                lambda r: f"£{r['Total_Spent']:,.2f} ({r['Percent']}%)", axis=1
            )
            
            tab_bar, tab_donut = st.tabs(["📊 Ranked Spending Breakdown", "🍩 Category Share Donut"])
            
            with tab_bar:
                # Dynamic height ensures generous spacing whether 5 or 25 categories
                bar_height = max(420, len(chart_df_sorted) * 32 + 90)
                fig_bar = go.Figure(go.Bar(
                    x=chart_df_sorted['Total_Spent'],
                    y=chart_df_sorted['Category'],
                    orientation='h',
                    text=chart_df_sorted['Bar_Label'],
                    textposition='outside',
                    textfont=dict(color='#0F172A', size=12, family='Inter, system-ui, sans-serif'),
                    cliponaxis=False,
                    marker=dict(
                        color=chart_df_sorted['Total_Spent'],
                        colorscale=[[0, '#818CF8'], [0.5, '#4F46E5'], [1.0, '#312E81']],
                        line=dict(color='#FFFFFF', width=1)
                    ),
                    hovertemplate="<b>%{y}</b><br>Total Spend: £%{x:,.2f}<br>Share: %{text}<extra></extra>"
                ))
                fig_bar.update_layout(
                    font=dict(color="#0F172A", family="Inter, system-ui, sans-serif"),
                    title=dict(
                        text="<b>Spending Breakdown by Category (Ranked Highest to Lowest)</b>",
                        font=dict(size=18, color="#0F172A", family="Inter, system-ui, sans-serif"),
                        x=0.0
                    ),
                    xaxis=dict(
                        title=dict(text="Total Outflow (£)", font=dict(color="#0F172A", size=13)),
                        tickfont=dict(color="#0F172A", size=11),
                        tickprefix="£",
                        tickformat=",.0f",
                        gridcolor="#E2E8F0",
                        showgrid=True,
                        zeroline=False
                    ),
                    yaxis=dict(
                        title="",
                        tickfont=dict(size=13, color="#0F172A", family="Inter, system-ui, sans-serif"),
                        automargin=True
                    ),
                    margin=dict(l=10, r=80, t=50, b=40),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    height=bar_height
                )
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with tab_donut:
                col_d1, col_d2, col_d3 = st.columns([1, 4, 1])
                with col_d2:
                    # Clean donut with inside text and automatic hiding of colliding micro-slice labels
                    fig_donut = go.Figure(data=[go.Pie(
                        labels=chart_df['Category'].tolist(), 
                        values=chart_df['Total_Spent'].tolist(), 
                        hole=0.50,
                        textposition='inside',
                        textinfo='percent',
                        insidetextfont=dict(size=12, color="#FFFFFF"),
                        marker=dict(line=dict(color='#FFFFFF', width=2)),
                        hovertemplate="<b>%{label}</b><br>Amount: £%{value:,.2f}<br>Share: %{percent}<extra></extra>"
                    )])
                    fig_donut.update_layout(
                        title_text="<b>Category Share of Total Spending</b>", 
                        title_x=0.5, 
                        title_font=dict(size=18, color="#111827", family="Inter"), 
                        height=500, 
                        showlegend=True, 
                        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02),
                        paper_bgcolor='rgba(0,0,0,0)', 
                        plot_bgcolor='rgba(0,0,0,0)',
                        uniformtext=dict(minsize=10, mode='hide')
                    )
                    st.plotly_chart(fig_donut, use_container_width=True)
    
    # Spending Categories: Major Spending Areas (Top 6) + Other Spending Areas
    if not summary_df.empty:
        st.write("---")
        sections = build_dashboard_sections(cat_df, summary_df)
        is_valid, integrity_issues = validate_categorisation(cat_df, sections)
        if not is_valid and IS_LOCAL_DEV:
            for issue in integrity_issues:
                st.warning(f"⚠️ Integrity Notice: {issue}")

        main_6_df = sections["major_spending"]
        other_cats_df = sections["other_spending"]

        if not main_6_df.empty:
            st.markdown("<h3 style='color: #111827; font-weight: 700;'>🏆 Major Spending Areas</h3>", unsafe_allow_html=True)
            chunks_main = [main_6_df.iloc[i:i + 2] for i in range(0, len(main_6_df), 2)]
            for chunk in chunks_main:
                draw_horizontal_grid(chunk, st.session_state.categorized_df)

        if not other_cats_df.empty:
            st.write("<br>", unsafe_allow_html=True)
            st.markdown(f"<h4 style='color: #374151; font-weight: 600;'>📂 Other Spending Areas ({len(other_cats_df)} More)</h4>", unsafe_allow_html=True)
            chunks_other = [other_cats_df.iloc[i:i + 2] for i in range(0, len(other_cats_df), 2)]
            for chunk in chunks_other:
                draw_horizontal_grid(chunk, st.session_state.categorized_df)

    # Inflows & Income Breakdown (Grouped by Category in symmetric 2-column grid)
    # Strictly pure inflows (salaries, client revenue, refunds, benefits, interest) not already rendered above
    pure_inflow_summary = sections["pure_inflows"] if "sections" in locals() and not sections["pure_inflows"].empty else pd.DataFrame()
    if not pure_inflow_summary.empty:
        st.write("---")
        st.markdown("<h3 style='color: #111827; font-weight: 700;'>💰 Verified Inflows, Salaries & Deposits</h3>", unsafe_allow_html=True)
        tot_pure_in = pure_inflow_summary['Total_Inflow'].sum()
        tot_pure_tx = pure_inflow_summary['Tx_Count'].sum()
        st.caption(f"Total Credited: £{tot_pure_in:,.2f} across {int(tot_pure_tx)} inflow transactions.")

        inflow_chunks = [pure_inflow_summary.iloc[i:i + 2] for i in range(0, len(pure_inflow_summary), 2)]
        for chunk in inflow_chunks:
            draw_inflows_grid(chunk, cat_df)

    # Instant DuckDB Transaction Explorer & Search Bar (Backend Retrieval)
    st.write("---")
    with st.expander("🔍 Search & Filter Transactions (DuckDB Instant Engine)", expanded=False):
        c_search, c_cat, c_dir = st.columns([2, 1, 1])
        with c_search:
            search_kw = st.text_input("Quick Keyword Search (Merchant, item, tag, note):", placeholder="e.g. TfL, Tesco, Amazon, Uber, salary, refund, rent...")
        with c_cat:
            cat_list = ["All"] + sorted([c for c in cat_df['Category'].dropna().unique() if c])
            selected_cat = st.selectbox("Filter Category:", cat_list)
        with c_dir:
            selected_dir = st.selectbox("Flow Direction:", ["All", "Out", "In"], format_func=lambda x: "All (In & Out)" if x == "All" else ("Out (Expenses Only)" if x == "Out" else "In (Income / Deposits)"))
            
        matched_txns, matched_total = search_vault(
            cat_df,
            query_str=search_kw,
            category=selected_cat,
            direction=selected_dir if selected_dir != "All" else None
        )
        st.markdown(f"**Found {len(matched_txns)} transaction(s) totaling £{matched_total:,.2f}**")
        if not matched_txns.empty:
            view_cols = [c for c in ['Date', 'Bank', 'Clean_Description', 'Category', 'Direction', 'Amount'] if c in matched_txns.columns]
            rename_txns = {'Clean_Description': 'Merchant / Source'}
            st.dataframe(
                matched_txns[view_cols].rename(columns=rename_txns),
                hide_index=True,
                column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")},
                use_container_width=True
            )

# ==========================================
# PAGE: AI CHAT ASSISTANT
# ==========================================
elif page_selection == "💬 AI Chat Assistant":
    c_head1, c_head2 = st.columns([3, 2])
    with c_head1:
        st.markdown("<h1 style='color: #111827; font-weight: 800;'>💬 Ask Your Data</h1>", unsafe_allow_html=True)
        st.caption("Powered by DuckDB SQL Engine — Every calculation verified against the local database with 100% precision.")
    with c_head2:
        if st.session_state.chat_history:
            col_c_dl, col_c_clr = st.columns(2)
            with col_c_dl:
                chat_pdf = generate_chat_pdf(st.session_state.chat_history)
                st.download_button(
                    "📄 Export PDF",
                    data=chat_pdf,
                    file_name="pulse_chat_transcript.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            with col_c_clr:
                if st.button("🗑️ Clear Chat", use_container_width=True, key="clear_chat_btn"):
                    st.session_state.chat_history = []
                    st.rerun()

    st.write("---")

    if st.session_state.auth_role is None and not IS_LOCAL_DEV:
        if "base_chats_used" not in st.session_state:
            st.session_state.base_chats_used = 0
        st.session_state.chat_allowance = max(0, 3 - st.session_state.base_chats_used)

    if st.session_state.auth_role == "master":
        st.info("🔓 **Master Access Active:** You have unlimited chats available.")
    elif st.session_state.auth_role == "recruiter":
        st.info(f"🔓 **Code Access Active:** You have {st.session_state.chat_allowance} / 10 chats remaining.")
    elif IS_LOCAL_DEV and st.session_state.auth_role is None:
        st.info(f"ℹ️ **Local Dev Mode:** {st.session_state.chat_allowance} / 3 chats remaining.")
    else:
        if st.session_state.chat_allowance > 0:
            st.info(f"ℹ️ **Base Demo:** You have {st.session_state.chat_allowance} / 3 free chats available. Enter a passcode in the sidebar for more.")
        else:
            st.error("🔒 **Chat Locked.** You've used your 3 free chats. Please enter a Recruiter or Master passcode in the sidebar.")

    # Suggestion starter pills when conversation is fresh
    if not st.session_state.chat_history:
        st.markdown("""
        <div style="background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 12px; padding: 20px; text-align: center; margin: 15px 0 25px 0;">
            <h4 style="color: #1E293B; margin-top: 0; margin-bottom: 6px;">⚡ Multi-Hop Financial Intelligence</h4>
            <p style="color: #64748B; font-size: 13px; margin-bottom: 0;">Ask anything across your statements. DuckDB translates your inquiry into exact SQL calculations and retrieves matching records instantly.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("**💡 Quick Suggestions (Click to query):**")
        p1, p2, p3, p4 = st.columns(4)
        quick_questions = [
            ("🚆 Weekly Travel Avg", "On average how much did I spend per week on travel and commute?", p1),
            ("💰 Income & Inflows", "What were my total income, salary, and inflow deposits across all statements?", p2),
            ("🍔 Dining & Delivery", "How much did I spend on dining out and food delivery (Uber Eats, Deliveroo)?", p3),
            ("🏆 Top 5 Expenses", "What were my 5 highest single expenses across all statements?", p4)
        ]
        for label, q_text, col in quick_questions:
            with col:
                if st.button(label, use_container_width=True, key=f"quick_{label}"):
                    st.session_state.chat_history.append({"role": "user", "type": "user", "content": q_text})
                    st.rerun()

    # Render history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            if message["type"] == "user":
                st.markdown(message["content"])
            elif message["type"] == "assistant":
                st.markdown(message["text"])
                if message.get("df") is not None and not message["df"].empty:
                    df_to_show = message["df"].copy()
                    clean_cols = [c for c in ['Date', 'Bank', 'Clean_Description', 'Category', 'Direction', 'Amount'] if c in df_to_show.columns]
                    if clean_cols:
                        df_to_show = df_to_show[clean_cols].rename(columns={'Clean_Description': 'Merchant / Source'})
                    st.markdown(f"<div style='font-size: 13px; font-weight: 600; color: #94A3B8; margin-top: 14px; margin-bottom: 6px;'>📋 Matching Transactions ({len(df_to_show)})</div>", unsafe_allow_html=True)
                    st.dataframe(
                        df_to_show,
                        hide_index=True,
                        use_container_width=True,
                        column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")}
                    )
                if message.get("sql"):
                    with st.expander("🛠️ View SQL details", expanded=False):
                        st.code(message["sql"], language="sql")
            elif message["type"] == "error":
                st.error(message["content"])

    # Sticky Footer Conversation Input
    if st.session_state.auth_role != "master" and st.session_state.chat_allowance <= 0:
        st.chat_input("Chat is locked. Enter an access code to continue.", disabled=True)
    elif user_query := st.chat_input("E.g., 'How much did I spend on TFL?' or 'What was my highest expense?'"):
        st.session_state.chat_history.append({"role": "user", "type": "user", "content": user_query})
        st.rerun()

    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        user_query = st.session_state.chat_history[-1]["content"]
        
        if st.session_state.chat_allowance <= 0 and st.session_state.auth_role != "master":
            st.session_state.chat_history.append({"role": "assistant", "type": "error", "content": "🛑 Tokens Depleted. Enter a passcode in the sidebar."})
            st.rerun()
        else:
            with st.spinner("Analyzing with DuckDB SQL engine..."):
                if st.session_state.auth_role != "master":
                    st.session_state.chat_allowance -= 1 
                    if st.session_state.auth_role is None:
                        st.session_state.base_chats_used = st.session_state.get("base_chats_used", 0) + 1
                
                try:
                    engine_choice = st.session_state.get("ai_choice", available_engines[0])
                    res = ask_financial_data(
                        user_query=user_query,
                        df=st.session_state.categorized_df,
                        preferred_engine=engine_choice,
                        chat_history=st.session_state.chat_history,
                        custom_keys=st.session_state.get("byok_keys")
                    )
                    
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "type": "assistant",
                        "text": res["text"],
                        "df": res.get("df"),
                        "sql": res.get("sql")
                    })
                    st.rerun()
                except Exception as e:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "type": "error",
                        "content": f"I struggled to query that. Try rephrasing your question. ({e})"
                    })
                    st.rerun()