import pdfplumber
import pandas as pd
import re
import datetime

# --- 1. HSBC PARSER ---
def parse_hsbc(pdf):
    parsed_transactions = []
    date_pattern = r'^(\d{2}\s[A-Z][a-z]{2}(?:\s\d{2})?)'
    amount_pattern = r'\s([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?$'
    
    current_date = ""
    text_buffer = ""

    for page in pdf.pages:
        raw_text = page.extract_text()
        if not raw_text: continue
            
        for line in raw_text.split('\n'):
            line = line.strip()
            if not line or len(line) > 120: continue
                
            junk_headers = ["BALANCE", "BROUGHT FORWARD", "PAGE", "ACCOUNT DETAILS", "PAYMENT TYPE"]
            if any(keyword in line.upper() for keyword in junk_headers): continue

            date_match = re.search(date_pattern, line)
            if date_match:
                current_date = date_match.group(1) 
                line = line[date_match.end():].strip() 
                text_buffer = "" 

            amount_match = re.search(amount_pattern, line)
            if amount_match:
                actual_amount = amount_match.group(1)
                desc_part = line[:amount_match.start()].strip()
                
                junk_pattern = r'126 High Road.*?Sheet Number(?:\s*[a-zA-Z\s]+)?(?:\s*\d{2}-\d{2}-\d{2})?(?:\s*\d{8})?(?:\s*\d+)?'
                clean_buffer = re.sub(junk_pattern, '', text_buffer, flags=re.IGNORECASE | re.DOTALL).strip()
                
                final_description = (clean_buffer + " " + desc_part).strip()
                
                if current_date:
                    parsed_transactions.append({
                        "Date": current_date,
                        "Description": final_description,
                        "Amount": actual_amount,
                        "Bank": "HSBC"
                    })
                text_buffer = "" 
            else:
                if current_date: 
                    text_buffer += " " + line
                    
    return parsed_transactions

# --- 2. SANTANDER PARSER ---
def parse_santander(pdf):
    parsed_transactions = []
    universal_pattern = re.compile(r'^(\d{1,2}(?:st|nd|rd|th)?[\s\-]?[A-Za-z]{3}(?:[\s\-]?\d{2,4})?|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})')
    current_year = str(datetime.datetime.now().year)
    
    for page in pdf.pages:
        raw_text = page.extract_text(layout=True) 
        if not raw_text: continue
            
        for line in raw_text.split('\n'):
            line = line.strip()
            if not line: continue
            
            year_match = re.search(r'\b(202\d)\b', line)
            if year_match:
                current_year = year_match.group(1)
            
            match = universal_pattern.search(line)
            if match:
                raw_date = match.group(1).strip()
                desc_val = match.group(2).strip()
                amount_val = match.group(3).strip()
                
                if "balance" in desc_val.lower() or "brought forward" in desc_val.lower(): continue
                
                desc_val = re.sub(r'\s+', ' ', desc_val)
                clean_date = re.sub(r'(st|nd|rd|th)', '', raw_date, flags=re.IGNORECASE)
                clean_date = re.sub(r'(\d+)([A-Za-z]+)', r'\1 \2', clean_date).strip()
                
                if not re.search(r'\d{4}', clean_date):
                    clean_date = f"{clean_date} {current_year}"
                
                parsed_transactions.append({
                    "Date": clean_date,
                    "Description": desc_val,
                    "Amount": amount_val,
                    "Bank": "Santander"
                })
                
    return parsed_transactions

# --- 3. STARLING PARSER ---
def parse_starling(pdf):
    parsed_transactions = []
    starling_pattern = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+£?([\d,]+\.\d{2})\s+£?[\d,]+\.\d{2}$')
    
    for page in pdf.pages:
        raw_text = page.extract_text()
        if not raw_text: continue
            
        for line in raw_text.split('\n'):
            line = line.strip()
            
            junk_headers = ["OPENING BALANCE", "CLOSING BALANCE", "DATE TYPE", "END OF DAY", "ACCOUNT BALANCE"]
            if any(junk in line.upper() for junk in junk_headers): continue
            
            match = starling_pattern.search(line)
            if match:
                raw_date = match.group(1)
                desc_val = match.group(2).strip() 
                amount_val = match.group(3)
                
                parsed_transactions.append({
                    "Date": raw_date,
                    "Description": desc_val,
                    "Amount": amount_val,
                    "Bank": "Starling"
                })
                
    return parsed_transactions

# --- 4. THE REVOLUT PARSER ---
def parse_revolut(pdf):
    parsed_transactions = []
    rev_pattern = re.compile(r'^(\d{1,2}\s[A-Za-z]{3,4}\s\d{4})\s+(.+?)\s+£?([\d,]+\.\d{2})\s+£?[\d,]+\.\d{2}$')
    reverted_pattern = re.compile(r'^(\d{1,2}\s[A-Za-z]{3,4}\s\d{4})\s+(.+?)\s+£?([\d,]+\.\d{2})$')
    
    current_date = ""
    current_desc = ""
    current_amount = ""

    for page in pdf.pages:
        raw_text = page.extract_text()
        if not raw_text: continue

        for line in raw_text.split('\n'):
            line = line.strip()
            if not line: continue

            if "REVPOINTS SPARE CHANGE" in line.upper(): continue

            junk_headers = [
                "BALANCE SUMMARY", "ACCOUNT TRANSACTIONS FROM", "PRODUCT", "OPENING BALANCE", 
                "CLOSING BALANCE", "REPORT LOST OR STOLEN", "SCAN THE QR CODE", "GET HELP DIRECTLY", 
                "PAGE", "GBP STATEMENT", "GENERATED ON", "REVERTED FROM", "START DATE",
                "REVOLUT LTD (NO.", "FINANCIAL CONDUCT AUTHORITY", "TRADING AND INVESTMENT SERVICES",
                "RESOLUTION COMPLIANCE", "A WHOLLY OWNED SUBSIDIARY", "ELECTRONIC MONEY REGULATIONS",
                "DATE DESCRIPTION MONEY" 
            ]
            
            if line.upper() == "REVOLUT LTD": continue
            if any(junk in line.upper() for junk in junk_headers): continue
            if line.startswith("+44 20") or line.startswith("©"): continue

            match = rev_pattern.search(line)
            rev_match = reverted_pattern.search(line)

            if match or rev_match:
                if current_date and current_amount:
                    parsed_transactions.append({
                        "Date": current_date,
                        "Description": current_desc.strip(),
                        "Amount": current_amount,
                        "Bank": "Revolut"
                    })

                if match:
                    current_date = match.group(1)
                    current_desc = match.group(2).strip()
                    current_amount = match.group(3)
                else:
                    current_date = rev_match.group(1)
                    current_desc = "[REVERTED] " + rev_match.group(2).strip()
                    current_amount = rev_match.group(3)
            else:
                if current_date: 
                    if "Revolut Rate" in line or "ECB rate" in line:
                        continue 
                    current_desc += " | " + line

    if current_date and current_amount:
        parsed_transactions.append({
            "Date": current_date,
            "Description": current_desc.strip(),
            "Amount": current_amount,
            "Bank": "Revolut"
        })

    return parsed_transactions

# --- 5. THE SMART ROUTER (Designed for Streamlit Uploads) ---
def process_pdf(file_object, file_name):
    """
    Takes a Streamlit uploaded file object, routes it, and returns a Pandas DataFrame.
    """
    try:
        with pdfplumber.open(file_object) as pdf:
            if len(pdf.pages) == 0:
                return None, f"❌ {file_name}: PDF is completely empty or locked."
                
            first_page_text = pdf.pages[0].extract_text()
            if not first_page_text:
                return None, f"❌ {file_name}: Contains no readable text (might be an image)."
                
            text_upper = first_page_text.upper()
            
            # Dynamic routing based on statement header
            if "REVOLUT" in text_upper:
                transactions = parse_revolut(pdf)
            elif "STARLING" in text_upper:
                transactions = parse_starling(pdf)
            elif "HSBC" in text_upper:
                transactions = parse_hsbc(pdf)
            elif "SANTANDER" in text_upper:
                transactions = parse_santander(pdf)
            else:
                return None, f"❓ {file_name}: Unsupported Bank. Only HSBC, Santander, Starling, and Revolut are allowed."
                
            if not transactions:
                 return None, f"⚠️ {file_name}: Recognized the bank, but couldn't find any valid transactions."
                 
            # Instantly map to Pandas in Volatile RAM
            df = pd.DataFrame(transactions)
            
            # Standardize and sort dates
            df['Date_Sorter'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce')
            df = df.dropna(subset=['Date_Sorter'])
            df = df.sort_values(by='Date_Sorter', ascending=True)
            
            # Reformat to match the clean UI (e.g., "10 Sep 2025")
            df['Date'] = df['Date_Sorter'].dt.strftime('%d %b %Y')
            df = df.drop(columns=['Date_Sorter'])
            
            return df, f"✅ {file_name}: Successfully extracted {len(df)} transactions!"

    except Exception as e:
        return None, f"🚨 {file_name}: Critical Error during extraction - {str(e)}"