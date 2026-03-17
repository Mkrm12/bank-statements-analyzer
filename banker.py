import os
import pandas as pd
import json
import duckdb
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

def run_ai_audit(df):
    cache_file = "memory.json"
    
    # 1. LOAD CACHE
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            memory_cache = json.load(f)
    else:
        memory_cache = {}

    unique_descriptions = df['Description'].dropna().unique().tolist()
    new_shops = [shop for shop in unique_descriptions if shop not in memory_cache]
    existing_categories = list(set(memory_cache.values()))

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)

    # 2. AI CATEGORIZATION (Context-Aware)
    if new_shops:
        prompt = f"""
        You are an elite financial auditor. You need to categorize these NEW bank transactions:
        {new_shops}

        Here are the EXISTING categories you have already established for this user:
        {existing_categories}

        CRITICAL INSTRUCTIONS:
        1. Prioritize sorting these new transactions into the EXISTING categories listed above.
        2. ONLY invent a new category if the transaction is a completely new type of spending that absolutely does not fit anywhere else.
        3. Do not create hyper-specific categories for 1 or 2 items. If it is ambiguous, put it in a broad existing category.

        Return ONLY a valid JSON dictionary where the key is the transaction name, and the value is the category string. Do not add any conversational text.
        """
        
        response = llm.invoke(prompt)
        raw_response = response.content
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        
        if json_match:
            clean_json_string = json_match.group(0)
            try:
                new_categories = json.loads(clean_json_string)
                memory_cache.update(new_categories)
                with open(cache_file, "w") as f:
                    json.dump(memory_cache, f, indent=4)
            except json.JSONDecodeError:
                pass # Silently fail for UI

    # 3. MAP CATEGORIES
    df['Category'] = df['Description'].map(memory_cache).fillna('Uncategorized')

    # 4. DUCKDB MATH
    query = """
        SELECT Category, SUM(Amount) as Total_Spent
        FROM df
        GROUP BY Category
        ORDER BY Total_Spent DESC
    """
    summary_df = duckdb.query(query).df()

    # 5. THE AI ROAST
    spending_summary = summary_df.to_string(index=False)
    roast_prompt = f"""
    You are a brutally honest, sarcastic financial advisor. 
    Here is my exact spending breakdown:

    {spending_summary}

    Roast my financial habits in exactly 3 sentences. Highlight the most ridiculous categories. Be harsh but factual. No emojis.
    """
    roast_response = llm.invoke(roast_prompt)
    roast_text = roast_response.content

    return df, summary_df, roast_text
