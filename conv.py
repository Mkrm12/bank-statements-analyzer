import os
import glob
import sys
import pdfplumber
import pandas as pd
import re

# 1. SETUP & AUTO-FIND PDFs
os.makedirs("data", exist_ok=True)
os.makedirs("pdf", exist_ok=True) 

pdf_files = glob.glob("pdf/*.pdf")

if not pdf_files:
    print("📁 The 'pdf' folder is empty! Drop some statements in there and run again.")
    sys.exit() 

csv_file = "data/bank_statement_1.csv" 
parsed_transactions = []

# Regex patterns
date_pattern = r'^(\d{2}\s[A-Z][a-z]{2}(?:\s\d{2})?)'
amount_pattern = r'\s([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?$'

print(f"🚀 Found {len(pdf_files)} PDFs. Starting extraction...\n")

for pdf_file in pdf_files:
    print(f"🕵️ Extracting: {os.path.basename(pdf_file)}...")
    
    current_date = ""
    text_buffer = ""

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            raw_text = page.extract_text()
            if not raw_text:
                continue
                
            for line in raw_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # --- THE 120 CHAR LIMIT FILTER ---
                if len(line) > 120:
                    continue
                    
                # Basic Junk Headers
                junk_headers = ["BALANCE", "BROUGHT FORWARD", "PAGE", "ACCOUNT DETAILS", "PAYMENT TYPE"]
                if any(keyword in line.upper() for keyword in junk_headers):
                    continue

                date_match = re.search(date_pattern, line)
                if date_match:
                    current_date = date_match.group(1) 
                    line = line[date_match.end():].strip() 
                    text_buffer = "" 

                amount_match = re.search(amount_pattern, line)
                
                if amount_match:
                    actual_amount = amount_match.group(1)
                    desc_part = line[:amount_match.start()].strip()
                    
                    # This pattern dynamically hunts down the moving dates and page numbers
                    junk_pattern = r'126 High Road.*?Sheet Number(?:\s*[a-zA-Z\s]+)?(?:\s*\d{2}-\d{2}-\d{2})?(?:\s*\d{8})?(?:\s*\d+)?'
                    clean_buffer = re.sub(junk_pattern, '', text_buffer, flags=re.IGNORECASE | re.DOTALL).strip()
                    
                    final_description = (clean_buffer + " " + desc_part).strip()
                    # -----------------------------
                    
                    if current_date:
                        parsed_transactions.append({
                            "Date": current_date,
                            "Description": final_description,
                            "Amount": actual_amount
                        })
                    
                    text_buffer = "" 
                else:
                    if current_date: 
                        text_buffer += " " + line

# 3. COMBINE, SORT, AND OVERWRITE CSV
if parsed_transactions:
    print("\n⚙️ Combining and sorting all transactions chronologically...")
    df = pd.DataFrame(parsed_transactions)
    df['Date_Sorter'] = pd.to_datetime(df['Date'], format='%d %b %y', errors='coerce')
    df = df.dropna(subset=['Date_Sorter'])
    df = df.sort_values(by='Date_Sorter', ascending=True)
    df = df.drop(columns=['Date_Sorter'])
    
    df.to_csv(csv_file, index=False, header=False)

    print(f"🔥 Total combined transactions: {len(df)}")
    print("✅ Absolute success! Clean data saved to", csv_file)
else:
    print("\n❌ No transactions found.")