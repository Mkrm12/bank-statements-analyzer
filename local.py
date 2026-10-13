"""
Local folder statement extractor.
Uses the unified column-aware engine from extractor.py.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from extractor import extract_statement

def run_local_extraction(folder_path="pdfs"):
    os.makedirs(folder_path, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    dfs = []
    
    print(f"📂 Scanning '{folder_path}' folder...")
    for filename in sorted(os.listdir(folder_path)):
        if not filename.lower().endswith(".pdf"):
            continue
        file_path = os.path.join(folder_path, filename)
        
        try:
            with open(file_path, "rb") as f:
                df, meta = extract_statement(f)
            if df is not None:
                df['Source_File'] = filename
                dfs.append(df)
                status = "✔ Reconciled" if meta.get("reconciled") else "Done"
                print(f"  ✅ {filename} ({meta.get('bank')}): {len(df)} txns [{status}]")
            else:
                print(f"  ❌ {filename}: {meta.get('error')}")
        except Exception as e:
            print(f"  🚨 {filename}: Error - {e}")

    if dfs:
        all_df = pd.concat(dfs, ignore_index=True)
        all_df['Date_Sorter'] = pd.to_datetime(all_df['Date'], format='mixed', errors='coerce')
        all_df = all_df.sort_values(by='Date_Sorter', ascending=True).reset_index(drop=True)
        all_df.drop(columns=['Date_Sorter'], inplace=True, errors='ignore')
        
        out_csv = "data/all_bank_statements.csv"
        all_df.to_csv(out_csv, index=False)
        print(f"\n🎉 Successfully saved {len(all_df)} unified transactions to {out_csv}")
    else:
        print("No valid statement transactions extracted.")

if __name__ == "__main__":
    folder = "pdfs" if os.path.exists("pdfs") else "pdf"
    run_local_extraction(folder)