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
    
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            memory_cache = json.load(f)
    else:
        memory_cache = {}

    unique_descriptions = df['Description'].dropna().unique().tolist()
    new_shops = [shop for shop in unique_descriptions if shop not in memory_cache]
    
    MAX_SHOPS_PER_BATCH = 50
    if len(new_shops) > MAX_SHOPS_PER_BATCH:
        new_shops = new_shops[:MAX_SHOPS_PER_BATCH]
        
    existing_categories = list(set([data.get('category') for data in memory_cache.values() if isinstance(data, dict)]))

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

    # --- PASS 1: INITIAL CATEGORIZATION ---
    if new_shops:
        prompt = f"""
        You are an elite financial data scientist. Analyze these NEW bank transactions:
        {new_shops}

        EXISTING categories: {existing_categories}

        CRITICAL INSTRUCTIONS:
        1. STRICTLY NO "UNCATEGORIZED": You MUST assign a valid category. Make your best logical deduction.
        2. LETTER-LEVEL DEDUCTION: Decode acronyms, typos, and local UK shops. 
           - 'GDK' = German Doner Kebab -> 'Takeaway'
           - 'papas' or 'papa;s' = Papa's -> 'Takeaway'
           - 'BP' = Bank Payment -> 'Transfers'
           - 'AMZN' = Amazon -> 'Shopping'
        3. CATEGORY LIMITS: Try to group into broad, existing categories first. If absolutely necessary, create a new one (Max 30 global categories total like 'Groceries', 'Entertainment', 'Bills').
        4. "clean_name": Strip all junk (dates, 'VIS', 'CARDPAYMENT'). Return the pure brand name.

        Return ONLY a valid JSON dictionary mapping the exact raw name to the category and clean_name.
        Example Format:
        {{
            "CARDPAYMENTTOTFLTRAVELCHON14-09-2024": {{"category": "Transit", "clean_name": "TFL"}},
            "))) SPICE HUT LONDON": {{"category": "Takeaway", "clean_name": "Spice Hut"}}
        }}
        """


        response = llm.invoke(prompt)
        json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
        
        if json_match:
            try:
                new_categories = json.loads(json_match.group(0))
                memory_cache.update(new_categories)
                with open(cache_file, "w") as f:
                    json.dump(memory_cache, f, indent=4)
            except json.JSONDecodeError:
                pass 

    # --- PASS 2: THE "UNCATEGORIZED" SWEEP ---
    # Find anything that fell through the cracks and force the AI to try again
    uncategorized_shops = [shop for shop, data in memory_cache.items() if isinstance(data, dict) and data.get('category') in ['Uncategorized', '', None]]
    
    if uncategorized_shops:
        updated_categories = list(set([data.get('category') for data in memory_cache.values() if isinstance(data, dict) and data.get('category') not in ['Uncategorized', '', None]]))
        
        sweep_prompt = f"""
        You are a financial auditor. These ambiguous bank transactions failed to categorize:
        {uncategorized_shops}

        Confirmed categories we are already using: {updated_categories}

        CRITICAL INSTRUCTIONS:
        1. Forcefully map these ambiguous shops into one of the EXISTING categories. Use deduction.
        2. "clean_name": Clean up the garbage characters into a readable brand name.
        
        Return ONLY a valid JSON dictionary mapping the raw name to the new category and clean_name.
        """
        try:
            sweep_response = llm.invoke(sweep_prompt)
            sweep_match = re.search(r'\{.*\}', sweep_response.content, re.DOTALL)
            if sweep_match:
                swept_categories = json.loads(sweep_match.group(0))
                memory_cache.update(swept_categories)
                with open(cache_file, "w") as f:
                    json.dump(memory_cache, f, indent=4)
        except Exception:
            pass

    # Map the final dict back to the DataFrame
    df['Category'] = df['Description'].map(lambda x: memory_cache.get(x, {}).get('category', 'Uncategorized') if isinstance(memory_cache.get(x), dict) else 'Uncategorized')
    df['Clean_Description'] = df['Description'].map(lambda x: memory_cache.get(x, {}).get('clean_name', x) if isinstance(memory_cache.get(x), dict) else x)

    query = """
        SELECT Category, SUM(Amount) as Total_Spent
        FROM df
        GROUP BY Category
        ORDER BY Total_Spent DESC
    """
    summary_df = duckdb.query(query).df()

    spending_summary = summary_df.to_string(index=False)
    roast_prompt = f"""
    You are a brutally honest, sarcastic comedian and financial advisor. 
    Here is my exact spending breakdown:

    {spending_summary}

    Roast my financial habits in exactly ONE brutal, sarcastic punchline sentence. No intro, no outro, just the kill shot. Be harsh but factual. No emojis.
    """
    roast_response = llm.invoke(roast_prompt)

    return df, summary_df, roast_response.content