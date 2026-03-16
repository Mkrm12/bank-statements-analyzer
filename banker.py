import os
import pandas as pd
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# 1. Setup
load_dotenv()
csv_file = "data/bank_statement_1.csv"
print(f"📊 Loading data from {csv_file}...\n")

df = pd.read_csv(csv_file, header=None, names=["Date", "Description", "Amount"])
df['Amount'] = df['Amount'].replace(',', '', regex=True)
df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')

unique_descriptions = df['Description'].dropna().unique().tolist()

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# 2. THE DYNAMIC PROMPT
print("🧠 Asking Gemini to INVENT categories based on your spending...\n")
prompt = f"""
You are a brilliant financial analyst. Look at this list of unique bank transactions:
{unique_descriptions}

I want you to analyze these and INVENT 5 to 8 major spending categories that best describe this specific person's habits (e.g., if you see lots of Temu, make a "Fast Fashion" category. If you see Steam, make a "Gaming" category). 

Return ONLY a valid JSON dictionary where the key is the transaction name, and the value is the category you assigned it to. Every transaction must be assigned a category.
"""

response = llm.invoke(prompt)

# Clean and load the JSON
clean_json_string = response.content.replace("```json", "").replace("```", "").strip()
category_dict = json.loads(clean_json_string)

print("⚙️ Processing dynamic math locally...\n")

# 3. THE PANDAS MAGIC (Map and GroupBy)
# This maps the AI's categories directly onto our main DataFrame
df['Category'] = df['Description'].map(category_dict).fillna('Uncategorized')

# This automatically groups everything by the AI's categories and adds up the money
summary_df = df.groupby('Category')['Amount'].sum().reset_index()
summary_df = summary_df.sort_values(by='Amount', ascending=False) # Sort by most expensive

# 4. PRINT THE DYNAMIC REPORT
print("📈 YOUR PERSONALIZED FINANCIAL AUDIT:")
print("=" * 50)
for index, row in summary_df.iterrows():
    cat = row['Category']
    total = row['Amount']
    print(f"\n📂 CATEGORY: {cat.upper()} | Total Spent: £{total:.2f}")
    print("-" * 50)
    
    # Show the exact transactions inside this category
    cat_transactions = df[df['Category'] == cat]
    print(cat_transactions[['Date', 'Description', 'Amount']].to_string(index=False))

print("\n✅ Audit Complete.")