import os
import glob
import pdfplumber

# 1. Define the folders we want to scout
folders_to_check = ["pdf", "pdf2", "pdf3"]

# 2. Gather all PDFs from all 3 folders
all_pdfs = []
for folder in folders_to_check:
    if os.path.exists(folder):
        all_pdfs.extend(glob.glob(f"{folder}/*.pdf"))
    else:
        print(f"⚠️ Folder '{folder}' does not exist yet. Skipping.")

if not all_pdfs:
    print("❌ No PDFs found in any of those folders!")
    exit()

print(f"🚀 Found {len(all_pdfs)} PDFs total. Starting the Scout Router...\n")
print("-" * 60)

# 3. The Router Logic
for pdf_path in all_pdfs:
    file_name = os.path.basename(pdf_path)
    folder_name = os.path.dirname(pdf_path)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) == 0:
                print(f"📁 [{folder_name}] {file_name} ➡️ ❌ INVALID (Empty or Locked PDF)")
                continue
                
            # Just read the first page to save time and memory
            first_page_text = pdf.pages[0].extract_text()
            
            if not first_page_text:
                print(f"📁 [{folder_name}] {file_name} ➡️ ❌ INVALID (Image-only or Unreadable)")
                continue
                
            text_upper = first_page_text.upper()
            
            # Security Check
            if "STATEMENT" not in text_upper and "ACCOUNT" not in text_upper:
                print(f"📁 [{folder_name}] {file_name} ➡️ ❌ INVALID (Not a Bank Statement)")
                continue
                
            # Bank Identification
            if "HSBC" in text_upper:
                print(f"📁 [{folder_name}] {file_name} ➡️ 🦁 HSBC")
            elif "SANTANDER" in text_upper:
                print(f"📁 [{folder_name}] {file_name} ➡️ 🏦 SANTANDER")
            else:
                print(f"📁 [{folder_name}] {file_name} ➡️ ❓ INVALID (Unsupported Bank)")
                
    except Exception as e:
        print(f"📁 [{folder_name}] {file_name} ➡️ 🚨 CRASH (File might be corrupted: {e})")

print("-" * 60)
print("✅ Scout complete.")