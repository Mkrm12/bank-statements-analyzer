import pdfplumber
import pandas as pd
import re
import datetime
import os

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
                    parsed_transactions.append({"Date": current_date, "Description": final_description, "Amount": actual_amount, "Bank": "HSBC"})
                text_buffer = "" 
            else:
                if current_date: text_buffer += " " + line
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
            if year_match: current_year = year_match.group(1)
            
            match = universal_pattern.search(line)
            if match:
                raw_date = match.group(1).strip()
                desc_val = match.group(2).strip()
                amount_val = match.group(3).strip()
                
                if "balance" in desc_val.lower() or "brought forward" in desc_val.lower(): continue
                
                desc_val = re.sub(r'\s+', ' ', desc_val)
                clean_date = re.sub(r'(st|nd|rd|th)', '', raw_date, flags=re.IGNORECASE)
                clean_date = re.sub(r'(\d+)([A-Za-z]+)', r'\1 \2', clean_date).strip()
                
                if not re.search(r'\d{4}', clean_date): clean_date = f"{clean_date} {current_year}"
                
                parsed_transactions.append({"Date": clean_date, "Description": desc_val, "Amount": amount_val, "Bank": "Santander"})
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
                parsed_transactions.append({"Date": match.group(1), "Description": match.group(2).strip(), "Amount": match.group(3), "Bank": "Starling"})
    return parsed_transactions

# --- 4. REVOLUT PARSER ---
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

            # 🛑 CRITICAL FIX: Massively expanded junk filters based on your errors
            junk_headers = [
                "BALANCE SUMMARY", "ACCOUNT TRANSACTIONS FROM", "PRODUCT", "OPENING BALANCE", 
                "CLOSING BALANCE", "REPORT LOST OR STOLEN", "SCAN THE QR CODE", "GET HELP DIRECTLY", 
                "PAGE", "GBP STATEMENT", "GENERATED ON", "REVERTED FROM", "START DATE",
                "REVOLUT LTD", "FINANCIAL CONDUCT AUTHORITY", "TRADING AND INVESTMENT SERVICES",
                "RESOLUTION COMPLIANCE", "A WHOLLY OWNED SUBSIDIARY", "ELECTRONIC MONEY REGULATIONS",
                "DATE DESCRIPTION MONEY", "ACTIVITIES.", "REPRESENTATIVE OF"
            ]
            
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

# --- 5. NATIONWIDE PARSER ---
def parse_nationwide(pdf):
    parsed_transactions = []
    current_year = str(datetime.datetime.now().year)
    current_date = ""

    # The Slicer
    junk_slice_pattern = re.compile(r'(?i)(Statement\s*date|Statement\s*no|Sort\s*code|Account\s*no|Your\s*FlexAccount|DC\d{2}|Nationwide\s*Building|Unless\s*stated|straightaway|This\s*information|Credit\s*interest|AER|Overdraft|Our\s*per|specialist|payments\s*being|An\s*international|from\s*a\s*LINK|your\s*transaction|usas\s*asterling|won\'t\s*apply|certainty|visit:|Page\s*\d+\s*/|Head\s*Office|transactions\s*\(continued\)|Date\s*Description|£Out|£In|£Balance).*')

    for page in pdf.pages:
        raw_text = page.extract_text(layout=True) 
        if not raw_text: 
            raw_text = page.extract_text()
        if not raw_text: continue

        for line in raw_text.split('\n'):
            line = line.strip()
            if not line: continue

            # Floating year check
            year_match = re.search(r'^20\d{2}$', line)
            if year_match:
                current_year = year_match.group(0)
                continue

            # Strict Date Match
            date_match = re.search(r'^(\d{2}\s[A-Za-z]{3})\s+(.*)$', line)
            if date_match:
                current_date = f"{date_match.group(1)} {current_year}"
                content = date_match.group(2)
            else:
                content = line 

            amount_match = re.search(r'^(.*?)\s+([\d,]+\.\d{2})(?:\s+[\d,]+\.\d{2})?$', content)

            if amount_match and current_date:
                desc = amount_match.group(1).strip()
                amount = amount_match.group(2).strip()

                # Slice off any hidden side-box junk glued to the main description
                desc = junk_slice_pattern.sub('', desc).strip()

                # 🛑 THE PHANTOM ROW KILL-SWITCH
                # If the description is literally just a year (e.g. "2026"), it's a balance row, ignore it!
                if re.match(r'^20\d{2}$', desc):
                    current_year = desc
                    continue

                if "Balance from statement" not in desc and desc:
                    parsed_transactions.append({
                        "Date": current_date,
                        "Description": desc,
                        "Amount": amount,
                        "Bank": "Nationwide"
                    })
            elif current_date and parsed_transactions:
                # Slicer applied to wrap text
                clean_content = junk_slice_pattern.sub('', content).strip()
                
                if clean_content:
                    # Final safety net: real wrap lines are short. Wall of text? Kill it.
                    if len(clean_content) < 60 and not re.search(r'[a-z]{4,}[.,]', clean_content):
                        # Ensure we don't accidentally append a year row
                        if not re.match(r'^20\d{2}$', clean_content):
                            parsed_transactions[-1]["Description"] += " " + clean_content
                    else:
                        current_date = "" # Stop appending

    return parsed_transactions

# --- 6. LOCAL FOLDER SCANNER ---
def run_local_extraction():
    os.makedirs("pdf", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    all_transactions = []
    
    print(f"📂 Scanning 'pdf' folder...")
    for filename in os.listdir("pdf"):
        if not filename.lower().endswith(".pdf"): continue
        file_path = os.path.join("pdf", filename)
        
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0: continue
            first_page = pdf.pages[0].extract_text().upper()
            
            if "NATIONWIDE" in first_page: transactions = parse_nationwide(pdf)
            elif "REVOLUT" in first_page: transactions = parse_revolut(pdf)
            elif "STARLING" in first_page: transactions = parse_starling(pdf)
            elif "HSBC" in first_page: transactions = parse_hsbc(pdf)
            elif "SANTANDER" in first_page: transactions = parse_santander(pdf)
            else: continue
                
            all_transactions.extend(transactions)
            print(f"✅ Processed: {filename}")
            
    if all_transactions:
        df = pd.DataFrame(all_transactions)
        df['Date_Sorter'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Date_Sorter']).sort_values(by='Date_Sorter', ascending=True)
        df['Date'] = df['Date_Sorter'].dt.strftime('%d %b %Y')
        df = df.drop(columns=['Date_Sorter'])
        
        df.to_csv("data/all_bank_statements.csv", index=False)
        print(f"🎉 Saved {len(df)} transactions to data/all_bank_statements.csv")

if __name__ == "__main__":
    run_local_extraction()