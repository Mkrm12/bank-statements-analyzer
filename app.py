import streamlit as st
import pandas as pd
import os

from extractor import process_pdf
from banker import run_ai_audit

st.set_page_config(page_title="AI Financial Auditor", page_icon="🏦", layout="centered")

st.title("🏦 AI Financial Auditor")
st.markdown("Upload your bank statements (PDF) and watch the engine extract your transactions instantly.")

uploaded_files = st.file_uploader("Drop your HSBC or Santander PDFs here", accept_multiple_files=True, type=['pdf'])

if uploaded_files:
    st.write("---")
    st.subheader("🕵️‍♂️ Extraction Log")
    
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
        st.subheader("📊 Combined Transactions")
        master_df = pd.concat(all_dfs, ignore_index=True)
        
        # Date & Money standardization
        master_df['Date_Sorter'] = pd.to_datetime(master_df['Date'], format='mixed', errors='coerce')
        master_df = master_df.sort_values(by='Date_Sorter', ascending=True).drop(columns=['Date_Sorter'])
        master_df['Amount'] = master_df['Amount'].replace(',', '', regex=True)
        master_df['Amount'] = pd.to_numeric(master_df['Amount'], errors='coerce')
        
        st.dataframe(master_df, width="stretch")
        st.write("---")
        
        # THE MAGIC BUTTON (Now with a unique key to prevent errors!)
        if st.button("🧠 Run AI Categorization & Audit", type="primary", key="master_ai_btn"):
            
            with st.spinner("Gemini is analyzing your spending habits..."):
                categorized_df, summary_df, roast = run_ai_audit(master_df)
                
                # 1. Roast
                st.subheader("🔥 Your Financial Roast")
                st.error(roast) 
                st.write("---")
                
                # 2. Chart
                st.subheader("📈 Spending by Category")
                st.bar_chart(data=summary_df, x="Category", y="Total_Spent")
                
                # 3. Dropdowns
                st.subheader("📂 Categorized Breakdown")
                for index, row in summary_df.iterrows():
                    cat_name = row['Category']
                    cat_total = row['Total_Spent']
                    
                    with st.expander(f"{cat_name.upper()} - Total: £{cat_total:.2f}"):
                        filtered_df = categorized_df[categorized_df['Category'] == cat_name]
                        st.dataframe(filtered_df[['Date', 'Description', 'Amount']], width="stretch")
                        
                st.success("✅ Audit Complete!")
