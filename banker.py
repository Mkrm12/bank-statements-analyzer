import os
import pandas as pd
import json
import duckdb
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

load_dotenv()

def run_ai_audit(df, ai_choice):
    cache_file = "memory.json"
    
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            memory_cache = json.load(f)
    else:
        memory_cache = {}

    unique_descriptions = df['Description'].dropna().unique().tolist()
    new_shops = [shop for shop in unique_descriptions if shop not in memory_cache]
    
    MAX_SHOPS_PER_BATCH = 40
    if len(new_shops) > MAX_SHOPS_PER_BATCH:
        new_shops = new_shops[:MAX_SHOPS_PER_BATCH]
        
    existing_categories = list(set([data.get('category') for data in memory_cache.values() if isinstance(data, dict)]))

    if ai_choice == "Option 1: Gemini Flash 2.5":
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    else:
        primary_llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("GITHUB_TOKEN"), base_url="https://models.github.ai/inference", temperature=0)
        fallback_llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("GITHUB_TOKEN"), base_url="https://models.github.ai/inference", temperature=0)
        llm = primary_llm.with_fallbacks([fallback_llm])

    # ==========================================
    # PASS 1: INITIAL CATEGORIZATION
    # ==========================================
    if new_shops:
        prompt = f"""
        You are a ruthless financial auditor. Review these RAW bank transaction descriptions:
        {new_shops}

        EXISTING categories: {existing_categories}

        CRITICAL INSTRUCTIONS:
        1. GRANULAR UMBRELLAS: Group similar stores into clean, distinct categories (e.g. 'Groceries', 'Takeaway & Dining', 'Subscriptions', 'Transport'). Aim for high granularity where logical, breaking out distinct spending habits.
        2. NO BRAND NAMES IN CATEGORIES: You are FORBIDDEN from outputting categories like "Dining - Spice Hut". The category MUST be the generic umbrella term.
        3. NO ESCAPE HATCHES: Assign a highly specific category to EVERY item. BANNED WORDS: 'Overhead', 'General', 'Miscellaneous', 'Other', 'Unknown', 'Uncategorized'.
        4. CLEAN NAME: Remove dates, store numbers, and 'VIS'. Keep the brand name clean.

        Output ONLY a valid JSON dictionary mapping the EXACT raw name to your determined category and clean_name.
        """
        try:
            response = llm.invoke(prompt)
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                memory_cache.update(json.loads(json_match.group(0)))
                with open(cache_file, "w") as f:
                    json.dump(memory_cache, f, indent=4)
        except Exception as e:
            print(f"Pass 1 Error: {e}")

    # ==========================================
    # PASS 2: THE ERROR SWEEP
    # ==========================================
    df['Category'] = df['Description'].map(lambda x: memory_cache.get(x, {}).get('category', 'AI MAPPING ERROR') if isinstance(memory_cache.get(x), dict) else 'AI MAPPING ERROR')
    
    unmapped_shops = df[df['Category'] == 'AI MAPPING ERROR']['Description'].unique().tolist()
    
    if unmapped_shops:
        sweep_prompt = f"""
        You previously failed to map these items: {unmapped_shops}
        Map them using broad umbrella categories (e.g. 'Groceries', 'Takeaway'). NO BRAND NAMES IN THE CATEGORY.
        Return ONLY a JSON dictionary mapping the raw name to the category and clean_name.
        """
        try:
            sweep_response = llm.invoke(sweep_prompt)
            json_match = re.search(r'\{.*\}', sweep_response.content, re.DOTALL)
            if json_match:
                memory_cache.update(json.loads(json_match.group(0)))
                with open(cache_file, "w") as f:
                    json.dump(memory_cache, f, indent=4)
        except Exception as e:
            print(f"Pass 2 Error: {e}")

    # ==========================================
    # PASS 3: FINAL GRAPH DATA & THE ROAST
    # ==========================================
    
    # Final mappings applied
    df['Category'] = df['Description'].map(lambda x: memory_cache.get(x, {}).get('category', 'AI MAPPING ERROR') if isinstance(memory_cache.get(x), dict) else 'AI MAPPING ERROR')
    df['Clean_Description'] = df['Description'].map(lambda x: memory_cache.get(x, {}).get('clean_name', x) if isinstance(memory_cache.get(x), dict) else x)
    
    # Explicitly cast to DOUBLE inside the query so DuckDB doesn't treat it as a Boolean/String
    final_query = """
        SELECT 
            Category, 
            SUM(CAST(Amount AS DOUBLE)) as Total_Spent 
        FROM df 
        GROUP BY Category 
        ORDER BY Total_Spent DESC
    """

    try:
        final_summary_df = duckdb.query(final_query).df()
    except Exception as e:
        # Fallback if the cast fails due to weird characters
        print(f"DuckDB Query Error: {e}")
        final_summary_df = df.groupby('Category')['Amount'].sum().reset_index().rename(columns={'Amount': 'Total_Spent'})

    final_summary_df['Total_Spent'] = pd.to_numeric(final_summary_df['Total_Spent'], errors='coerce').fillna(0.0)

    # NOW we roast the perfectly clean data
    spending_summary = final_summary_df.to_string(index=False)
    roast_prompt = f"""
    You are a brutally honest, sarcastic comedian and financial advisor.
    Here is the user's PERFECTLY CLEANED spending summary:
    {spending_summary}
    
    Roast their financial habits in exactly ONE brutal, short sarcastic punchline sentence. No intro, no emojis.
    """
    try:
        roast_response_text = llm.invoke(roast_prompt).content
    except:
        roast_response_text = "You broke the AI with your terrible spending habits."

    return df, final_summary_df, roast_response_text