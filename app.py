import streamlit as st
import pandas as pd
import os
import json
import plotly.express as px
import duckdb
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI

from extractor import process_pdf
from banker import run_ai_audit

# --- PAGE CONFIG & AGGRESSIVE PREMIUM CSS ---
st.set_page_config(page_title="Pulse AI", page_icon="🏦", layout="wide")

st.markdown(
    """
    <style>
    /* Import Inter Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }

    /* Main App Background (Light Grey) */
    .stApp {
        background-color: #F9FAFB !important;
    }

    /* HIDE THE DEPLOY / MENU BUT KEEP THE SIDEBAR ARROW */
    .stDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    header { background-color: transparent !important; }
    

    /* Midnight SaaS Sidebar (Width restrictions removed for smooth collapsing) */
    [data-testid="stSidebar"] {
        background-color: #111827 !important;
        border-right: none !important;
    }
    [data-testid="stSidebar"] * {
        color: #E5E7EB !important; 
    }
    
    /* Active Sidebar Buttons */
    div[role="radiogroup"] label {
        background-color: transparent !important;
        padding: 12px 15px !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }
    div[role="radiogroup"] label:hover {
        background-color: #1F2937 !important;
    }

    /* Floating Metric Cards */
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border-radius: 16px !important;
        padding: 20px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
        border: 1px solid #F3F4F6 !important;
    }
    [data-testid="stMetricValue"] {
        color: #4F46E5 !important; 
        font-weight: 700 !important;
        font-size: 2.2rem !important;
    }
    [data-testid="stMetricLabel"] {
        color: #6B7280 !important;
        font-weight: 600 !important;
    }

    /* Premium Category Expanders */
    [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border-radius: 12px !important;
        border: 1px solid #F3F4F6 !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02) !important;
        overflow: hidden !important;
    }
    div[data-testid="stExpander"] details summary {
        background-color: #FFFFFF !important;
        padding: 15px 15px !important;
        font-weight: 700 !important;
        color: #111827 !important;
        border-bottom: 1px solid #F3F4F6 !important;
    }

    /* BEAUTIFUL TABLES */
    [data-testid="stDataFrame"] {
        border-radius: 8px !important;
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    [data-testid="stDataFrame"] table {
        background-color: #FFFFFF !important;
    }
    [data-testid="stDataFrame"] th {
        background-color: #F3F4F6 !important;
        color: #374151 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #E5E7EB !important;
    }

    /* Gradient Primary Button */
    [data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #4F46E5 0%, #3B82F6 100%) !important;
        color: #FFFFFF !important;
        border-radius: 12px !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3) !important;
        transition: transform 0.1s ease !important;
    }
    [data-testid="baseButton-primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 12px rgba(59, 130, 246, 0.4) !important;
    }

    /* CHAT UI GLOW-UP */
    .stChatMessage {
        border-radius: 16px !important;
        padding: 20px !important;
        margin-bottom: 15px !important;
    }
    /* Chat Message content text color */
    .stChatMessage * {
        color: #1F2937 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- SESSION STATE ---
if "audit_complete" not in st.session_state:
    st.session_state.audit_complete = False
if "api_calls_used" not in st.session_state:
    st.session_state.api_calls_used = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

MAX_API_CALLS = 50 

st.sidebar.markdown("<h1 style='color: white; font-weight: 800; font-size: 2rem;'>🏦 Pulse AI</h1>", unsafe_allow_html=True)
if st.session_state.audit_complete:
    page_selection = st.sidebar.radio("Navigation", ["📊 Overview Dashboard", "💬 AI Chat Assistant"])
    st.sidebar.write("---")
    # Fixed Sidebar Text Color!
    st.sidebar.markdown(f"<div style='color: #9CA3AF; font-size: 14px; margin-top: 10px;'><b>API Requests Used:</b> {st.session_state.api_calls_used} / {MAX_API_CALLS}</div>", unsafe_allow_html=True)
else:
    page_selection = "Setup"
    st.sidebar.markdown("<div style='color: #9CA3AF; font-size: 14px;'>Upload statements to unlock navigation.</div>", unsafe_allow_html=True)

def draw_horizontal_grid(summary_chunk, master_df):
    cols = st.columns(len(summary_chunk))
    for col, (index, row) in zip(cols, summary_chunk.iterrows()):
        cat_name = row['Category']
        cat_total = row['Total_Spent']
        with col:
            with st.expander(f"{cat_name.upper()} | £{cat_total:,.2f}"):
                filtered_df = master_df[master_df['Category'] == cat_name]
                st.dataframe(
                    filtered_df[['Date', 'Bank', 'Clean_Description', 'Amount']],
                    hide_index=True,
                    column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")},
                    use_container_width=True
                )

# ==========================================
# PAGE: SETUP
# ==========================================
if page_selection == "Setup":
    st.markdown("<h1 style='color: #111827; font-weight: 800;'>Welcome to Pulse ⚡</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #4B5563; font-size: 1.1rem;'>Upload your bank statements (PDF) to generate your financial dashboard.</p>", unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Drop your HSBC or Santander PDFs here", accept_multiple_files=True, type=['pdf'])

    if uploaded_files:
        st.write("---")
        st.markdown("<h3 style='color: #111827;'>🕵️‍♂️ Extraction Log</h3>", unsafe_allow_html=True)
        all_dfs = []
        for file in uploaded_files:
            df, message = process_pdf(file, file.name)
            if df is not None:
                st.success(message)
                all_dfs.append(df)
            else:
                if "Error" in message or "INVALID" in message:
                    st.error(message)
                else:
                    st.warning(message)

        if all_dfs:
            st.write("---")
            master_df = pd.concat(all_dfs, ignore_index=True)
            
            master_df['Description'] = master_df['Description'].astype(str).str.replace(r'^[^\w]+', '', regex=True).str.strip()
            master_df['Date_Sorter'] = pd.to_datetime(master_df['Date'], format='mixed', errors='coerce')
            master_df = master_df.sort_values(by='Date_Sorter', ascending=True)
            master_df['Amount'] = master_df['Amount'].replace(',', '', regex=True)
            master_df['Amount'] = pd.to_numeric(master_df['Amount'], errors='coerce')
            
            st.dataframe(master_df[['Date', 'Bank', 'Description', 'Amount']], width="stretch", hide_index=True, column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")})
            st.write("---")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                run_btn = st.button("🧠 Run AI Categorization & Audit", use_container_width=True, type="primary")

            if run_btn:
                if st.session_state.api_calls_used >= MAX_API_CALLS - 1:
                    st.error(f"🛑 Session Limit Reached ({MAX_API_CALLS}/{MAX_API_CALLS}). Refresh to start a new session.")
                else:
                    with st.spinner("Gemini is analyzing your transactions..."):
                        st.session_state.api_calls_used += 2 
                        categorized_df, summary_df, roast = run_ai_audit(master_df)
                        st.session_state.categorized_df = categorized_df
                        st.session_state.summary_df = summary_df
                        st.session_state.roast = roast
                        st.session_state.audit_complete = True
                        st.rerun()

# ==========================================
# PAGE: OVERVIEW DASHBOARD
# ==========================================
elif page_selection == "📊 Overview Dashboard":
    st.markdown("<h1 style='color: #111827; font-weight: 800;'>📊 Global Overview</h1>", unsafe_allow_html=True)
    
    # Custom Gradient Roast Banner
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%); padding: 25px; border-radius: 16px; color: white; font-size: 1.1rem; font-weight: 600; text-align: center; box-shadow: 0 10px 25px rgba(255, 65, 108, 0.3); margin-bottom: 30px;">
        🔥 AI Verdict: {st.session_state.roast}
    </div>
    """, unsafe_allow_html=True)
    
    total_spend = st.session_state.summary_df['Total_Spent'].sum()
    top_cat_name = st.session_state.summary_df.iloc[0]['Category']
    top_cat_val = st.session_state.summary_df.iloc[0]['Total_Spent']
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Tracked Spend", f"£{total_spend:,.2f}")
    m2.metric("Highest Category", top_cat_name)
    m3.metric(f"{top_cat_name} Spend", f"£{top_cat_val:,.2f}")
    
    st.write("<br>", unsafe_allow_html=True)
    
    top_5_df = st.session_state.summary_df.head(5)
    st.markdown("<h3 style='color: #111827; font-weight: 700;'>🏆 Major Spendings (Top 5)</h3>", unsafe_allow_html=True)
    
    chunks_top = [top_5_df.iloc[i:i + 2] for i in range(0, len(top_5_df), 2)]
    for chunk in chunks_top:
        draw_horizontal_grid(chunk, st.session_state.categorized_df)
    
    st.write("<br>", unsafe_allow_html=True)
    fig1 = px.pie(top_5_df, values='Total_Spent', names='Category', hole=0.5)
    fig1.update_traces(
        textposition='outside', 
        texttemplate='<b>%{label}</b><br>£%{value:,.2f}', 
        insidetextfont=dict(size=14, color="#111827"),
        marker=dict(line=dict(color='#FFFFFF', width=2)), 
        pull=[0.02] * len(top_5_df)
    )
    fig1.update_layout(
        title_text="Top 5 Categories Breakdown", 
        title_x=0.5, 
        title_font=dict(size=22, color="#111827", family="Inter"), 
        height=500, 
        showlegend=True, 
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig1, use_container_width=True)
    
    st.write("---")
    rest_df = st.session_state.summary_df.iloc[5:]
    if not rest_df.empty:
        st.markdown("<h3 style='color: #111827; font-weight: 700;'>🛒 Other Spendings</h3>", unsafe_allow_html=True)
        chunks_rest = [rest_df.iloc[i:i + 2] for i in range(0, len(rest_df), 2)]
        for chunk in chunks_rest:
            draw_horizontal_grid(chunk, st.session_state.categorized_df)

# ==========================================
# PAGE: AI CHAT ASSISTANT
# ==========================================
elif page_selection == "💬 AI Chat Assistant":
    st.markdown("<h1 style='color: #111827; font-weight: 800;'>💬 Ask Your Data</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #4B5563; font-size: 1.1rem;'>Your AI Financial Analyst is ready. Ask about your spending, trends, or specific transactions.</p>", unsafe_allow_html=True)
    st.write("---")

    for message in st.session_state.chat_history:
        # Dynamically switch styles based on who is speaking
        bubble_bg = "#FFFFFF" if message["role"] == "assistant" else "#EEF2FF"
        bubble_border = "1px solid #E5E7EB" if message["role"] == "assistant" else "none"
        bubble_shadow = "0 4px 6px -1px rgba(0,0,0,0.05)" if message["role"] == "assistant" else "none"

        st.markdown(f"""
        <div style="background-color: {bubble_bg}; border: {bubble_border}; box-shadow: {bubble_shadow}; border-radius: 16px; padding: 20px; margin-bottom: 15px;">
        """, unsafe_allow_html=True)
        
        with st.chat_message(message["role"]):
            if message["type"] == "user":
                st.markdown(message["content"])
            elif message["type"] == "assistant":
                st.markdown(message["text"])
                if message.get("df") is not None and not message["df"].empty:
                    with st.expander("🔍 View Source Transactions"):
                        st.dataframe(message["df"], hide_index=True, use_container_width=True, column_config={"Amount": st.column_config.NumberColumn("Amount", format="£%.2f")})
            elif message["type"] == "error":
                st.error(message["content"])
                
        st.markdown("</div>", unsafe_allow_html=True)

    if user_query := st.chat_input("E.g., 'How much did I spend on papa;s?' or 'travel last month'"):
        
        st.session_state.chat_history.append({"role": "user", "type": "user", "content": user_query})
        st.rerun() # Force a fast visual update so the user query appears instantly

    # Run the AI logic if the last message is from the user
    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        user_query = st.session_state.chat_history[-1]["content"]
        
        if st.session_state.api_calls_used >= MAX_API_CALLS:
            err = f"🛑 Session Limit Reached ({MAX_API_CALLS}/{MAX_API_CALLS}). Start a new session to continue."
            st.session_state.chat_history.append({"role": "assistant", "type": "error", "content": err})
            st.rerun()
        else:
            with st.spinner("Scanning your transactions..."):
                st.session_state.api_calls_used += 1 
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
                
                search_df = st.session_state.categorized_df.copy()
                search_df['Row_ID'] = range(len(search_df))
                csv_data = search_df[['Row_ID', 'Date', 'Bank', 'Clean_Description', 'Category', 'Amount']].to_csv(index=False)
                
                today_date = datetime.now().strftime('%Y-%m-%d')
                past_questions = [msg["content"] for msg in st.session_state.chat_history if msg["type"] == "user"]
                recent_context = "\n".join(past_questions[-4:-1]) # Grab history excluding current

                prompt = f"""
                You are an elite Financial Analyst AI. 
                
                Here is the user's COMPLETE transaction history in CSV format:
                {csv_data}
                
                Today's Date: {today_date}
                Recent Chat Context: {recent_context}
                User Query: "{user_query}"

                INSTRUCTIONS:
                1. Read the CSV data directly to answer the user's query.
                2. BE EXTREMELY FORGIVING. If they ask for "papas", match it to "Papa's Chicken". If they ask for "travel", match it to "Transit" or "TFL". 
                3. Calculate the total spent based ONLY on the matching rows.
                4. Write a friendly, conversational response detailing what you found. Format money with £.
                5. Look at the 'Row_ID' column in the CSV. You MUST provide an array of the exact Row_IDs that match their query so we can display the receipts.

                Return ONLY a valid JSON object in this exact format:
                {{
                    "text": "Your conversational response here.",
                    "matched_ids": [1, 5, 12]
                }}
                """
                
                try:
                    raw_response = llm.invoke(prompt).content
                    clean_json = raw_response.replace("```json", "").replace("```", "").strip()
                    response_data = json.loads(clean_json)
                    
                    text_response = response_data.get("text", "Here is what I found:")
                    matched_ids = response_data.get("matched_ids", [])
                    
                    if matched_ids:
                        result_df = search_df[search_df['Row_ID'].isin(matched_ids)].drop(columns=['Row_ID'])
                    else:
                        result_df = pd.DataFrame()
                    
                    st.session_state.chat_history.append({
                        "role": "assistant", 
                        "type": "assistant", 
                        "text": text_response,
                        "df": result_df
                    })
                    st.rerun()
                    
                except Exception as e:
                    err_msg = f"I struggled to process that. Could you try rephrasing? (Error: {str(e)})"
                    st.session_state.chat_history.append({"role": "assistant", "type": "error", "content": err_msg})
                    st.rerun()