"""
Synthetic Bank Statement Generator & Evaluation Harness.

Generates 3 realistic UK bank statements (100 transactions each) for a fictional
user (Jordan Ellis) with 3 interconnected accounts:
1. Barclays Current Account (daily spend, salary, rent, commute, dining, transfers)
2. Nationwide Household Account (mortgage, utilities, car, family, pets, transfers)
3. Northbridge Side-Hustle Account (business income, software, tax, BNPL, fees, transfers)

Includes 25+ deliberate edge-case traps (e.g., Cash Converters vs ATM, Shell Energy vs Fuel,
Sky Bet vs Telecom, Tesco Mobile vs Groceries, HMRC tax rebate vs Salary, PayPal withdrawals,
internal transfer pairs, etc.) to rigorously test generalisation without overfitting.
"""
import os
import sys
import csv
import datetime as dt
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def build_pdf_bytes(pages_items, page_width=595, page_height=842):
    """
    Pure Python multi-page PDF generator without any third-party PDF library.
    pages_items is a list of pages; each page is a list of tuples:
    (x, y, font_name, font_size, text)
    where font_name is 'F1' (Helvetica) or 'F2' (Helvetica-Bold).
    """
    page_count = len(pages_items)
    kids = ' '.join(f'{5 + i*2} 0 R' for i in range(page_count))
    objs = []
    objs.append('1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n')
    objs.append(f'2 0 obj << /Type /Pages /Kids [{kids}] /Count {page_count} >> endobj\n')
    objs.append('3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n')
    objs.append('4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> endobj\n')

    for i, p_items in enumerate(pages_items):
        page_obj_id = 5 + i * 2
        content_obj_id = 6 + i * 2
        stream_parts = ['BT\n']
        for x, y, font, size, text in p_items:
            escaped = (
                str(text)
                .replace('\\', '\\\\')
                .replace('(', '\\(')
                .replace(')', '\\)')
            )
            stream_parts.append(f'/{font} {size} Tf\n1 0 0 1 {x} {y} Tm\n({escaped}) Tj\n')
        stream_parts.append('ET\n')
        stream_bytes = ''.join(stream_parts).encode('latin1')

        objs.append(
            f'{page_obj_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] '
            f'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj_id} 0 R >> endobj\n'
        )
        objs.append(
            f'{content_obj_id} 0 obj << /Length {len(stream_bytes)} >>\nstream\n'
            + ''.join(stream_parts)
            + 'endstream\nendobj\n'
        )

    total_objs = 4 + page_count * 2
    header = '%PDF-1.4\n'
    xref = [f'xref\n0 {total_objs + 1}\n0000000000 65535 f \n']
    body = ''
    offset = len(header.encode('latin1'))
    for obj in objs:
        xref.append(f'{offset:010d} 00000 n \n')
        body += obj
        offset += len(obj.encode('latin1'))

    startxref = offset
    trailer = f'trailer << /Size {total_objs + 1} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n'
    return (header + body + ''.join(xref) + trailer).encode('latin1')


def render_statement_pdf(
    bank_title,
    header_lines,
    summary_text,
    column_headers, # (date_lbl, desc_lbl, out_lbl, in_lbl, bal_lbl)
    txns_data,      # list of dicts: Date, Description, Amount, Direction, Running_Balance
    col_x=(40, 110, 360, 440, 520),
    statement_date="31 Mar 2026"
):
    """
    Renders a multi-page bank statement with Page 1 summary reconciliation
    and repeated table headers across pages.
    col_x: (date_x, desc_x, out_x, in_x, bal_x)
    """
    date_x, desc_x, out_x, in_x, bal_x = col_x
    pages_items = []
    
    # --- PAGE 1 ---
    p1 = []
    y = 800
    p1.append((40, y, 'F2', 14, bank_title))
    y -= 18
    for hl in header_lines:
        p1.append((40, y, 'F1', 9, hl))
        y -= 14
    p1.append((40, y, 'F1', 9, f'Statement Date: {statement_date}'))
    y -= 18
    p1.append((40, y, 'F2', 9, summary_text))
    y -= 25

    # Table Header helper
    def add_table_header(item_list, at_y):
        item_list.append((date_x, at_y, 'F2', 9, column_headers[0]))
        item_list.append((desc_x, at_y, 'F2', 9, column_headers[1]))
        item_list.append((out_x, at_y, 'F2', 9, column_headers[2]))
        item_list.append((in_x, at_y, 'F2', 9, column_headers[3]))
        item_list.append((bal_x, at_y, 'F2', 9, column_headers[4]))

    add_table_header(p1, y)
    y -= 18

    current_page_items = p1
    pages_items.append(current_page_items)

    for txn in txns_data:
        if y < 60:
            # Start new page
            current_page_items = []
            pages_items.append(current_page_items)
            y = 800
            current_page_items.append((40, y, 'F2', 10, f'{bank_title} (Continued)'))
            y -= 25
            add_table_header(current_page_items, y)
            y -= 18

        d_str = str(txn['Date'])
        desc_str = str(txn['Description'])[:42] # truncate to avoid column overlap
        amt_str = f"{txn['Amount']:.2f}"
        bal_str = f"{txn['Running_Balance']:.2f}"

        current_page_items.append((date_x, y, 'F1', 8.5, d_str))
        current_page_items.append((desc_x, y, 'F1', 8.5, desc_str))
        if txn['Direction'] == 'Out':
            current_page_items.append((out_x, y, 'F1', 8.5, amt_str))
        else:
            current_page_items.append((in_x, y, 'F1', 8.5, amt_str))
        current_page_items.append((bal_x, y, 'F1', 8.5, bal_str))
        y -= 15

    return build_pdf_bytes(pages_items)


def create_statement_datasets():
    """
    Builds the 3 100-row statement specifications with transactions,
    running balances, traps, and expected labels.
    """
    # -------------------------------------------------------------
    # 1. BARCLAYS CURRENT ACCOUNT (Jordan Ellis)
    # -------------------------------------------------------------
    barclays_rows = [
        # Inflows / Salary
        {"Date": "01 Mar 2026", "Description": "ACME GLOBAL CORP MONTHLY SALARY", "Amount": 3450.00, "Direction": "In", "Cat": "Salary", "Sub": "Employment Wages", "Trap": False, "Reason": ""},
        {"Date": "01 Mar 2026", "Description": "HMRC TAX REBATE REFUND", "Amount": 184.20, "Direction": "In", "Cat": "Benefits", "Sub": "Tax Rebates", "Trap": True, "Reason": "HMRC Inflow is a tax rebate/benefit, NOT employment salary"},
        {"Date": "02 Mar 2026", "Description": "RENT PAYMENT TO LANDLORD SMITH", "Amount": 1100.00, "Direction": "Out", "Cat": "Rent", "Sub": "Tenancy Rent", "Trap": False, "Reason": ""},
        
        # Internal Transfers (cross-account)
        {"Date": "02 Mar 2026", "Description": "To: Jordan Ellis Nationwide", "Amount": 650.00, "Direction": "Out", "Cat": "Transfers", "Sub": "Internal Account Transfer", "Trap": True, "Reason": "Own-account transfer to Nationwide household account"},
        {"Date": "03 Mar 2026", "Description": "To: Jordan Ellis Northbridge", "Amount": 300.00, "Direction": "Out", "Cat": "Transfers", "Sub": "Internal Account Transfer", "Trap": True, "Reason": "Own-account transfer to Northbridge side-hustle account"},
        
        # Commute & Transport
        {"Date": "03 Mar 2026", "Description": "TFL TRAVEL CHG TFL.GOV.UK", "Amount": 3.40, "Direction": "Out", "Cat": "Transport", "Sub": "Public Transit", "Trap": False, "Reason": ""},
        {"Date": "03 Mar 2026", "Description": "TFL TRAVEL CHG TFL.GOV.UK", "Amount": 3.40, "Direction": "Out", "Cat": "Transport", "Sub": "Public Transit", "Trap": True, "Reason": "Legitimate duplicate tap on same day, must NOT be deduped"},
        {"Date": "04 Mar 2026", "Description": "TRAINLINE TICKETS LONDON BRG", "Amount": 28.50, "Direction": "Out", "Cat": "Transport", "Sub": "Trains & Rail", "Trap": False, "Reason": ""},
        
        # Ride-hailing vs Food Delivery Trap
        {"Date": "04 Mar 2026", "Description": "UBER TRIP HELP.UBER.COM", "Amount": 16.80, "Direction": "Out", "Cat": "Taxis", "Sub": "Ride-Hailing", "Trap": True, "Reason": "Uber ride must be Taxis, NOT general Transport or Takeaway"},
        {"Date": "04 Mar 2026", "Description": "UBER *EATS PENDING", "Amount": 21.40, "Direction": "Out", "Cat": "Takeaway", "Sub": "Food Delivery", "Trap": True, "Reason": "Uber Eats must be Takeaway, NOT Taxis or Transport"},
        
        # Digit-glued merchant trap
        {"Date": "05 Mar 2026", "Description": "))) SUBWAY18831-0 UXBRIDGE", "Amount": 8.49, "Direction": "Out", "Cat": "Takeaway", "Sub": "Fast Food", "Trap": True, "Reason": "Digit-glued SUBWAY18831 must match Subway Takeaway, NOT Unknown"},
        {"Date": "05 Mar 2026", "Description": "PRET A MANGER VICTORIA", "Amount": 4.85, "Direction": "Out", "Cat": "Coffee", "Sub": "Cafes & Coffee", "Trap": False, "Reason": ""},
        
        # Groceries
        {"Date": "05 Mar 2026", "Description": "TESCO STORES 4921", "Amount": 42.18, "Direction": "Out", "Cat": "Groceries", "Sub": "Supermarket", "Trap": False, "Reason": ""},
        {"Date": "06 Mar 2026", "Description": "SAINSBURYS S/MKTS LONDON", "Amount": 29.60, "Direction": "Out", "Cat": "Groceries", "Sub": "Supermarket", "Trap": False, "Reason": ""},
        {"Date": "06 Mar 2026", "Description": "LIDL GB UXBRIDGE", "Amount": 18.25, "Direction": "Out", "Cat": "Groceries", "Sub": "Supermarket", "Trap": False, "Reason": ""},
        {"Date": "06 Mar 2026", "Description": "PNR SUPERSTORE LONDON", "Amount": 4.50, "Direction": "Out", "Cat": "Groceries", "Sub": "Local Convenience", "Trap": True, "Reason": "PNR Superstore is a convenience food store, NOT transport"},

        # Trap: Cash Converters vs ATM
        {"Date": "07 Mar 2026", "Description": "CASH CONVERTERS UXBRIDGE", "Amount": 35.00, "Direction": "Out", "Cat": "Shopping", "Sub": "Secondhand & Variety", "Trap": True, "Reason": "Cash Converters is a retail store, NOT ATM Cash"},
        {"Date": "07 Mar 2026", "Description": "ATM CASH BARCLAYS HIGH ST", "Amount": 40.00, "Direction": "Out", "Cat": "Cash", "Sub": "ATM Withdrawal", "Trap": False, "Reason": ""},
        
        # Trap: Shell Energy vs Fuel
        {"Date": "08 Mar 2026", "Description": "SHELL ENERGY DIRECT DEBIT", "Amount": 78.50, "Direction": "Out", "Cat": "Energy", "Sub": "Gas & Electricity", "Trap": True, "Reason": "Shell Energy is home utility, NOT vehicle fuel"},
        {"Date": "08 Mar 2026", "Description": "BP CONNECT LEWISHAM", "Amount": 45.00, "Direction": "Out", "Cat": "Fuel", "Sub": "Petrol & Diesel", "Trap": True, "Reason": "BP fuel station; prefix BP must NOT be stripped as Bill Payment"},
        
        # Trap: Sky Bet vs Broadband
        {"Date": "09 Mar 2026", "Description": "SKY BET ONLINE DEPOSIT", "Amount": 15.00, "Direction": "Out", "Cat": "Gambling", "Sub": "Sports Betting", "Trap": True, "Reason": "Sky Bet is gambling, NOT Sky broadband/TV"},
        {"Date": "09 Mar 2026", "Description": "SKY BROADBAND DIRECT DEBIT", "Amount": 34.00, "Direction": "Out", "Cat": "Broadband", "Sub": "Internet Service", "Trap": False, "Reason": ""},
        
        # Trap: O2 Academy vs Mobile
        {"Date": "10 Mar 2026", "Description": "O2 ACADEMY BRIXTON TICKETS", "Amount": 42.50, "Direction": "Out", "Cat": "Entertainment", "Sub": "Live Events & Gigs", "Trap": True, "Reason": "O2 Academy is entertainment venue, NOT O2 mobile phone"},
        {"Date": "10 Mar 2026", "Description": "O2 MOBILE MONTHLY CONTRACT", "Amount": 22.00, "Direction": "Out", "Cat": "Mobile", "Sub": "Phone Contract", "Trap": False, "Reason": ""},
        
        # Trap: Tesco Mobile vs Groceries
        {"Date": "11 Mar 2026", "Description": "TESCO MOBILE DIRECT DEBIT", "Amount": 12.50, "Direction": "Out", "Cat": "Mobile", "Sub": "Phone Contract", "Trap": True, "Reason": "Tesco Mobile is phone contract, NOT Tesco grocery store"},
        {"Date": "11 Mar 2026", "Description": "TESCO BANK CREDIT CARD PMT", "Amount": 120.00, "Direction": "Out", "Cat": "Credit Card", "Sub": "Card Repayment", "Trap": True, "Reason": "Tesco Bank payment is credit card debt repayment, NOT groceries"},
        
        # Trap: Amazon Prime Video vs Shopping & Inflow Refund
        {"Date": "12 Mar 2026", "Description": "AMAZON PRIME VIDEO SUBSCRIPTION", "Amount": 8.99, "Direction": "Out", "Cat": "Streaming", "Sub": "Video Streaming", "Trap": True, "Reason": "Prime Video is digital streaming subscription, NOT marketplace shopping"},
        {"Date": "12 Mar 2026", "Description": "AMAZON UK MARKETPLACE", "Amount": 24.99, "Direction": "Out", "Cat": "Shopping", "Sub": "Online Retail", "Trap": False, "Reason": ""},
        {"Date": "13 Mar 2026", "Description": "AMAZON UK MARKETPLACE REFUND", "Amount": 24.99, "Direction": "In", "Cat": "Refunds", "Sub": "Merchant Refund", "Trap": True, "Reason": "Amazon Inflow is a store return refund, NOT income or shopping"},
        
        # Trap: PayPal withdrawal vs Merchant Refund
        {"Date": "13 Mar 2026", "Description": "FASTER PAYMENTS PPWDL53HJ FROM PAYPAL", "Amount": 150.00, "Direction": "In", "Cat": "Transfers", "Sub": "Payment App Withdrawal", "Trap": True, "Reason": "PayPal balance withdrawal (PPWDL) is money transfer, NOT merchant refund"},
        
        # Trap: Salary Finance Loan vs Employment Salary
        {"Date": "14 Mar 2026", "Description": "SALARY FINANCE LOAN REPAYMENT", "Amount": 85.00, "Direction": "Out", "Cat": "Loans", "Sub": "Loan Instalment", "Trap": True, "Reason": "Salary Finance Outflow is a loan repayment, NOT salary or transfer"},
        
        # Dining, Coffee, Bars & Takeaways (distinct categories)
        {"Date": "14 Mar 2026", "Description": "DISHOOM COVENT GARDEN", "Amount": 48.60, "Direction": "Out", "Cat": "Dining", "Sub": "Restaurants", "Trap": False, "Reason": ""},
        {"Date": "15 Mar 2026", "Description": "FRANCO MANCA SOHO", "Amount": 18.50, "Direction": "Out", "Cat": "Dining", "Sub": "Restaurants", "Trap": False, "Reason": ""},
        {"Date": "15 Mar 2026", "Description": "GREGGS THE BAKERY LONDON", "Amount": 3.65, "Direction": "Out", "Cat": "Takeaway", "Sub": "Fast Food", "Trap": False, "Reason": ""},
        {"Date": "16 Mar 2026", "Description": "STARBUCKS COFFEE KINGS CROSS", "Amount": 4.45, "Direction": "Out", "Cat": "Coffee", "Sub": "Cafes & Coffee", "Trap": False, "Reason": ""},
        {"Date": "16 Mar 2026", "Description": "THE RED LION PUB WESTMINSTER", "Amount": 14.80, "Direction": "Out", "Cat": "Bars", "Sub": "Pubs & Bars", "Trap": False, "Reason": ""},
        {"Date": "17 Mar 2026", "Description": "BREWDOG SEVEN DIALS", "Amount": 18.20, "Direction": "Out", "Cat": "Bars", "Sub": "Pubs & Bars", "Trap": False, "Reason": ""},
        {"Date": "17 Mar 2026", "Description": "DELIVEROO ORDER LONDON", "Amount": 26.50, "Direction": "Out", "Cat": "Takeaway", "Sub": "Food Delivery", "Trap": False, "Reason": ""},
        {"Date": "18 Mar 2026", "Description": "JUST EAT PIZZA TAKEAWAY", "Amount": 19.80, "Direction": "Out", "Cat": "Takeaway", "Sub": "Food Delivery", "Trap": False, "Reason": ""},
        
        # Peer to Peer Transfers (distinct from own Transfers)
        {"Date": "18 Mar 2026", "Description": "To: Sarah Jenkins (Dinner share)", "Amount": 24.30, "Direction": "Out", "Cat": "Peer-to-Peer", "Sub": "Personal Transfer", "Trap": True, "Reason": "Payment to another person is Peer-to-Peer, NOT internal transfer"},
        {"Date": "19 Mar 2026", "Description": "From: Michael Brown (Concert ticket)", "Amount": 45.00, "Direction": "In", "Cat": "Peer-to-Peer", "Sub": "Personal Transfer", "Trap": True, "Reason": "Receipt from another person is Peer-to-Peer, NOT income or internal transfer"},
        {"Date": "19 Mar 2026", "Description": "To: Alex Davies", "Amount": 15.00, "Direction": "Out", "Cat": "Peer-to-Peer", "Sub": "Personal Transfer", "Trap": False, "Reason": ""},
        
        # Digital Subscriptions & Tech
        {"Date": "20 Mar 2026", "Description": "NETFLIX.COM MONTHLY", "Amount": 10.99, "Direction": "Out", "Cat": "Streaming", "Sub": "Video Streaming", "Trap": False, "Reason": ""},
        {"Date": "20 Mar 2026", "Description": "SPOTIFY UK SUBSCRIPTION", "Amount": 11.99, "Direction": "Out", "Cat": "Streaming", "Sub": "Music Streaming", "Trap": False, "Reason": ""},
        {"Date": "20 Mar 2026", "Description": "DISNEY PLUS STREAMING", "Amount": 7.99, "Direction": "Out", "Cat": "Streaming", "Sub": "Video Streaming", "Trap": False, "Reason": ""},
        {"Date": "21 Mar 2026", "Description": "OPENAI CHATGPT PLUS", "Amount": 19.99, "Direction": "Out", "Cat": "Software", "Sub": "AI Tools", "Trap": False, "Reason": ""},
        {"Date": "21 Mar 2026", "Description": "GOOGLE ONE CLOUD STORAGE", "Amount": 1.99, "Direction": "Out", "Cat": "Software", "Sub": "Cloud Storage", "Trap": False, "Reason": ""},
        
        # Fashion & Beauty (distinct from general Shopping)
        {"Date": "22 Mar 2026", "Description": "ZARA CLOTHING OXFORD ST", "Amount": 65.00, "Direction": "Out", "Cat": "Fashion", "Sub": "Clothing & Apparel", "Trap": False, "Reason": ""},
        {"Date": "22 Mar 2026", "Description": "ASOS.COM FASHION ORDER", "Amount": 38.50, "Direction": "Out", "Cat": "Fashion", "Sub": "Online Fashion", "Trap": False, "Reason": ""},
        {"Date": "23 Mar 2026", "Description": "BOOTS THE CHEMIST UXBRIDGE", "Amount": 14.20, "Direction": "Out", "Cat": "Beauty", "Sub": "Cosmetics & Toiletries", "Trap": False, "Reason": ""},
        {"Date": "23 Mar 2026", "Description": "SUPERDRUG STORES LONDON", "Amount": 8.75, "Direction": "Out", "Cat": "Beauty", "Sub": "Cosmetics & Toiletries", "Trap": False, "Reason": ""},
        {"Date": "24 Mar 2026", "Description": "TRADITIONAL TURKISH BARBER", "Amount": 22.00, "Direction": "Out", "Cat": "Beauty", "Sub": "Hair & Grooming", "Trap": False, "Reason": ""},

        # Traps: Fees
        {"Date": "24 Mar 2026", "Description": "OVERDRAFT MONTHLY USAGE FEE", "Amount": 6.50, "Direction": "Out", "Cat": "Fees", "Sub": "Bank Charges", "Trap": True, "Reason": "Bank overdraft charge is Fees, NOT general spending"},
        {"Date": "25 Mar 2026", "Description": "NON-STERLING TRANSACTION FEE", "Amount": 1.75, "Direction": "Out", "Cat": "Fees", "Sub": "Foreign Exchange Fees", "Trap": True, "Reason": "Card currency fee is Fees, NOT Shopping"},

        # BNPL & Debt
        {"Date": "25 Mar 2026", "Description": "KLARNA INSTALMENT PMT 1 OF 3", "Amount": 24.50, "Direction": "Out", "Cat": "BNPL", "Sub": "Buy Now Pay Later", "Trap": False, "Reason": ""},
        {"Date": "26 Mar 2026", "Description": "CLEARPAY MONTHLY SPLIT", "Amount": 18.00, "Direction": "Out", "Cat": "BNPL", "Sub": "Buy Now Pay Later", "Trap": False, "Reason": ""},

        # Fitness & Health
        {"Date": "26 Mar 2026", "Description": "PUREGYM MONTHLY MEMBERSHIP", "Amount": 26.99, "Direction": "Out", "Cat": "Fitness", "Sub": "Gym Membership", "Trap": False, "Reason": ""},
        {"Date": "27 Mar 2026", "Description": "BOOTS PHARMACY PRESCRIPTION", "Amount": 9.65, "Direction": "Out", "Cat": "Health", "Sub": "Pharmacy & Medicine", "Trap": False, "Reason": ""},
        
        # Entertainment & Gaming
        {"Date": "27 Mar 2026", "Description": "ODEON CINEMAS TICKETS", "Amount": 21.00, "Direction": "Out", "Cat": "Entertainment", "Sub": "Cinema & Theatre", "Trap": False, "Reason": ""},
        {"Date": "28 Mar 2026", "Description": "STEAM GAMES PURCHASE", "Amount": 14.99, "Direction": "Out", "Cat": "Gaming", "Sub": "Video Games", "Trap": False, "Reason": ""},
        {"Date": "28 Mar 2026", "Description": "PLAYSTATION NETWORK PSN", "Amount": 6.99, "Direction": "Out", "Cat": "Gaming", "Sub": "Gaming Subscription", "Trap": False, "Reason": ""},
        
        # Miscellaneous realistic daily items to bring count to exactly 100
    ]
    
    # Fill remaining rows up to 100 with realistic items
    additional_barclays = [
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG", 3.40, "Out", "Transport", "Public Transit"),
        ("TESCO STORES", 12.45, "Out", "Groceries", "Supermarket"),
        ("SAINSBURYS", 8.90, "Out", "Groceries", "Supermarket"),
        ("M&S SIMPLY FOOD", 14.20, "Out", "Groceries", "Supermarket"),
        ("WAITROSE", 16.50, "Out", "Groceries", "Supermarket"),
        ("COSTA COFFEE", 3.80, "Out", "Coffee", "Cafes & Coffee"),
        ("CAFFE NERO", 3.65, "Out", "Coffee", "Cafes & Coffee"),
        ("MCDONALDS RESTAURANT", 7.29, "Out", "Takeaway", "Fast Food"),
        ("KFC RESTAURANT", 8.49, "Out", "Takeaway", "Fast Food"),
        ("NANDOS CHICKEN", 16.50, "Out", "Dining", "Restaurants"),
        ("WAGAMAMA NOODLES", 18.20, "Out", "Dining", "Restaurants"),
        ("ARGOS RETAIL STORE", 22.99, "Out", "Shopping", "Department Stores"),
        ("JOHN LEWIS & PARTNERS", 45.00, "Out", "Shopping", "Department Stores"),
        ("WATERSTONES BOOKS", 12.99, "Out", "Education", "Books & Stationery"),
        ("POST OFFICE POSTAGE", 4.85, "Out", "Services", "Postal Services"),
        ("TIMPSON SHOE REPAIRS", 11.00, "Out", "Services", "Key Cutting & Repairs"),
        ("ATM CASH LINK HIGH ST", 20.00, "Out", "Cash", "ATM Withdrawal"),
        ("ATM CASH NOTEMACHINE", 50.00, "Out", "Cash", "ATM Withdrawal"),
        ("SHELL PETROL STATION", 38.00, "Out", "Fuel", "Petrol & Diesel"),
        ("RINGGO PARKING LONDON", 4.20, "Out", "Parking", "Parking Charges"),
        ("JUSTPARK METERS", 3.50, "Out", "Parking", "Parking Charges"),
        ("UBER RIDE CITY", 12.40, "Out", "Taxis", "Ride-Hailing"),
        ("BOLT RIDES LONDON", 11.20, "Out", "Taxis", "Ride-Hailing"),
        ("BRITISH HEART FOUNDATION", 5.00, "Out", "Charity", "Donations"),
        ("CANCER RESEARCH UK", 10.00, "Out", "Charity", "Donations"),
        ("NATIONAL LOTTERY ONLINE", 5.00, "Out", "Gambling", "Lottery"),
        ("BET365 ONLINE", 10.00, "Out", "Gambling", "Sports Betting"),
        ("MOONPIG GREETING CARDS", 4.99, "Out", "Gifts", "Cards & Gifts"),
        ("CARD FACTORY UXBRIDGE", 2.50, "Out", "Gifts", "Cards & Gifts"),
        ("SEPHORA UK BEAUTY", 28.00, "Out", "Beauty", "Cosmetics"),
        ("UNIQLO CLOTHING", 34.90, "Out", "Fashion", "Clothing"),
        ("H&M APPAREL", 19.99, "Out", "Fashion", "Clothing")
    ]
    
    day_counter = 1
    for desc, amt, dir_, cat, sub in additional_barclays[:(100 - len(barclays_rows))]:
        d_str = f"{(day_counter % 28) + 1:02d} Mar 2026"
        day_counter += 1
        barclays_rows.append({
            "Date": d_str, "Description": desc, "Amount": amt, "Direction": dir_,
            "Cat": cat, "Sub": sub, "Trap": False, "Reason": ""
        })

    # -------------------------------------------------------------
    # 2. NATIONWIDE HOUSEHOLD ACCOUNT (Jordan Ellis)
    # -------------------------------------------------------------
    nationwide_rows = [
        # Internal transfer received from Barclays
        {"Date": "02/03/2026", "Description": "From: Jordan Ellis Barclays", "Amount": 650.00, "Direction": "In", "Cat": "Transfers", "Sub": "Internal Account Transfer", "Trap": True, "Reason": "Matching pair of Barclays Out transfer, internal transfer"},
        {"Date": "02/03/2026", "Description": "NATIONWIDE BS MORTGAGE DIRECT DEBIT", "Amount": 845.00, "Direction": "Out", "Cat": "Mortgage", "Sub": "Mortgage Payment", "Trap": False, "Reason": ""},
        {"Date": "03/03/2026", "Description": "COUNCIL TAX LONDON BOROUGH", "Amount": 145.00, "Direction": "Out", "Cat": "Council Tax", "Sub": "Local Council Tax", "Trap": False, "Reason": ""},
        {"Date": "03/03/2026", "Description": "BRITISH GAS ENERGY DIRECT DEBIT", "Amount": 115.40, "Direction": "Out", "Cat": "Energy", "Sub": "Electricity & Gas", "Trap": False, "Reason": ""},
        {"Date": "04/03/2026", "Description": "THAMES WATER UTILITIES DIRECT DEBIT", "Amount": 38.60, "Direction": "Out", "Cat": "Water", "Sub": "Water Rates", "Trap": False, "Reason": ""},
        {"Date": "04/03/2026", "Description": "VIRGIN MEDIA BROADBAND & TV", "Amount": 48.00, "Direction": "Out", "Cat": "Broadband", "Sub": "Home Internet", "Trap": False, "Reason": ""},
        {"Date": "05/03/2026", "Description": "EE HOME & MOBILE CONTRACT", "Amount": 35.00, "Direction": "Out", "Cat": "Mobile", "Sub": "Mobile Contract", "Trap": False, "Reason": ""},
        {"Date": "05/03/2026", "Description": "ADMIRAL CAR INSURANCE DIRECT DEBIT", "Amount": 62.50, "Direction": "Out", "Cat": "Insurance", "Sub": "Vehicle Insurance", "Trap": False, "Reason": ""},
        {"Date": "06/03/2026", "Description": "AVIVA HOME & CONTENTS INSURANCE", "Amount": 28.00, "Direction": "Out", "Cat": "Insurance", "Sub": "Home Insurance", "Trap": False, "Reason": ""},
        {"Date": "06/03/2026", "Description": "PETPLAN PET INSURANCE DOG", "Amount": 31.20, "Direction": "Out", "Cat": "Pets", "Sub": "Pet Insurance", "Trap": False, "Reason": ""},
        {"Date": "07/03/2026", "Description": "VETS4PETS ANIMAL CLINIC", "Amount": 54.00, "Direction": "Out", "Cat": "Pets", "Sub": "Veterinary Care", "Trap": False, "Reason": ""},
        {"Date": "07/03/2026", "Description": "ZOOPLUS UK PET FOOD SUPPLIES", "Amount": 42.80, "Direction": "Out", "Cat": "Pets", "Sub": "Pet Food & Supplies", "Trap": False, "Reason": ""},
        {"Date": "08/03/2026", "Description": "BUSY BEES NURSERY CHILDCARE", "Amount": 240.00, "Direction": "Out", "Cat": "Childcare", "Sub": "Day Nursery", "Trap": False, "Reason": ""},
        {"Date": "08/03/2026", "Description": "B&Q HOME IMPROVEMENT DIY", "Amount": 64.50, "Direction": "Out", "Cat": "Home", "Sub": "DIY & Hardware", "Trap": False, "Reason": ""},
        {"Date": "09/03/2026", "Description": "IKEA UK FURNITURE & HOME", "Amount": 112.00, "Direction": "Out", "Cat": "Home", "Sub": "Furniture & Decor", "Trap": False, "Reason": ""},
        {"Date": "09/03/2026", "Description": "DUNELM HOMES CURTAINS & BEDDING", "Amount": 45.00, "Direction": "Out", "Cat": "Home", "Sub": "Home Furnishings", "Trap": False, "Reason": ""},
        {"Date": "10/03/2026", "Description": "HALFORDS AUTO SERVICE & MOT", "Amount": 85.00, "Direction": "Out", "Cat": "Motoring", "Sub": "Service & MOT", "Trap": False, "Reason": ""},
        {"Date": "10/03/2026", "Description": "DVLA ROAD TAX ANNUAL PAYMENT", "Amount": 190.00, "Direction": "Out", "Cat": "Motoring", "Sub": "Road Tax", "Trap": False, "Reason": ""},
        {"Date": "11/03/2026", "Description": "KWIK FIT TYRES REPLACEMENT", "Amount": 140.00, "Direction": "Out", "Cat": "Motoring", "Sub": "Tyres & Repairs", "Trap": False, "Reason": ""},
        {"Date": "11/03/2026", "Description": "ESSO SERVICE STATION FUEL", "Amount": 55.00, "Direction": "Out", "Cat": "Fuel", "Sub": "Petrol & Diesel", "Trap": False, "Reason": ""},
        {"Date": "12/03/2026", "Description": "TEXACO FUEL FORECOURT", "Amount": 48.00, "Direction": "Out", "Cat": "Fuel", "Sub": "Petrol & Diesel", "Trap": False, "Reason": ""},
        # Child benefit inflow
        {"Date": "12/03/2026", "Description": "HMRC CHILD BENEFIT DEPOSIT", "Amount": 102.40, "Direction": "In", "Cat": "Benefits", "Sub": "Child Benefit", "Trap": True, "Reason": "HMRC Child Benefit is state benefits, NOT salary"},
        # Savings Vault transfer
        {"Date": "13/03/2026", "Description": "TRANSFER TO NATIONWIDE SAVINGS VAULT", "Amount": 200.00, "Direction": "Out", "Cat": "Savings", "Sub": "Savings Transfer", "Trap": False, "Reason": ""},
        # Supermarkets & Family provisions
        {"Date": "13/03/2026", "Description": "ASDA SUPERSTORE FAMILY SHOP", "Amount": 78.40, "Direction": "Out", "Cat": "Groceries", "Sub": "Supermarket", "Trap": False, "Reason": ""},
        {"Date": "14/03/2026", "Description": "MORRISONS SUPERMARKET", "Amount": 52.10, "Direction": "Out", "Cat": "Groceries", "Sub": "Supermarket", "Trap": False, "Reason": ""},
        {"Date": "14/03/2026", "Description": "ALDI STORES UXBRIDGE", "Amount": 34.60, "Direction": "Out", "Cat": "Groceries", "Sub": "Supermarket", "Trap": False, "Reason": ""},
    ]

    # Additional household rows to reach 100
    nationwide_extra = [
        ("TESCO STORES", 32.50, "Out", "Groceries", "Supermarket"),
        ("SAINSBURYS", 28.40, "Out", "Groceries", "Supermarket"),
        ("LIDL STORES", 19.90, "Out", "Groceries", "Supermarket"),
        ("BOOTS PHARMACY", 11.20, "Out", "Health", "Pharmacy"),
        ("SPECSAVERS OPTICIANS", 45.00, "Out", "Health", "Optical Care"),
        ("DENTAL PRACTICE CHECKUP", 65.00, "Out", "Health", "Dental Care"),
        ("MARKS & SPENCER FOOD", 24.50, "Out", "Groceries", "Supermarket"),
        ("WAITROSE SUPERMARKET", 38.00, "Out", "Groceries", "Supermarket"),
        ("B&Q GARDEN CENTRE", 28.50, "Out", "Home", "Garden & DIY"),
        ("SCREWFIX HARDWARE", 19.99, "Out", "Home", "Hardware"),
        ("TOOLSTATION TRADING", 14.50, "Out", "Home", "Hardware"),
        ("WILKO RETAIL STORES", 12.80, "Out", "Home", "Homeware"),
        ("PETS AT HOME STORE", 26.40, "Out", "Pets", "Pet Supplies"),
        ("JOJO MAMAN BEBE CHILDWEAR", 32.00, "Out", "Childcare", "Children Clothing"),
        ("CLARKS SHOES KIDS", 44.00, "Out", "Fashion", "Footwear"),
        ("NEXT DIRECT HOME & CLOTHES", 58.00, "Out", "Fashion", "Clothing"),
        ("PRIMARK UXBRIDGE", 22.50, "Out", "Fashion", "Clothing"),
        ("WATERSTONES CHILDRENS BOOKS", 14.99, "Out", "Education", "Books"),
        ("SMITHS TOYS SUPERSTORE", 29.99, "Out", "Gifts", "Toys & Games"),
        ("CURRYS PC WORLD", 89.99, "Out", "Electronics", "Home Appliances"),
        ("DOMINOS PIZZA FAMILY DEAL", 28.99, "Out", "Takeaway", "Pizza Delivery"),
        ("PAPA JOHNS PIZZA", 24.50, "Out", "Takeaway", "Pizza Delivery"),
        ("JUST EAT CURRY TAKEAWAY", 26.00, "Out", "Takeaway", "Food Delivery"),
        ("UBER EATS CHINESE", 29.50, "Out", "Takeaway", "Food Delivery"),
        ("ESSO PETROL STATION", 42.00, "Out", "Fuel", "Petrol"),
        ("SHELL OIL FORECOURT", 46.00, "Out", "Fuel", "Petrol"),
        ("BP CONNECT PETROL", 41.50, "Out", "Fuel", "Petrol"),
        ("NCP CAR PARK BRISTOL", 12.00, "Out", "Parking", "Parking Charges"),
        ("PAYBYPHONE PARKING METERS", 4.50, "Out", "Parking", "Parking Charges"),
        ("RINGGO PARKING VALET", 5.00, "Out", "Parking", "Parking Charges"),
        ("TRAINLINE FAMILY TICKET", 42.00, "Out", "Transport", "Rail Travel"),
        ("GREAT WESTERN RAILWAY", 36.50, "Out", "Transport", "Rail Travel"),
        ("NATIONAL EXPRESS COACH", 18.00, "Out", "Transport", "Coach Travel"),
        ("AA BREAKDOWN COVER DIRECT DEBIT", 14.99, "Out", "Motoring", "Breakdown Cover"),
        ("RAC ROADSIDE RESCUE", 16.50, "Out", "Motoring", "Breakdown Cover"),
        ("APPLE ICLOUD STORAGE 200GB", 2.99, "Out", "Software", "Cloud Storage"),
        ("MICROSOFT 365 FAMILY SUB", 7.99, "Out", "Software", "Productivity Software"),
        ("AMAZON PRIME VIDEO", 8.99, "Out", "Streaming", "Video Streaming"),
        ("DISNEY PLUS UK", 7.99, "Out", "Streaming", "Video Streaming"),
        ("NETFLIX STANDARD UK", 10.99, "Out", "Streaming", "Video Streaming"),
        ("SPOTIFY FAMILY PLAN", 17.99, "Out", "Streaming", "Music Streaming"),
        ("OXFAM CHARITY SHOP", 8.50, "Out", "Charity", "Charity Shop"),
        ("BARNARDO'S DONATION", 10.00, "Out", "Charity", "Donation"),
        ("LOCAL DRY CLEANERS", 18.00, "Out", "Services", "Dry Cleaning"),
        ("SHOE ZONE REPAIRS", 9.50, "Out", "Services", "Repairs"),
        ("PHOTO-ME BOOTH PASSPORT", 11.00, "Out", "Services", "Photography"),
        ("ODEON CINEMA TICKETS", 24.00, "Out", "Entertainment", "Cinema"),
        ("VUE CINEMA TICKETS", 19.50, "Out", "Entertainment", "Cinema"),
        ("NATIONAL TRUST MEMBERSHIP", 12.50, "Out", "Entertainment", "Heritage & Days Out"),
        ("ENGLISH HERITAGE VISIT", 14.00, "Out", "Entertainment", "Days Out"),
        ("MCDONALDS DRIVE THRU", 14.50, "Out", "Takeaway", "Fast Food"),
        ("KFC BUCKET MEAL", 18.99, "Out", "Takeaway", "Fast Food"),
        ("SUBWAY SUBS LUNCH", 11.20, "Out", "Takeaway", "Fast Food"),
        ("COSTA COFFEE DRIVE THRU", 7.50, "Out", "Coffee", "Coffee Shop"),
        ("STARBUCKS DRIVE THRU", 8.20, "Out", "Coffee", "Coffee Shop"),
        ("GREGGS PASTIES", 5.40, "Out", "Takeaway", "Bakery"),
        ("BEAUTY SALON MANICURE", 25.00, "Out", "Beauty", "Nails & Beauty"),
        ("HAIR SALON HAIRCUT & COLOUR", 45.00, "Out", "Beauty", "Hair Salon"),
        ("PUREGYM FAMILY ACCESS", 39.99, "Out", "Fitness", "Gym"),
        ("DAVID LLOYD RACQUETS", 85.00, "Out", "Fitness", "Health Club"),
        ("CARD FACTORY BIRTHDAY", 4.50, "Out", "Gifts", "Greeting Cards"),
        ("MOONPIG FLOWERS & CARD", 24.99, "Out", "Gifts", "Flowers & Gifts"),
        ("AMAZON MARKETPLACE GOODS", 31.50, "Out", "Shopping", "Online Retail"),
        ("ARGOS EXTRA UXBRIDGE", 42.00, "Out", "Shopping", "Department Store"),
        ("JOHN LEWIS GIFT VOUCHER", 50.00, "Out", "Shopping", "Department Store"),
        ("TESCO FUEL PETROL", 45.00, "Out", "Fuel", "Petrol"),
        ("ASDA PETROL FORECOURT", 41.20, "Out", "Fuel", "Petrol"),
        ("MORRISONS PETROL STATION", 39.80, "Out", "Fuel", "Petrol"),
        ("ATM CASH LLOYDS BANK", 50.00, "Out", "Cash", "ATM"),
        ("ATM CASH NATWEST BANK", 40.00, "Out", "Cash", "ATM"),
        ("ATM CASH BARCLAYS BANK", 60.00, "Out", "Cash", "ATM"),
        ("BANK GROSS INTEREST PAID", 4.35, "In", "Interest", "Savings Interest"),
        ("NATIONWIDE REWARD CASHBACK", 5.00, "In", "Rewards", "Account Cashback"),
        ("REFUND FROM B&Q STORES", 28.50, "In", "Refunds", "Store Return")
    ]

    day_counter = 1
    for desc, amt, dir_, cat, sub in nationwide_extra[:(100 - len(nationwide_rows))]:
        d_str = f"{(day_counter % 28) + 1:02d}/03/2026"
        day_counter += 1
        nationwide_rows.append({
            "Date": d_str, "Description": desc, "Amount": amt, "Direction": dir_,
            "Cat": cat, "Sub": sub, "Trap": False, "Reason": ""
        })

    # -------------------------------------------------------------
    # 3. NORTHBRIDGE SIDE-HUSTLE ACCOUNT (Jordan Ellis)
    # -------------------------------------------------------------
    northbridge_rows = [
        # Inflows / Revenue & Transfers
        {"Date": "01 Mar 2026", "Description": "CLIENT INVOICE #1042 APEX DESIGN", "Amount": 1850.00, "Direction": "In", "Cat": "Revenue", "Sub": "Client Invoices", "Trap": False, "Reason": ""},
        {"Date": "03 Mar 2026", "Description": "From: Jordan Ellis Barclays", "Amount": 300.00, "Direction": "In", "Cat": "Transfers", "Sub": "Internal Account Transfer", "Trap": True, "Reason": "Matching pair of Barclays Out transfer, internal transfer"},
        {"Date": "04 Mar 2026", "Description": "FREELANCE CONSULTING ACME TECH", "Amount": 920.00, "Direction": "In", "Cat": "Revenue", "Sub": "Freelance Income", "Trap": False, "Reason": ""},
        {"Date": "05 Mar 2026", "Description": "STRIPE PAYMENTS REVENUE TRANSFER", "Amount": 640.50, "Direction": "In", "Cat": "Revenue", "Sub": "Merchant Sales", "Trap": False, "Reason": ""},
        
        # Tax payment Out
        {"Date": "05 Mar 2026", "Description": "HMRC SELF ASSESSMENT TAX PAYMENT", "Amount": 480.00, "Direction": "Out", "Cat": "Tax", "Sub": "Income Tax", "Trap": True, "Reason": "HMRC Outflow is tax payment, NOT salary or benefits"},
        
        # Software tools & Hosting
        {"Date": "06 Mar 2026", "Description": "GITHUB COPILOT & TEAM SUB", "Amount": 21.00, "Direction": "Out", "Cat": "Software", "Sub": "Developer Tools", "Trap": False, "Reason": ""},
        {"Date": "06 Mar 2026", "Description": "AWS EMEA CLOUD COMPUTING", "Amount": 64.20, "Direction": "Out", "Cat": "Software", "Sub": "Cloud Infrastructure", "Trap": False, "Reason": ""},
        {"Date": "07 Mar 2026", "Description": "NOTION LABS TEAM WORKSPACE", "Amount": 15.00, "Direction": "Out", "Cat": "Software", "Sub": "Productivity Software", "Trap": False, "Reason": ""},
        {"Date": "07 Mar 2026", "Description": "VERCEL INC PRO HOSTING", "Amount": 16.50, "Direction": "Out", "Cat": "Software", "Sub": "Cloud Hosting", "Trap": False, "Reason": ""},
        {"Date": "08 Mar 2026", "Description": "ADOBE CREATIVE CLOUD SUITE", "Amount": 54.99, "Direction": "Out", "Cat": "Software", "Sub": "Design Software", "Trap": False, "Reason": ""},
        {"Date": "08 Mar 2026", "Description": "CANVA PRO DESIGN SUBSCRIPTION", "Amount": 10.99, "Direction": "Out", "Cat": "Software", "Sub": "Design Tools", "Trap": False, "Reason": ""},
        {"Date": "09 Mar 2026", "Description": "ENVATO ELEMENTS DIGITAL ASSETS", "Amount": 29.00, "Direction": "Out", "Cat": "Software", "Sub": "Design Assets", "Trap": False, "Reason": ""},
        {"Date": "09 Mar 2026", "Description": "FOCALBOARD APP HOSTING", "Amount": 8.00, "Direction": "Out", "Cat": "Software", "Sub": "Productivity", "Trap": False, "Reason": ""},
        {"Date": "10 Mar 2026", "Description": "CLAUDE AI ANTHROPIC SUBSCRIPTION", "Amount": 18.00, "Direction": "Out", "Cat": "Software", "Sub": "AI Tools", "Trap": False, "Reason": ""},
        {"Date": "10 Mar 2026", "Description": "OPENAI API PLATFORM CREDITS", "Amount": 25.00, "Direction": "Out", "Cat": "Software", "Sub": "AI Infrastructure", "Trap": False, "Reason": ""},

        # Hardware & Office
        {"Date": "11 Mar 2026", "Description": "APPLE STORE REGENT ST MAC ACCESSORY", "Amount": 79.00, "Direction": "Out", "Cat": "Electronics", "Sub": "Computer Hardware", "Trap": False, "Reason": ""},
        {"Date": "11 Mar 2026", "Description": "CURRYS ELECTRONICS MONITORS", "Amount": 149.00, "Direction": "Out", "Cat": "Electronics", "Sub": "Computer Hardware", "Trap": False, "Reason": ""},
        {"Date": "12 Mar 2026", "Description": "AMAZON UK OFFICE SUPPLIES", "Amount": 34.50, "Direction": "Out", "Cat": "Shopping", "Sub": "Office Supplies", "Trap": False, "Reason": ""},
        {"Date": "12 Mar 2026", "Description": "VIKING DIRECT STATIONERY & PAPER", "Amount": 28.00, "Direction": "Out", "Cat": "Shopping", "Sub": "Stationery", "Trap": False, "Reason": ""},

        # Travel & Client Meetings
        {"Date": "13 Mar 2026", "Description": "BRITISH AIRWAYS FLIGHT TO EDINBURGH", "Amount": 135.00, "Direction": "Out", "Cat": "Travel", "Sub": "Flights", "Trap": False, "Reason": ""},
        {"Date": "13 Mar 2026", "Description": "PREMIER INN EDINBURGH CITY", "Amount": 89.00, "Direction": "Out", "Cat": "Travel", "Sub": "Hotels", "Trap": False, "Reason": ""},
        {"Date": "14 Mar 2026", "Description": "AIRBNB UK BUSINESS TRIP STAY", "Amount": 145.00, "Direction": "Out", "Cat": "Travel", "Sub": "Accommodation", "Trap": False, "Reason": ""},
        {"Date": "14 Mar 2026", "Description": "UBER TRIP EDINBURGH AIRPORT", "Amount": 24.50, "Direction": "Out", "Cat": "Taxis", "Sub": "Ride-Hailing", "Trap": False, "Reason": ""},
        {"Date": "15 Mar 2026", "Description": "THE IVY EDINBURGH CLIENT DINNER", "Amount": 92.40, "Direction": "Out", "Cat": "Dining", "Sub": "Business Dining", "Trap": False, "Reason": ""},
        {"Date": "15 Mar 2026", "Description": "COSTA COFFEE AIRPORT TERMINAL", "Amount": 5.40, "Direction": "Out", "Cat": "Coffee", "Sub": "Coffee Shop", "Trap": False, "Reason": ""},

        # International Remittance & Crypto
        {"Date": "16 Mar 2026", "Description": "WISE INTERNATIONAL REMITTANCE", "Amount": 180.00, "Direction": "Out", "Cat": "Remittance", "Sub": "International Transfer", "Trap": True, "Reason": "Wise overseas payment is Remittance, NOT P2P or local transfer"},
        {"Date": "16 Mar 2026", "Description": "WESTERN UNION MONEY TRANSFER", "Amount": 95.00, "Direction": "Out", "Cat": "Remittance", "Sub": "International Remittance", "Trap": True, "Reason": "Western Union overseas payment is Remittance"},
        {"Date": "17 Mar 2026", "Description": "COINBASE CRYPTO INVESTMENT", "Amount": 100.00, "Direction": "Out", "Cat": "Investments", "Sub": "Crypto Trading", "Trap": False, "Reason": ""},
        {"Date": "17 Mar 2026", "Description": "TRADING 212 UK STOCK ISA", "Amount": 150.00, "Direction": "Out", "Cat": "Investments", "Sub": "Stocks & Shares", "Trap": False, "Reason": ""},

        # Telecom & Utilities
        {"Date": "18 Mar 2026", "Description": "VODAFONE BUSINESS BROADBAND", "Amount": 38.00, "Direction": "Out", "Cat": "Broadband", "Sub": "Business Internet", "Trap": False, "Reason": ""},
        {"Date": "18 Mar 2026", "Description": "THREE UK 5G MOBILE SIM", "Amount": 16.00, "Direction": "Out", "Cat": "Mobile", "Sub": "Mobile Contract", "Trap": False, "Reason": ""},
        {"Date": "19 Mar 2026", "Description": "ZONG TELECOM ADH 101", "Amount": 4.50, "Direction": "Out", "Cat": "Mobile", "Sub": "International Roaming", "Trap": True, "Reason": "Zong is a telecom operator, NOT electricity & gas"},

        # Fees
        {"Date": "19 Mar 2026", "Description": "MONTHLY BUSINESS ACCOUNT CHARGE", "Amount": 6.50, "Direction": "Out", "Cat": "Fees", "Sub": "Bank Charges", "Trap": False, "Reason": ""},
        {"Date": "20 Mar 2026", "Description": "INTERNATIONAL PAYMENT FEE", "Amount": 4.00, "Direction": "Out", "Cat": "Fees", "Sub": "Transfer Fee", "Trap": False, "Reason": ""},
        
        # P2P Transfers
        {"Date": "20 Mar 2026", "Description": "To: David Clark (Freelance design)", "Amount": 120.00, "Direction": "Out", "Cat": "Peer-to-Peer", "Sub": "Freelance Subcontractor", "Trap": True, "Reason": "Payment to subcontractor person is Peer-to-Peer"},
        {"Date": "21 Mar 2026", "Description": "From: Claire Wilson (Co-working split)", "Amount": 45.00, "Direction": "In", "Cat": "Peer-to-Peer", "Sub": "Personal Contribution", "Trap": True, "Reason": "Receipt from person is Peer-to-Peer, NOT revenue"},
    ]

    # Additional side-hustle rows up to 100
    northbridge_extra = [
        ("UDEMY BUSINESS COURSE", 14.99, "Out", "Education", "Online Courses"),
        ("COURSERA ANNUAL SPECIALISATION", 39.00, "Out", "Education", "Online Courses"),
        ("AMAZON UK TECH CABLES", 16.50, "Out", "Electronics", "Accessories"),
        ("EBAY UK OFFICE CHAIR", 85.00, "Out", "Home", "Office Furniture"),
        ("IKEA ERGONOMIC DESK", 140.00, "Out", "Home", "Office Furniture"),
        ("POST OFFICE SPECIAL DELIVERY", 8.95, "Out", "Services", "Postal Courier"),
        ("DHL EXPRESS INTERNATIONAL", 24.50, "Out", "Services", "Courier"),
        ("FEDEX UK SHIPPING", 18.00, "Out", "Services", "Shipping"),
        ("TIMPSON KEY CUTTING", 7.50, "Out", "Services", "Keys"),
        ("SNAPPY SNAPS PRINTING & BINDING", 16.00, "Out", "Services", "Printing"),
        ("VISTAPRINT BUSINESS CARDS", 22.00, "Out", "Services", "Marketing Materials"),
        ("GOOGLE WORKSPACE EMAIL", 10.80, "Out", "Software", "Email & Office"),
        ("SLACK TECHNOLOGIES PRO", 12.50, "Out", "Software", "Team Chat"),
        ("ZOOM VIDEO PRO COMMUNICATIONS", 11.99, "Out", "Software", "Video Conferencing"),
        ("CALENDLY PRO SCHEDULING", 9.00, "Out", "Software", "Scheduling"),
        ("MAILCHIMP MARKETING CAMPAIGN", 26.00, "Out", "Software", "Email Marketing"),
        ("WEBFLOW HOSTING & CMS", 24.00, "Out", "Software", "Website Hosting"),
        ("NAMECHEAP DOMAIN RENEWAL", 12.40, "Out", "Software", "Domain Names"),
        ("CLOUDFLARE PRO SUBSCRIPTION", 18.00, "Out", "Software", "Security & CDN"),
        ("FIGMA PROFESSIONAL PLAN", 12.00, "Out", "Software", "Design Collaboration"),
        ("LOOM VIDEO RECORDING PRO", 8.00, "Out", "Software", "Screen Recording"),
        ("MIRO TEAM WHITEBOARD", 8.00, "Out", "Software", "Collaboration"),
        ("ZAPIER AUTOMATION STARTER", 19.99, "Out", "Software", "Workflow Automation"),
        ("1PASSWORD TEAMS PASSWORD MGR", 6.00, "Out", "Software", "Security"),
        ("NORDVPN SECURE CONNECTION", 4.99, "Out", "Software", "VPN Security"),
        ("PRET A MANGER MEETING COFFEE", 7.20, "Out", "Coffee", "Coffee"),
        ("STARBUCKS MEETING COFFEE", 8.50, "Out", "Coffee", "Coffee"),
        ("NERO COFFEE CLIENT CHAT", 6.80, "Out", "Coffee", "Coffee"),
        ("LEON HEALTHY FAST FOOD", 9.50, "Out", "Takeaway", "Lunch"),
        ("WASABI SUSHI BENTO LUNCH", 8.95, "Out", "Takeaway", "Lunch"),
        ("ITSU NOODLE BOWL", 8.45, "Out", "Takeaway", "Lunch"),
        ("HONEST BURGERS SOHO", 16.50, "Out", "Dining", "Dinner"),
        ("PIZZA EXPRESS WORK LUNCH", 19.00, "Out", "Dining", "Lunch"),
        ("BILL'S RESTAURANT CLIENT LUNCH", 24.00, "Out", "Dining", "Business Lunch"),
        ("TRAINLINE MANCHESTER TRAVEL", 68.00, "Out", "Transport", "Train Travel"),
        ("AVANTI WEST COAST FIRST CLASS", 95.00, "Out", "Transport", "Train Travel"),
        ("LNER KINGS CROSS TO LEEDS", 54.00, "Out", "Transport", "Train Travel"),
        ("TFL TRAVEL CHG TUBE", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG TUBE", 3.40, "Out", "Transport", "Public Transit"),
        ("TFL TRAVEL CHG TUBE", 3.40, "Out", "Transport", "Public Transit"),
        ("UBER RIDE SOHO", 14.20, "Out", "Taxis", "Ride-Hailing"),
        ("BOLT RIDE SHOREDITCH", 11.80, "Out", "Taxis", "Ride-Hailing"),
        ("ADDISON LEE CHAUFFEUR", 38.00, "Out", "Taxis", "Executive Minicab"),
        ("EASYJET FLIGHT GLASGOW", 64.00, "Out", "Travel", "Flights"),
        ("RYANAIR DUBLIN FLIGHT", 48.00, "Out", "Travel", "Flights"),
        ("TRAVELODGE MANCHESTER CENTRAL", 62.00, "Out", "Travel", "Hotels"),
        ("HILTON DOUBLETREE LEEDS", 98.00, "Out", "Travel", "Hotels"),
        ("NOVOTEL LONDON EXCEL", 115.00, "Out", "Travel", "Hotels"),
        ("ATM CASH BARCLAYS SHOREDITCH", 40.00, "Out", "Cash", "ATM"),
        ("ATM CASH LINK OXFORD ST", 50.00, "Out", "Cash", "ATM"),
        ("BARCLAYCARD BUSINESS PMT", 150.00, "Out", "Credit Card", "Card Repayment"),
        ("AMEX UK BUSINESS CARD", 220.00, "Out", "Credit Card", "Card Repayment"),
        ("PAYPAL WORKING CAPITAL LOAN", 75.00, "Out", "Loans", "Business Loan"),
        ("STRIPE INVOICE REFUND TO CLIENT", 85.00, "Out", "Refunds", "Client Refund"),
        ("TOPCASHBACK PAYOUT RECEIVED", 18.50, "In", "Rewards", "Cashback Payout"),
        ("BANK GROSS INTEREST RECEIVED", 6.80, "In", "Interest", "Interest"),
        ("CLIENT PAYMENT DELTA MEDIA", 750.00, "In", "Revenue", "Client Invoice"),
        ("FREELANCE EDITING VORTEX", 320.00, "In", "Revenue", "Freelance"),
        ("CONSULTING FEE OMEGA GROUP", 1200.00, "In", "Revenue", "Consulting"),
        ("WORKSHOP TRAINING REVENUE", 450.00, "In", "Revenue", "Workshops"),
        ("AFFILIATE MARKETING REVENUE", 85.00, "In", "Revenue", "Affiliate"),
        ("EBOOK SALES GUMROAD PAYOUT", 114.00, "In", "Revenue", "Digital Sales"),
        ("SPONSORSHIP PODCAST EPISODE", 250.00, "In", "Revenue", "Sponsorship"),
        ("SUBSTACK SUBSCRIPTION PAYOUT", 95.00, "In", "Revenue", "Publishing")
    ]

    day_counter = 1
    for desc, amt, dir_, cat, sub in northbridge_extra[:(100 - len(northbridge_rows))]:
        d_str = f"{(day_counter % 28) + 1:02d} Mar 2026"
        day_counter += 1
        northbridge_rows.append({
            "Date": d_str, "Description": desc, "Amount": amt, "Direction": dir_,
            "Cat": cat, "Sub": sub, "Trap": False, "Reason": ""
        })

    def _distribute_dates(rows, is_slash=False):
        for i, r in enumerate(rows):
            if i < 33:
                day = min(31, max(1, int(round(1 + (i / 32.0) * 30))))
                m_text = "Jan"
                m_slash = "01"
            elif i < 66:
                day = min(28, max(1, int(round(1 + ((i - 33) / 32.0) * 27))))
                m_text = "Feb"
                m_slash = "02"
            else:
                day = min(31, max(1, int(round(1 + ((i - 66) / 33.0) * 30))))
                m_text = "Mar"
                m_slash = "03"
            if is_slash:
                r["Date"] = f"{day:02d}/{m_slash}/2026"
            else:
                r["Date"] = f"{day:02d} {m_text} 2026"

    _distribute_dates(barclays_rows, is_slash=False)
    _distribute_dates(nationwide_rows, is_slash=True)
    _distribute_dates(northbridge_rows, is_slash=False)

    return barclays_rows, nationwide_rows, northbridge_rows



def compute_balances_and_summary(rows, initial_balance=1000.0):
    """
    Computes running balance row by row and calculates total money in and out.
    """
    running = initial_balance
    total_in = 0.0
    total_out = 0.0
    
    enriched = []
    for r in rows:
        amt = float(r["Amount"])
        direction = r["Direction"]
        if direction == "In":
            running = round(running + amt, 2)
            total_in = round(total_in + amt, 2)
        else:
            running = round(running - amt, 2)
            total_out = round(total_out + amt, 2)
            
        row_copy = dict(r)
        row_copy["Running_Balance"] = running
        enriched.append(row_copy)
        
    return enriched, total_in, total_out, running


def generate_all():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, "..", "..", ".."))
    pdfs_dir = os.path.join(project_root, "pdfs")
    fixtures_dir = os.path.join(project_root, "tests", "fixtures", "synthetic")
    
    os.makedirs(pdfs_dir, exist_ok=True)
    os.makedirs(fixtures_dir, exist_ok=True)

    b_rows, n_rows, nb_rows = create_statement_datasets()
    
    # 1. BARCLAYS
    b_enriched, b_in, b_out, b_final = compute_balances_and_summary(b_rows, initial_balance=1500.0)
    b_pdf = render_statement_pdf(
        bank_title="BARCLAYS BANK UK PLC",
        header_lines=[
            "SORT CODE: 20-00-00  ACCOUNT NUMBER: 12345678  STATEMENT 42",
            "NAME: JORDAN ELLIS",
            "ACCOUNT: BARCLAYS BANK CURRENT ACCOUNT"
        ],
        summary_text=f"Total money in: £{b_in:,.2f}  Total money out: £{b_out:,.2f}  Balance: £{b_final:,.2f}",
        column_headers=("Date", "Description", "Money out", "Money in", "Balance"),
        txns_data=b_enriched,
        col_x=(40, 110, 360, 440, 520),
        statement_date="31 Mar 2026"
    )
    b_pdf_path = os.path.join(pdfs_dir, "synthetic_barclays_current.pdf")
    with open(b_pdf_path, "wb") as f:
        f.write(b_pdf)
    print(f"✅ Generated {b_pdf_path} ({len(b_enriched)} txns, In: £{b_in:,.2f}, Out: £{b_out:,.2f})")

    # Truth CSV
    b_truth_path = os.path.join(fixtures_dir, "barclays_current.truth.csv")
    pd.DataFrame(b_enriched).to_csv(b_truth_path, index=False)
    print(f"✅ Saved truth CSV: {b_truth_path}")

    # 2. NATIONWIDE
    n_enriched, n_in, n_out, n_final = compute_balances_and_summary(n_rows, initial_balance=2500.0)
    n_pdf = render_statement_pdf(
        bank_title="NATIONWIDE BUILDING SOCIETY",
        header_lines=[
            "SORT CODE: 07-00-93  ACCOUNT NUMBER: 88776655  STATEMENT 88",
            "NAME: JORDAN ELLIS & ALEX ELLIS (FLEXACCOUNT)",
            "BUILDING SOCIETY BRANCH: HIGH STREET UXBRIDGE"
        ],
        summary_text=f"Payments in: £{n_in:,.2f}  Payments out: £{n_out:,.2f}  Balance: £{n_final:,.2f}",
        column_headers=("Date", "Description", "Withdrawals", "Deposits", "Balance"),
        txns_data=n_enriched,
        col_x=(40, 110, 360, 440, 520),
        statement_date="31/03/2026"
    )
    n_pdf_path = os.path.join(pdfs_dir, "synthetic_nationwide_household.pdf")
    with open(n_pdf_path, "wb") as f:
        f.write(n_pdf)
    print(f"✅ Generated {n_pdf_path} ({len(n_enriched)} txns, In: £{n_in:,.2f}, Out: £{n_out:,.2f})")

    n_truth_path = os.path.join(fixtures_dir, "nationwide_household.truth.csv")
    pd.DataFrame(n_enriched).to_csv(n_truth_path, index=False)
    print(f"✅ Saved truth CSV: {n_truth_path}")

    # 3. NORTHBRIDGE (Generic Bank Statement Signals)
    nb_enriched, nb_in, nb_out, nb_final = compute_balances_and_summary(nb_rows, initial_balance=1200.0)
    nb_pdf = render_statement_pdf(
        bank_title="NORTHBRIDGE COMMERCIAL BANK",
        header_lines=[
            "SORT CODE: 11-22-33  ACCOUNT NUMBER: 99443322  STATEMENT 15",
            "NAME: JORDAN ELLIS T/A ELLIS DIGITAL LABS",
            "COMMERCIAL BANK STATEMENT  CURRENCY: GBP"
        ],
        summary_text=f"Payments in: £{nb_in:,.2f}  Payments out: £{nb_out:,.2f}  Balance: £{nb_final:,.2f}",
        column_headers=("Date", "Details", "Debit", "Credit", "Balance"),
        txns_data=nb_enriched,
        col_x=(40, 110, 360, 440, 520),
        statement_date="31 Mar 2026"
    )
    nb_pdf_path = os.path.join(pdfs_dir, "synthetic_northbridge_sidehustle.pdf")
    with open(nb_pdf_path, "wb") as f:
        f.write(nb_pdf)
    print(f"✅ Generated {nb_pdf_path} ({len(nb_enriched)} txns, In: £{nb_in:,.2f}, Out: £{nb_out:,.2f})")

    nb_truth_path = os.path.join(fixtures_dir, "northbridge_sidehustle.truth.csv")
    pd.DataFrame(nb_enriched).to_csv(nb_truth_path, index=False)
    print(f"✅ Saved truth CSV: {nb_truth_path}")


if __name__ == "__main__":
    generate_all()
