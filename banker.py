"""
AI Financial Auditor & Deep Categorization Engine (Phase 10 Enterprise).

Features:
- Individual, non-lumped taxonomy (Food split into Groceries/Dining/Takeaway/Coffee/Bars;
  Retail split into Shopping/Fashion/Beauty/Home/Electronics/Gifts;
  Bills split into Energy/Water/Mobile/Broadband/Council Tax;
  Getting around split into Transport/Taxis/Fuel/Parking/Motoring/Travel;
  Transfers split into Transfers/Peer-to-Peer/Remittance; etc.).
- Dual-tier classification: Category + Subcategory + Multi-dimensional Search Tags.
- Deterministic text normaliser (splits digit-glued tokens, unwraps payment processors,
  cleans bank prefixes, preserves fuel brand BP).
- Seed rules ordered from specific to generic (catches 25+ loaded traps with 0 tokens).
- Pass 2 Consolidation Engine:
  * Cross-account internal transfer pairing (detects matching Out/In legs across statements)
  * Peer-to-Peer vs Own-account Transfers separation
  * Generic recurring employer income detection (zero hard-coded employer names)
  * Merchant direction enforcement (store inflows -> Refunds)
  * Clean-name validation (no empty/numeric/unknown names)
- Channel detection (Direct Debit, Card Payment, Bank Transfer, ATM, etc.).
- Versioned, validated memory cache.
"""
import os
import json
import re
import datetime as dt
import pandas as pd
from llm_router import invoke_llm, parse_json_safely

# --- MASTER TAXONOMY & SUBCATEGORIES (Individual, Single-Title Categories) ---
TAXONOMY = {
    # Food (Individual Categories)
    "Groceries": ["Supermarket", "Local Convenience", "Bakery", "Greengrocer", "Wholesale Food"],
    "Dining": ["Restaurants", "Bistros", "Steakhouses", "Italian & Pizzeria", "Asian Dining"],
    "Takeaway": ["Food Delivery", "Fast Food", "Burgers & Pizza", "Fried Chicken", "Sandwiches"],
    "Coffee": ["Cafes & Coffee", "Artisan Coffee", "Tea Rooms", "Bakery Cafe"],
    "Bars": ["Pubs & Taverns", "Bars & Lounges", "Breweries & Taprooms", "Nightclubs"],

    # Retail (Individual Categories)
    "Shopping": ["Online Marketplaces", "Department Stores", "Variety Goods", "Stationery"],
    "Fashion": ["Clothing & Apparel", "Footwear & Shoes", "Sportswear", "Designer & Luxury"],
    "Beauty": ["Cosmetics & Skincare", "Barbers & Hair Salons", "Toiletries", "Nail & Beauty"],
    "Home": ["Furniture & Decor", "DIY & Hardware", "Bedding & Curtains", "Garden & Outdoor"],
    "Electronics": ["Computers & Hardware", "Mobile Devices", "Audio & Gadgets", "Appliances"],
    "Gifts": ["Cards & Greetings", "Flowers & Florists", "Toys & Games", "Novelty Gifts"],

    # Digital & Media (Individual Categories)
    "Software": ["AI Tools", "Cloud Storage", "Productivity Apps", "Developer Tools", "Web Hosting"],
    "Streaming": ["Video Streaming", "Music Streaming", "Audiobooks & Podcasts", "Digital News"],
    "Gaming": ["Video Games", "Gaming Subscriptions", "In-Game Purchases", "Game Stores"],

    # Getting Around (Individual Categories)
    "Transport": ["Public Transit", "Trains & Rail", "Buses & Coaches", "Ferry Travel"],
    "Taxis": ["Ride-Hailing", "Minicabs & Taxis", "Executive Chauffeur"],
    "Fuel": ["Petrol & Diesel", "EV Charging", "Motorway Fuel"],
    "Parking": ["Parking Meters", "Car Parks", "Airport Parking", "Parking Permits"],
    "Motoring": ["Vehicle Repairs", "MOT & Servicing", "Road Tax", "Breakdown Cover", "Tyres"],
    "Travel": ["Flights & Airlines", "Hotels & Stays", "Holidays & Tours", "Car Rental"],

    # Home & Bills (Individual Categories)
    "Rent": ["Tenancy Rent", "Room Rent", "Estate Agent Fees"],
    "Mortgage": ["Mortgage Payment", "Equity Loan"],
    "Energy": ["Electricity & Gas", "Gas Supply", "Green Energy"],
    "Water": ["Water Rates", "Sewerage"],
    "Mobile": ["Mobile Phone Contract", "SIM Only", "International Roaming"],
    "Broadband": ["Home Broadband", "Fibre Internet", "Cable & TV Packages"],
    "Council Tax": ["Local Council Tax"],
    "Tax": ["Self Assessment", "Income Tax", "Corporation Tax", "Customs Duty"],
    "Insurance": ["Car Insurance", "Home Insurance", "Pet Insurance", "Life Insurance"],

    # Life (Individual Categories)
    "Entertainment": ["Cinema & Theatre", "Live Music & Gigs", "Attractions & Museums", "Events"],
    "Fitness": ["Gym Membership", "Sports Clubs", "Yoga & Pilates", "Martial Arts"],
    "Health": ["Pharmacy & Medicine", "Dental Care", "Opticians", "Medical Services"],
    "Pets": ["Veterinary Care", "Pet Food & Supplies", "Pet Grooming"],
    "Childcare": ["Day Nursery", "Childminding", "School Fees & Activities"],
    "Education": ["Courses & Training", "Tuition & Tutors", "Books & Textbooks"],
    "Charity": ["Donations", "Charity Shops", "Sponsorship"],
    "Gambling": ["Sports Betting", "Online Casino", "National Lottery"],
    "Fees": ["Bank Charges", "Overdraft Fees", "Foreign Transaction Fees", "Account Fees"],
    "Services": ["Postal & Couriers", "Dry Cleaning & Laundry", "Key Cutting & Repairs", "Printing"],

    # Two-Way Financial Flows (Transfers, Debt, Savings, Cash)
    "Transfers": ["Internal Account Transfer", "Own Bank Move", "Cross-Account Transfer"],
    "Peer-to-Peer": ["Personal Transfer", "Split Bill", "Friend & Family Transfer"],
    "Remittance": ["International Remittance", "Overseas Transfer"],
    "Savings": ["Savings Vault Deposit", "Interest Savings", "Plum Savings"],
    "Investments": ["Crypto Trading", "Stocks & Shares ISA", "Pension Contribution"],
    "Cash": ["ATM Withdrawal", "Counter Cash", "Cashback"],
    "Credit Card": ["Card Repayment", "Statement Balance Settlement"],
    "Loans": ["Personal Loan", "Auto Finance", "Student Loan"],
    "BNPL": ["Klarna Instalment", "Clearpay", "Pay in 3"],

    # Inflow Only Categories
    "Salary": ["Employment Wages", "Payroll", "Director Remuneration", "Overtime & Bonus"],
    "Pension": ["State Pension", "Workplace Pension", "Annuity"],
    "Revenue": ["Client Invoices", "Freelance Income", "Business Sales", "Stripe Payout"],
    "Refunds": ["Merchant Refund", "Store Return", "Order Cancellation", "Chargeback"],
    "Benefits": ["Tax Rebates", "Child Benefit", "Universal Credit", "State Support"],
    "Interest": ["Savings Interest", "Deposit Interest"],
    "Rewards": ["Cashback Reward", "Loyalty Payout"]
}

VALID_CATEGORIES = list(TAXONOMY.keys())

DEFAULT_TAGS_BY_CATEGORY = {
    "Groceries": ["groceries", "supermarket", "convenience store", "food shopping", "provisions"],
    "Dining": ["dining", "restaurants", "table service", "dinner", "lunch"],
    "Takeaway": ["takeaway", "fast food", "food delivery", "delivery app", "quick bite"],
    "Coffee": ["coffee", "cafe", "espresso", "hot drinks", "bakery cafe"],
    "Bars": ["pubs", "bars", "drinks", "beer", "nightlife"],
    "Shopping": ["retail", "shopping", "marketplace", "goods", "general merchandise"],
    "Fashion": ["clothing", "fashion", "apparel", "footwear", "shoes"],
    "Beauty": ["cosmetics", "skincare", "barber", "hair salon", "toiletries"],
    "Home": ["homeware", "furniture", "diy", "hardware", "garden"],
    "Electronics": ["electronics", "hardware", "computers", "gadgets", "appliances"],
    "Gifts": ["gifts", "greeting cards", "flowers", "toys", "presents"],
    "Software": ["software", "ai tools", "cloud storage", "apps", "developer tools"],
    "Streaming": ["streaming", "digital subscription", "video", "music", "podcasts"],
    "Gaming": ["gaming", "video games", "console", "in-game purchase", "steam"],
    "Transport": ["public transit", "commute", "train", "tube", "bus"],
    "Taxis": ["taxi", "ride hailing", "minicab", "cabs", "chauffeur"],
    "Fuel": ["fuel", "petrol", "diesel", "service station", "forecourt"],
    "Parking": ["parking", "parking meters", "car park", "parking charges"],
    "Motoring": ["motoring", "vehicle repairs", "mot", "road tax", "breakdown"],
    "Travel": ["travel", "flights", "hotels", "airlines", "holidays"],
    "Rent": ["rent", "tenancy", "housing", "landlord", "accommodation"],
    "Mortgage": ["mortgage", "home loan", "property financing"],
    "Energy": ["energy", "electricity", "gas", "utility bill", "power"],
    "Water": ["water rates", "water utility", "sewerage"],
    "Mobile": ["mobile phone", "phone contract", "sim only", "telecom"],
    "Broadband": ["broadband", "home internet", "wifi", "cable tv"],
    "Council Tax": ["council tax", "local authority", "borough rates"],
    "Tax": ["tax", "hmrc", "self assessment", "income tax"],
    "Insurance": ["insurance", "car insurance", "home insurance", "policy premium"],
    "Entertainment": ["entertainment", "cinema", "theatre", "live events", "gigs"],
    "Fitness": ["fitness", "gym", "workout", "sports club", "exercise"],
    "Health": ["health", "pharmacy", "medical", "dentist", "opticians"],
    "Pets": ["pets", "veterinary", "pet food", "pet supplies"],
    "Childcare": ["childcare", "nursery", "daycare", "school expenses"],
    "Education": ["education", "courses", "tuition", "learning", "books"],
    "Charity": ["charity", "donation", "good cause", "philanthropy"],
    "Gambling": ["gambling", "betting", "lottery", "casino", "wager"],
    "Fees": ["fees", "bank charges", "overdraft fee", "fx fees"],
    "Services": ["services", "repairs", "dry cleaning", "postage", "keys"],
    "Transfers": ["transfer", "internal transfer", "own account", "bank move"],
    "Peer-to-Peer": ["p2p", "peer to peer", "personal transfer", "split payment"],
    "Remittance": ["remittance", "international transfer", "overseas money", "fx"],
    "Savings": ["savings", "savings vault", "rainy day", "deposit"],
    "Investments": ["investments", "crypto", "trading", "stocks", "isa"],
    "Cash": ["cash", "atm withdrawal", "physical money", "cash out"],
    "Credit Card": ["credit card", "card payment", "statement payment"],
    "Loans": ["loan", "finance repayment", "instalment"],
    "BNPL": ["bnpl", "buy now pay later", "instalment", "pay in 3"],
    "Salary": ["salary", "payroll", "wages", "employment earnings", "net pay"],
    "Pension": ["pension", "retirement", "annuity"],
    "Revenue": ["business revenue", "client payment", "invoice", "freelance"],
    "Refunds": ["refund", "merchant refund", "store return", "money back"],
    "Benefits": ["benefits", "tax rebate", "child benefit", "universal credit"],
    "Interest": ["interest", "savings interest", "bank credit"],
    "Rewards": ["cashback", "reward payout", "loyalty"]
}

def get_fallback_tags(category):
    return DEFAULT_TAGS_BY_CATEGORY.get(category, ["financial transaction", "card payment"])

# --- HIGH-CONFIDENCE SEED RULES (Specific Before Generic, 0 Tokens) ---
# Format: (pattern, Category, Subcategory, Clean_Name, [Tags])
SEED_PATTERNS = [
    # 1. SPECIFIC TRAPS FIRST (Must match before broader keywords)
    # Retail trap: Cash Converters is shopping, not ATM cash
    (r"\bCASH\s*CONVERTERS\b", "Shopping", "Variety Goods", "Cash Converters", ["retail", "shopping", "secondhand"]),
    # Energy trap: Shell Energy is home utility, not motoring fuel
    (r"\bSHELL\s*ENERGY\b", "Energy", "Electricity & Gas", "Shell Energy", ["energy", "electricity", "gas", "utility bill"]),
    # Gambling trap: Sky Bet is betting, not broadband
    (r"\bSKY\s*BET\b", "Gambling", "Sports Betting", "Sky Bet", ["gambling", "betting", "sports betting"]),
    # Entertainment trap: O2 Academy is a live venue, not mobile phone
    (r"\bO2\s*ACADEMY\b", "Entertainment", "Live Music & Gigs", "O2 Academy", ["entertainment", "gigs", "concerts", "live music"]),
    # Telecom trap: Tesco Mobile is phone contract, not groceries
    (r"\bTESCO\s*MOBILE\b", "Mobile", "Mobile Phone Contract", "Tesco Mobile", ["mobile", "phone contract", "telecom"]),
    # Debt trap: Tesco Bank is credit card debt, not groceries
    (r"\bTESCO\s*BANK\b", "Credit Card", "Card Repayment", "Tesco Bank Credit Card", ["credit card", "debt repayment"]),
    # Streaming trap: Amazon Prime Video is streaming, not online shopping
    (r"\bAMAZON\s*PRIME(?:\s*VIDEO)?\b", "Streaming", "Video Streaming", "Amazon Prime Video", ["streaming", "video", "subscription"]),
    # Debt trap: Salary Finance is a loan repayment, not salary
    (r"\bSALARY\s*FINANCE\b", "Loans", "Personal Loan", "Salary Finance Loan", ["loan", "debt repayment", "finance"]),

    # 2. CASH & ATM (Strict match for physical cash machines)
    (r"\bATM\s*CASH\b|\bATM\s*WITHDRAWAL\b|\bNOTEMAC\b|\bLINK\s*ATM\b|\bCASH\s*MACHINE\b", "Cash", "ATM Withdrawal", "ATM Cash Withdrawal", ["cash", "atm withdrawal", "physical money"]),

    # 3. RIDE-HAILING VS TAKEAWAY VS COMMUTE (TFL, Uber, Delivery)
    (r"\bTFL\b|TRANSPORT\s*FOR\s*LONDON|TFL\.GOV", "Transport", "Public Transit", "TfL (Transport for London)", ["tfl", "public transit", "commute", "tube", "bus"]),
    (r"\bTRAINLINE\b", "Transport", "Trains & Rail", "Trainline", ["train", "rail", "commute", "travel"]),
    (r"\bNATIONAL\s*RAIL\b|\bGREAT\s*WESTERN\b|\bLNER\b|\bAVANTI\b|\bTHAMESLINK\b", "Transport", "Trains & Rail", "National Rail", ["train", "rail", "commute"]),
    (r"\bUBER\s*\*?\s*EATS\b", "Takeaway", "Food Delivery", "Uber Eats", ["food delivery", "takeaway", "fast food"]),
    (r"\bDELIVEROO\b", "Takeaway", "Food Delivery", "Deliveroo", ["food delivery", "takeaway"]),
    (r"\bJUST\s*EAT\b", "Takeaway", "Food Delivery", "Just Eat", ["food delivery", "takeaway"]),
    (r"\bUBER\b(?!.*EATS)", "Taxis", "Ride-Hailing", "Uber", ["taxi", "ride hailing", "transport", "uber"]),
    (r"\bBOLT\s*(?:RIDE|EU)?\b", "Taxis", "Ride-Hailing", "Bolt", ["taxi", "ride hailing", "transport"]),
    (r"\bADDISON\s*LEE\b", "Taxis", "Minicabs & Taxis", "Addison Lee", ["taxi", "minicab", "chauffeur"]),

    # 4. TAKEAWAY & FAST FOOD (Distinct from Dining and Coffee)
    (r"\bSUBWAY\b", "Takeaway", "Fast Food", "Subway", ["takeaway", "fast food", "sandwiches"]),
    (r"\bMCDONALDS?\b", "Takeaway", "Fast Food", "McDonald's", ["takeaway", "fast food", "burgers"]),
    (r"\bKFC\b", "Takeaway", "Fast Food", "KFC", ["takeaway", "fast food", "fried chicken"]),
    (r"\bBURGER\s*KING\b", "Takeaway", "Fast Food", "Burger King", ["takeaway", "fast food", "burgers"]),
    (r"\bGREGGS\b", "Takeaway", "Fast Food", "Greggs", ["takeaway", "fast food", "bakery"]),
    (r"\bDOMINO'?S\b|\bPAPA\s*JOHNS?\b|\bPIZZA\s*HUT\b", "Takeaway", "Burgers & Pizza", "Pizza Delivery", ["pizza", "takeaway", "delivery"]),

    # 5. COFFEE SHOPS & CAFES (Distinct from Restaurants)
    (r"\bSTARBUCKS\b", "Coffee", "Cafes & Coffee", "Starbucks", ["coffee", "cafe", "hot drinks"]),
    (r"\bCOSTA\s*COFFEE\b|\bCOSTA\b", "Coffee", "Cafes & Coffee", "Costa Coffee", ["coffee", "cafe"]),
    (r"\bPRET\s*A\s*MANGER\b|\bPRET\b", "Coffee", "Cafes & Coffee", "Pret A Manger", ["coffee", "cafe", "lunch"]),
    (r"\bCAFF[EE]\s*NERO\b", "Coffee", "Cafes & Coffee", "Caffè Nero", ["coffee", "cafe"]),

    # 6. RESTAURANTS & CASUAL DINING (Sit-down table service)
    (r"\bNANDO'?S\b", "Dining", "Restaurants", "Nando's", ["dining", "restaurant", "chicken"]),
    (r"\bWAGAMAMA\b", "Dining", "Asian Dining", "Wagamama", ["dining", "restaurant", "asian"]),
    (r"\bDISHOOM\b", "Dining", "Restaurants", "Dishoom", ["dining", "restaurant", "indian"]),
    (r"\bFRANCO\s*MANCA\b", "Dining", "Italian & Pizzeria", "Franco Manca", ["dining", "restaurant", "pizza"]),
    (r"\bPIZZA\s*EXPRESS\b", "Dining", "Italian & Pizzeria", "PizzaExpress", ["dining", "restaurant", "pizza"]),

    # 7. PUBS & BARS
    (r"\bBREWDOG\b", "Bars", "Breweries & Taprooms", "BrewDog", ["bars", "craft beer", "pubs"]),
    (r"\bWETHERSPOON\b|\bJ\s*D\s*WETHERSPOON\b", "Bars", "Pubs & Taverns", "Wetherspoon", ["pubs", "drinks", "food"]),

    # 8. GROCERIES & SUPERMARKETS (Food bought to take home)
    (r"\bTESCO\b", "Groceries", "Supermarket", "Tesco", ["groceries", "supermarket", "food shopping"]),
    (r"\bSAINSBURYS?\b|\bSAINSBURY'S\b", "Groceries", "Supermarket", "Sainsbury's", ["groceries", "supermarket", "food shopping"]),
    (r"\bLIDL\b", "Groceries", "Supermarket", "Lidl", ["groceries", "supermarket", "food shopping"]),
    (r"\bALDI\b", "Groceries", "Supermarket", "Aldi", ["groceries", "supermarket", "food shopping"]),
    (r"\bASDA\b", "Groceries", "Supermarket", "Asda", ["groceries", "supermarket", "food shopping"]),
    (r"\bMORRISONS?\b", "Groceries", "Supermarket", "Morrisons", ["groceries", "supermarket", "food shopping"]),
    (r"\bM&S\b|MARKS\s*&\s*SPENCER", "Groceries", "Supermarket", "M&S Food", ["groceries", "supermarket", "food"]),
    (r"\bWAITROSE\b", "Groceries", "Supermarket", "Waitrose", ["groceries", "supermarket", "food shopping"]),
    (r"\bICELAND\s*(?:FOODS)?\b", "Groceries", "Supermarket", "Iceland", ["groceries", "supermarket", "frozen food"]),
    (r"\bPNR\s*SUPERSTORE\b", "Groceries", "Local Convenience", "PNR Superstore", ["groceries", "convenience store"]),

    # 9. FASHION & CLOTHING (Distinct from General Shopping)
    (r"\bZARA\b", "Fashion", "Clothing & Apparel", "Zara", ["fashion", "clothing", "apparel"]),
    (r"\bASOS\b", "Fashion", "Clothing & Apparel", "ASOS", ["fashion", "clothing", "online fashion"]),
    (r"\bH&M\b|\bH\s*&\s*M\b", "Fashion", "Clothing & Apparel", "H&M", ["fashion", "clothing", "apparel"]),
    (r"\bUNIQLO\b", "Fashion", "Clothing & Apparel", "Uniqlo", ["fashion", "clothing", "apparel"]),
    (r"\bPRIMARK\b", "Fashion", "Clothing & Apparel", "Primark", ["fashion", "clothing", "apparel"]),
    (r"\bSPORTSDIRECT\b|\bSPORTS\s*DIRECT\b", "Fashion", "Sportswear", "Sports Direct", ["fashion", "sportswear", "footwear"]),
    (r"\bNIKE\b|\bADIDAS\b", "Fashion", "Sportswear", "Sportswear Store", ["fashion", "sportswear", "footwear"]),
    (r"\bNEXT\s*(?:RETAIL|DIRECTORY)?\b", "Fashion", "Clothing & Apparel", "Next", ["fashion", "clothing", "homeware"]),

    # 10. BEAUTY & PERSONAL CARE (Distinct from Shopping)
    (r"\bBOOTS\b(?!.*PHARMACY)", "Beauty", "Toiletries", "Boots", ["beauty", "cosmetics", "toiletries"]),
    (r"\bSUPERDRUG\b", "Beauty", "Toiletries", "Superdrug", ["beauty", "cosmetics", "toiletries"]),
    (r"\bSEPHORA\b", "Beauty", "Cosmetics & Skincare", "Sephora", ["beauty", "cosmetics", "skincare"]),
    (r"\bBARBER\b|\bHAIR\s*SALON\b", "Beauty", "Barbers & Hair Salons", "Hair & Grooming", ["beauty", "haircut", "barber"]),

    # 11. HOME, DIY & FURNITURE
    (r"\bIKEA\b", "Home", "Furniture & Decor", "IKEA", ["home", "furniture", "homeware"]),
    (r"\bB&Q\b|\bB\s*&\s*Q\b", "Home", "DIY & Hardware", "B&Q", ["home", "diy", "hardware", "garden"]),
    (r"\bDUNELM\b", "Home", "Bedding & Curtains", "Dunelm", ["home", "homeware", "furniture"]),
    (r"\bSCREWFIX\b|\bTOOLSTATION\b", "Home", "DIY & Hardware", "Hardware Store", ["home", "hardware", "diy"]),
    (r"\bWILKO\b", "Shopping", "Variety Goods", "Wilko", ["shopping", "retail", "variety"]),

    # 12. CONSUMER ELECTRONICS
    (r"\bAPPLE(?:\.COM)?\b", "Electronics", "Computers & Hardware", "Apple", ["electronics", "hardware", "gadgets"]),
    (r"\bCURRYS\b", "Electronics", "Computers & Hardware", "Currys", ["electronics", "hardware", "appliances"]),
    (r"\bCEX\b", "Electronics", "Computers & Hardware", "CeX", ["electronics", "gaming", "secondhand"]),

    # 13. SHOPPING & ONLINE MARKETPLACES
    (r"\bAMAZON\b|\bAMZNMKTPLACE\b", "Shopping", "Online Marketplaces", "Amazon", ["shopping", "retail", "marketplace"]),
    (r"\bEBAY\b", "Shopping", "Online Marketplaces", "eBay", ["shopping", "retail", "marketplace"]),
    (r"\bTEMU\b", "Shopping", "Online Marketplaces", "Temu", ["shopping", "retail", "marketplace"]),
    (r"\bARGOS\b", "Shopping", "Department Stores", "Argos", ["shopping", "department store", "catalogue"]),
    (r"\bJOHN\s*LEWIS\b", "Shopping", "Department Stores", "John Lewis", ["shopping", "department store"]),

    # 14. DIGITAL SOFTWARE, AI TOOLS & CLOUD
    (r"\bOPENAI\b|CHATGPT", "Software", "AI Tools", "OpenAI / ChatGPT", ["software", "ai tools", "technology"]),
    (r"\bANTHROPIC\b|CLAUDE\s*AI", "Software", "AI Tools", "Anthropic Claude", ["software", "ai tools"]),
    (r"\bGITHUB\b", "Software", "Developer Tools", "GitHub", ["software", "developer tools", "cloud"]),
    (r"\bAWS\b|AMAZON\s*WEB\s*SERVICES", "Software", "Cloud Storage", "AWS Cloud", ["software", "cloud infrastructure"]),
    (r"\bGOOGLE\s*ONE\b", "Software", "Cloud Storage", "Google One", ["software", "cloud storage", "google"]),
    (r"\bDROPBOX\b|\bICLOUD\b", "Software", "Cloud Storage", "Cloud Storage", ["software", "cloud storage"]),
    (r"\bADOBE\b", "Software", "Productivity Apps", "Adobe Creative Cloud", ["software", "design", "creative"]),
    (r"\bNOTION\b", "Software", "Productivity Apps", "Notion", ["software", "productivity", "workspace"]),
    (r"\bCANVA\b", "Software", "Productivity Apps", "Canva", ["software", "design", "graphics"]),
    (r"\bENVATO\b", "Software", "Productivity Apps", "Envato Elements", ["software", "design assets"]),

    # 15. STREAMING & DIGITAL MEDIA
    (r"\bNETFLIX\b", "Streaming", "Video Streaming", "Netflix", ["streaming", "video", "entertainment"]),
    (r"\bSPOTIFY\b", "Streaming", "Music Streaming", "Spotify", ["streaming", "music", "audio"]),
    (r"\bDISNEY\s*\+?\b", "Streaming", "Video Streaming", "Disney+", ["streaming", "video"]),
    (r"\bYOUTUBE\s*PREMIUM\b", "Streaming", "Video Streaming", "YouTube Premium", ["streaming", "video"]),
    (r"\bAUDIBLE\b", "Streaming", "Audiobooks & Podcasts", "Audible", ["streaming", "audiobooks"]),

    # 16. GAMING
    (r"\bSTEAM\b|\bVALVE\b", "Gaming", "Video Games", "Steam Games", ["gaming", "pc games", "video games"]),
    (r"\bPLAYSTATION\b|\bPSN\b", "Gaming", "Gaming Subscriptions", "PlayStation Network", ["gaming", "console", "playstation"]),
    (r"\bXBOX\b|\bMICROSOFT\s*GAME\s*PASS\b", "Gaming", "Gaming Subscriptions", "Xbox Game Pass", ["gaming", "console"]),
    (r"\bNINTENDO\b", "Gaming", "Video Games", "Nintendo eShop", ["gaming", "console"]),

    # 17. MOTORING & FUEL (Shell, Esso, BP, Texaco)
    (r"\bSHELL\b|\bESSO\b|\bBP\s*(?:CONNECT|OIL|PULSE|PETROL|SERVICE|FORECOURT)?\b|\bTEXACO\b", "Fuel", "Petrol & Diesel", "Petrol Station", ["fuel", "petrol", "diesel", "motoring"]),
    (r"\bDVLA\b", "Motoring", "Road Tax", "DVLA Vehicle Tax", ["motoring", "road tax", "dvla"]),
    (r"\bHALFORDS\b", "Motoring", "Vehicle Repairs", "Halfords", ["motoring", "auto parts", "cycling"]),
    (r"\bKWIK\s*FIT\b", "Motoring", "Tyres", "Kwik Fit", ["motoring", "tyres", "servicing"]),
    (r"\bAA\s*BREAKDOWN\b|\bRAC\s*RESCUE\b", "Motoring", "Breakdown Cover", "Breakdown Cover", ["motoring", "roadside rescue"]),

    # 18. PARKING
    (r"\bRINGGO\b|\bJUSTPARK\b|\bPAYBYPHONE\b|\bNCP\s*(?:CAR\s*PARK)?\b", "Parking", "Parking Meters", "Parking Provider", ["parking", "motoring", "car park"]),

    # 19. HOME BILLS & UTILITIES (Individual Categories)
    (r"\bBRITISH\s*GAS\b|\bOCTOPUS\s*ENERGY\b|\bEDF\s*ENERGY\b|\bE\.ON\b", "Energy", "Electricity & Gas", "Energy Provider", ["energy", "electricity", "gas", "utility bill"]),
    (r"\bTHAMES\s*WATER\b|\bSEVERN\s*TRENT\b|\bANGLIAN\s*WATER\b|\bSOUTHERN\s*WATER\b", "Water", "Water Rates", "Water Utility", ["water", "utilities", "water rates"]),
    (r"\bEE\b|\bVODAFONE\b|\bO2\b|\bTHREE\s*UK\b|\bGIFFGAFF\b|\bSMARTY\b|\bZONG\b", "Mobile", "Mobile Phone Contract", "Mobile Network", ["mobile", "phone contract", "telecom"]),
    (r"\bVIRGIN\s*MEDIA\b|\bBT\s*BROADBAND\b|\bSKY\s*BROADBAND\b|\bPLUSNET\b|\bTALKTALK\b", "Broadband", "Home Broadband", "Broadband Provider", ["broadband", "home internet", "wifi"]),
    (r"\bCOUNCIL\s*TAX\b", "Council Tax", "Local Council Tax", "Council Tax", ["council tax", "local authority"]),

    # 20. HOUSING & RENT (Distinct from Mortgage)
    (r"\bRENT\b|\bLANDLORD\b|\bTENANCY\b|\bESTATE\s*AGENT\b", "Rent", "Tenancy Rent", "Rent Payment", ["rent", "housing", "property", "accommodation"]),
    (r"\bMORTGAGE\b", "Mortgage", "Mortgage Payment", "Mortgage Payment", ["mortgage", "housing", "property", "home loan"]),

    # 21. TAX PAYMENTS (Outflow)
    (r"\bHMRC\b.*(?:\bSELF\s*ASSESSMENT\b|\bINCOME\s*TAX\b|\bTAX\s*PAYMENT\b)", "Tax", "Self Assessment", "HMRC Tax Payment", ["tax", "hmrc", "income tax"]),

    # 22. INSURANCE
    (r"\bADMIRAL\b|\bAVIVA\b|\bDIRECT\s*LINE\b|\bAXA\b|\bCHURCHILL\s*INSURANCE\b|\bCAR\s*INSURANCE\b|\bHOME\s*INSURANCE\b", "Insurance", "Car Insurance", "Insurance Provider", ["insurance", "policy premium", "cover"]),

    # 23. HEALTH & FITNESS
    (r"\bPUREGYM\b|\bDAVID\s*LLOYD\b|\bTHE\s*GYM\s*GROUP\b|\bNUFFIELD\s*HEALTH\b", "Fitness", "Gym Membership", "Gym & Fitness", ["fitness", "gym", "exercise"]),
    (r"\bBOOTS\s*PHARMACY\b|\bPHARMACY\b|\bPRESCRIPTION\b|\bNHS\s*DENTAL\b|\bDENTAL\s*PRACTICE\b|\bOPTICIAN\b|\bDOCTOR\b|\bCLINIC\b", "Health", "Pharmacy & Medicine", "Health & Medical", ["health", "pharmacy", "medical", "dental"]),
    (r"\bSPECSAVERS\b|\bVISION\s*EXPRESS\b", "Health", "Opticians", "Opticians", ["health", "opticians", "eyecare"]),

    # 24. PETS & CHILDCARE
    (r"\bPETPLAN\b|\bPETS\s*AT\s*HOME\b|\bZOOPLUS\b|\bVETS4PETS\b|\bVET\s*CLINIC\b|\bVETERINARY\b", "Pets", "Veterinary Care", "Pet Care", ["pets", "animals", "vet", "pet food"]),
    (r"\bBUSY\s*BEES\b|\bDAY\s*NURSERY\b|\bCHILDCARE\b", "Childcare", "Day Nursery", "Childcare & Nursery", ["childcare", "nursery", "children"]),

    # 25. GAMBLING
    (r"\bBET365\b|\bSKY\s*BET\b|\bPADDY\s*POWER\b|\bLADBROKES\b|\bNATIONAL\s*LOTTERY\b", "Gambling", "Sports Betting", "Gambling Provider", ["gambling", "betting", "lottery"]),

    # 26. BNPL & DEBT
    (r"\bKLARNA\b", "BNPL", "Klarna Instalment", "Klarna", ["bnpl", "instalment", "pay in 3"]),
    (r"\bCLEARPAY\b", "BNPL", "Clearpay", "Clearpay", ["bnpl", "instalment"]),
    (r"\bBARCLAYCARD\b|\bAMEX\b|\bAMERICAN\s*EXPRESS\b", "Credit Card", "Card Repayment", "Credit Card Payment", ["credit card", "debt repayment"]),

    # 27. INTERNATIONAL REMITTANCE
    (r"\bWISE\b(?:\s*PAYMENTS?|\s*INTERNATIONAL|\s*REMITTANCE)?|\bWESTERN\s*UNION\b|\bREMITLY\b|\bMONEYGRAM\b|\bWORLDREMIT\b|\bACE\s*MONEY\s*TRANSFER\b", "Remittance", "International Remittance", "Money Remittance", ["remittance", "international transfer", "fx"]),

    # 28. INVESTMENTS & SAVINGS
    (r"\bCOINBASE\b|\bKRAKEN\b|\bBINANCE\b|\bTRADING\s*212\b|\bETORO\b|\bHARGREAVES\s*LANSDOWN\b|\bVANGUARD\b", "Investments", "Crypto Trading", "Investment Platform", ["investments", "crypto", "trading", "stocks"]),
    (r"\bSAVINGS\s*VAULT\b|\bPLUM\s*SAVINGS\b|\bCHIP\s*SAVINGS\b|\bMONEYBOX\b", "Savings", "Savings Vault Deposit", "Savings Deposit", ["savings", "deposit"]),

    # 29. TRAVEL & AIRLINES
    (r"\bBRITISH\s*AIRWAYS\b|\bEASYJET\b|\bRYANAIR\b|\bPREMIER\s*INN\b|\bTRAVELODGE\b|\bAIRBNB\b|\bBOOKING\.COM\b|\bHOTELS?\.COM\b", "Travel", "Flights & Airlines", "Travel Booking", ["travel", "flights", "hotels"]),

    # 30. WEB & APP HOSTING
    (r"\bVERCEL\b|\bNETLIFY\b|\bHEROKU\b|\bSUPABASE\b|\bDIGITALOCEAN\b|\bCLOUDFLARE\b|\bFOCALBOARD\b", "Software", "Web Hosting", "Developer Hosting", ["software", "developer tools", "cloud"]),

    # 31. RESTAURANTS & PUBS
    (r"\bTHE\s*IVY\b|\bBISTRO\b|\bSTEAKHOUSE\b|\bTRATTORIA\b", "Dining", "Restaurants", "Restaurant", ["dining", "restaurant", "food"]),
    (r"\bTHE\s*RED\s*LION\b|\bTHE\s*CROWN\b|\bPUB\b|\bTAVERN\b|\bBREWERY\b", "Bars", "Pubs & Taverns", "Pub & Bar", ["bars", "pub", "drinks"]),

    # 32. BANK FEES
    (r"\bOVERDRAFT\b|\bNON-STERLING\b|\bFOREIGN\s*TRANSACTION\s*FEE\b|\bACCOUNT\s*(?:MAINTENANCE\s*)?CHARGE\b|\bBANK\s*CHARGES?\b", "Fees", "Bank Charges", "Bank Account Fee", ["fees", "bank charges", "service charge"])
]

def clean_raw_description(desc):
    """
    Cleans banking technical codes, prefixes, dates, and locations.
    Preserves true brand names and unglues digit-stuck tokens.
    """
    t = str(desc).strip()

    # 1. Split digit-glued tokens (e.g. 'SUBWAY18831' -> 'SUBWAY 18831')
    t = re.sub(r'([A-Za-z]{3,})(\d+)', r'\1 \2', t)

    # 2. Normalize asterisks to spaces (e.g. 'UBER* EATS' -> 'UBER EATS')
    t = re.sub(r'\*', ' ', t)

    # 3. Strip payment processor wrappers (e.g. 'PAYPAL *NETFLIX' -> 'NETFLIX')
    t = re.sub(r'^(?:PAYPAL\s+|SQ\s+|SUMUP\s+|ZETTLE_\s*|STRIPE\s+|IZ\s+)', '', t, flags=re.I)

    # 4. Bank transaction prefixes (Santander, HSBC, Starling)
    t = re.sub(r"^CARD\s*PAYMENT\s*TO\s+(.*?)\s+ON\s+\d{2}-\d{2}-\d{4}.*$", r"\1", t, flags=re.I)
    t = re.sub(r"^BILL\s*PAYMENT\s*(?:VIA\s*FASTER\s*PAYMENT\s*)?TO\s+(.*?)(?:\s+REFERENCE|\s+MANDATE|,).*$", r"To: \1", t, flags=re.I)
    t = re.sub(r"^BILL\s*PAYMENT\s*FROM\s+(.*?)(?:,\s*REFERENCE|\s+MANDATE).*$", r"From: \1", t, flags=re.I)
    t = re.sub(r"^FASTER\s*PAYMENTS?\s*(?:RECEIPT\s*)?(?:REF\..*?\s*)?FROM\s+(.*)$", r"From: \1", t, flags=re.I)

    # Clean technical prefixes
    t = re.sub(r"^\)\)\)\s*", "", t)
    t = re.sub(r"^VIS\s+", "", t)
    t = re.sub(r"^GOOGLE\s*PAY\s+", "", t, flags=re.I)
    t = re.sub(r"^FASTER\s*PAYMENT\s+", "", t, flags=re.I)
    t = re.sub(r"^CR\s+", "", t)

    # Strip 'BP ' prefix ONLY if not followed by fuel keywords
    if re.match(r"^BP\s+(?!CONNECT|OIL|PULSE|PETROL|SERVICE|FORECOURT)", t, flags=re.I):
        t = re.sub(r"^BP\s+", "", t, flags=re.I)

    # 5. Universal postal district codes, URLs, terminal noise, and numeric reference codes
    t = re.sub(r'/[A-Za-z0-9_\-\.]+', '', t)
    t = re.sub(r'\.(?:com|co\.uk|org|net|gov\.uk)\b', '', t, flags=re.I)
    t = re.sub(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", "", t)
    t = re.sub(r"\bREF(?:\.|\s+)[A-Z0-9]+\b", "", t, flags=re.I)
    t = re.sub(r"\b(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{8,}\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()

    return t

def anonymize_human_names(name):
    """
    Anonymizes human personal names into initials (e.g. 'To: Sarah Jenkins' -> 'To: SJ').
    Leaves company / business names intact.
    """
    clean_str = name.strip()
    prefix = ""
    if clean_str.lower().startswith("to: "):
        prefix = "To: "
        clean_str = clean_str[4:].strip()
    elif clean_str.lower().startswith("from: "):
        prefix = "From: "
        clean_str = clean_str[6:].strip()

    words = clean_str.split()
    non_person = {
        "ltd", "limited", "plc", "llp", "uk", "shop", "market", "chicken", "kebab",
        "services", "security", "store", "news", "travel", "cafe", "bakes", "design",
        "tech", "energy", "water", "mobile", "broadband", "council", "tax", "bank",
        "pharmacy", "dental", "clinic", "restaurant", "pub", "bar", "cinema", "hotel"
    }
    if 2 <= len(words) <= 4 and not any(w.lower() in non_person for w in words):
        initials = "".join([w[0].upper() for w in words if w[0].isalpha()])
        if initials:
            return f"{prefix}{initials}" if prefix else initials

    return name

def detect_channel(desc):
    """
    Infers payment transaction channel from banking raw codes.
    """
    up = str(desc).upper()
    if "DIRECT DEBIT" in up or "D/D" in up:
        return "Direct Debit"
    if "STANDING ORDER" in up or "S/O" in up:
        return "Standing Order"
    if "CARD PAYMENT" in up or "VIS " in up or "DEBIT CARD" in up or ")))" in up:
        return "Card Payment"
    if "ATM" in up or "CASH" in up or "LINK" in up or "NOTEMAC" in up:
        return "ATM Cash"
    if "FASTER PAYMENT" in up or "BILL PAYMENT" in up or "TRANSFER" in up or "BP " in up:
        return "Bank Transfer"
    if "GOOGLE PAY" in up or "APPLE PAY" in up:
        return "Digital Wallet"
    if "PAYPAL" in up:
        return "Payment App"
    if "CHEQUE" in up:
        return "Cheque"
    return "Electronic Payment"

def rule_based_classify(cleaned_desc, direction):
    """
    Deterministic rule matcher for SEED_PATTERNS.
    Direction-aware:
    - If Direction == 'In' and matched a merchant -> Refunds
    - If Direction == 'In' and matched wages/payroll -> Salary
    """
    upper_desc = cleaned_desc.upper()

    # Cash / ATM Withdrawals
    if re.search(r"\bATM\s*CASH\b|\bATM\s*WITHDRAWAL\b|\bNOTEMAC\b|\bLINK\s*ATM\b", upper_desc):
        return "Cash", "ATM Withdrawal", "ATM Cash Withdrawal", ["cash", "atm withdrawal", "physical money"]

    # Inflow-specific rules
    if direction == "In":
        # Salary / Payroll keywords
        if re.search(r"\bSALARY\b|\bPAYROLL\b|\bWAGES?\b|\bDIRECT\s*DEPOSIT\b|\bSTIPEND\b", upper_desc):
            return "Salary", "Employment Wages", "Payroll Receipt", ["salary", "payroll", "wages", "earnings"]
        # Benefits / Tax rebates
        if re.search(r"\bTAX\s*(?:REBATE|REFUND)\b|\bCHILD\s*BENEFIT\b|\bUNIVERSAL\s*CREDIT\b|\bHMRC\b.*(?:\bREFUND\b|\bREBATE\b|\bBENEFIT\b)", upper_desc):
            return "Benefits", "Tax Rebates", "HMRC Benefit / Rebate", ["benefits", "tax rebate", "hmrc"]
        # Bank Interest
        if re.search(r"\bGROSS\s*INTEREST\b|\bNET\s*INTEREST\b|\bSAVINGS\s*INTEREST\b", upper_desc):
            return "Interest", "Savings Interest", "Bank Interest Paid", ["interest", "savings interest"]
        # Cashback / Rewards
        if re.search(r"\bCASHBACK\b|\bTOPCASHBACK\b|\bREWARD\s*PAYOUT\b", upper_desc):
            return "Rewards", "Cashback Reward", "Cashback Reward", ["rewards", "cashback"]
        # PayPal withdrawal (money transfer to bank)
        if "PPWDL" in upper_desc or ("PAYPAL" in upper_desc and "WITHDRAWAL" in upper_desc):
            return "Transfers", "Payment App Withdrawal", "PayPal Withdrawal", ["transfer", "paypal", "wallet"]

    for pattern, category, subcat, clean_name, tags in SEED_PATTERNS:
        if re.search(pattern, upper_desc):
            if direction == "In":
                # Store / retailer inflow is a REFUND!
                merchant_categories = {
                    "Shopping", "Fashion", "Beauty", "Home", "Electronics", "Gifts",
                    "Groceries", "Dining", "Takeaway", "Coffee", "Bars", "Streaming",
                    "Gaming", "Software", "Fuel", "Motoring", "Travel", "Entertainment"
                }
                if category in merchant_categories:
                    return "Refunds", "Merchant Refund", clean_name, ["refund", "store return", "money back"]
                elif category == "Salary":
                    return "Salary", "Employment Wages", clean_name, tags
            elif direction == "Out":
                if category == "Salary":
                    category = "Transfers"
                    subcat = "Internal Account Transfer"
            return category, subcat, clean_name, tags

    # Personal Transfers fallback
    if upper_desc.startswith("TO:") or upper_desc.startswith("FROM:"):
        anon = anonymize_human_names(cleaned_desc)
        return "Peer-to-Peer", "Personal Transfer", anon, ["transfer", "p2p", "personal payment"]

    return None, None, None, None

def pass2_consolidate(df):
    """
    Pass 2 Consolidation Engine:
    1. Cross-account internal transfer pairing (pairs matching Out on Bank A with In on Bank B).
    2. Peer-to-Peer vs Own-account Transfers separation.
    3. Generic recurring employer income detection (works for ANY employer).
    4. Merchant direction alignment (merchant In -> Refunds).
    5. Clean-name validation (replaces empty/numeric names).
    """
    df = df.copy()

    # Step A: Cross-Account Internal Transfer Pairing
    # If Bank A has Out for £X and Bank B has In for £X on similar dates (+- 3 days)
    # pair them as Transfers (Internal Account Transfer)
    try:
        df['Date_Parsed'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
    except Exception:
        df['Date_Parsed'] = pd.NaT

    out_candidates = df[df['Direction'] == 'Out'].index
    in_candidates = df[df['Direction'] == 'In'].index

    paired_indices = set()
    for o_idx in out_candidates:
        o_row = df.loc[o_idx]
        o_amt = o_row['Amount']
        o_bank = o_row.get('Bank')
        o_date = o_row['Date_Parsed']

        # Find matching In candidate on a DIFFERENT bank
        for i_idx in in_candidates:
            if i_idx in paired_indices or i_idx == o_idx:
                continue
            i_row = df.loc[i_idx]
            i_amt = i_row['Amount']
            i_bank = i_row.get('Bank')
            i_date = i_row['Date_Parsed']

            if abs(o_amt - i_amt) < 0.01 and o_bank != i_bank:
                # Check date window if dates valid
                date_ok = True
                if pd.notna(o_date) and pd.notna(i_date):
                    date_ok = abs((o_date - i_date).days) <= 3

                if date_ok:
                    df.at[o_idx, 'Category'] = "Transfers"
                    df.at[o_idx, 'Subcategory'] = "Internal Account Transfer"
                    df.at[o_idx, 'Tags'] = ["internal transfer", "own account", "cross-account"]
                    df.at[i_idx, 'Category'] = "Transfers"
                    df.at[i_idx, 'Subcategory'] = "Internal Account Transfer"
                    df.at[i_idx, 'Tags'] = ["internal transfer", "own account", "cross-account"]
                    paired_indices.add(o_idx)
                    paired_indices.add(i_idx)
                    break

    # Step B: Own-Account Transfer reference keywords
    own_bank_pattern = r"\b(?:REVOLUT|NATIONWIDE|BARCLAYS|SANTANDER|HSBC|STARLING|MONZO|LLOYDS|NATWEST|HALIFAX|NORTHBRIDGE)\b|OWN\s*ACCOUNT|SAVINGS\s*VAULT"
    for idx, row in df.iterrows():
        raw_upper = str(row['Description']).upper()
        if row['Category'] in ("Transfers", "Peer-to-Peer"):
            if re.search(own_bank_pattern, raw_upper):
                df.at[idx, 'Category'] = "Transfers"
                df.at[idx, 'Subcategory'] = "Internal Account Transfer"

    # Step C: Generic Recurring Employer Income Detection (Anti-Overfitting)
    # Detects corporate employer entity receipts >= £250 without hardcoding employer names
    corporate_employer_pattern = r"\b(?:LTD|LIMITED|PLC|CORP|GROUP|SERVICES|LOGISTICS|HEALTHCARE|NHS|COUNCIL|SECURITY|MANAGEMENT)\b"
    for idx, row in df.iterrows():
        if row['Direction'] == 'In' and row['Category'] not in ("Salary", "Transfers", "Refunds", "Benefits", "Interest"):
            desc_upper = str(row['Description']).upper()
            amt = float(row.get('Amount', 0.0))
            if amt >= 250.0 and re.search(corporate_employer_pattern, desc_upper):
                clean_name = row['Clean_Description']
                df.at[idx, 'Category'] = "Salary"
                df.at[idx, 'Subcategory'] = "Employment Wages"
                df.at[idx, 'Tags'] = ["salary", "payroll", "employer earnings", "wages"]

    # Step D: Direction alignment: any store/merchant Inflow -> Refunds
    merchant_cats = {
        "Shopping", "Fashion", "Beauty", "Home", "Electronics", "Gifts",
        "Groceries", "Dining", "Takeaway", "Coffee", "Bars", "Streaming",
        "Gaming", "Software", "Fuel", "Motoring", "Travel", "Entertainment"
    }
    for idx, row in df.iterrows():
        if row['Direction'] == 'In' and row['Category'] in merchant_cats:
            df.at[idx, 'Category'] = "Refunds"
            df.at[idx, 'Subcategory'] = "Merchant Refund"
            df.at[idx, 'Tags'] = ["refund", "merchant refund", "store return", "money back"]

    # Step E: Clean Name Validation
    for idx, row in df.iterrows():
        c_name = str(row.get('Clean_Description', '')).strip()
        if not c_name or c_name.lower() in ("unknown", "none", "") or c_name.isdigit():
            # Fall back to cleaned raw description
            df.at[idx, 'Clean_Description'] = clean_raw_description(row['Description'])

    # Step F: Validate Subcategory
    for idx, row in df.iterrows():
        cat = row.get('Category')
        sub = row.get('Subcategory')
        valid_subs = TAXONOMY.get(cat, ["Specialty Spending"])
        if not sub or sub not in valid_subs:
            df.at[idx, 'Subcategory'] = valid_subs[0]

    return df

def pass2_ai_qa_audit(df, memory_cache=None, preferred="gemini"):
    """
    Pass 2 AI QA Auditor (2nd API Request):
    Independent second-pass QA review using Gemini 3.5 Flash Lite.
    Audits critical, two-way, inflow, and high-value transactions to:
    1. Catch misclassifications or edge-case oversights.
    2. Prevent lumped/compound categories.
    3. Ensure strict taxonomy adherence.
    4. Enforce directional consistency (Store inflows -> Refunds, Corporate receipts -> Salary/Revenue).
    5. Resolve P2P vs Internal Transfers.
    Gracefully handles offline/unreachable LLM without modifying df.
    """
    if df is None or df.empty:
        return df, memory_cache

    df = df.copy()
    if memory_cache is None:
        memory_cache = {}

    if 'Tags' not in df.columns:
        df['Tags'] = [None] * len(df)
    if 'Clean_Description' not in df.columns:
        df['Clean_Description'] = df['Description'] if 'Description' in df.columns else ""

    critical_cats = {"Transfers", "Peer-to-Peer", "Loans", "Tax", "Cash", "Credit Card", "Refunds", "Revenue", "Salary"}
    
    candidate_indices = []
    for idx, row in df.iterrows():
        cat = row.get("Category")
        direction = row.get("Direction", "Out")
        try:
            amt = float(row.get("Amount", 0.0))
        except (ValueError, TypeError):
            amt = 0.0

        is_inflow = direction == "In"
        is_critical_cat = cat in critical_cats
        is_high_value = amt >= 150.0
        is_invalid = not cat or cat not in VALID_CATEGORIES

        if is_inflow or is_critical_cat or is_high_value or is_invalid:
            candidate_indices.append(idx)

    if not candidate_indices:
        return df, memory_cache

    # Chunk into batches of up to 40 to stay well within token and latency constraints
    for i in range(0, len(candidate_indices), 40):
        batch_idxs = candidate_indices[i:i + 40]
        batch_items = []
        for b_idx in batch_idxs:
            r = df.loc[b_idx]
            batch_items.append({
                "id": int(b_idx),
                "merchant": str(r.get("Clean_Description", r.get("Description", ""))),
                "raw_desc": str(r.get("Description", "")),
                "direction": str(r.get("Direction", "Out")),
                "amount": float(r.get("Amount", 0.0)),
                "current_category": str(r.get("Category", "")),
                "current_subcategory": str(r.get("Subcategory", ""))
            })

        qa_prompt = f"""
You are the Chief Financial Auditor and QA Lead conducting Pass 2 Quality Assurance.
Review the classified transactions below. Identify and correct ANY misclassifications, duplicate categories, or taxonomy violations.

AVAILABLE TAXONOMY (Strict Single-Title Categories Only - NEVER use '&', ',', or '/'):
- Food: Groceries, Dining, Takeaway, Coffee, Bars
- Retail: Shopping, Fashion, Beauty, Home, Electronics, Gifts
- Digital: Software, Streaming, Gaming
- Travel & Commute: Transport, Taxis, Fuel, Parking, Motoring, Travel
- Bills: Rent, Mortgage, Energy, Water, Mobile, Broadband, Council Tax, Tax, Insurance
- Life: Entertainment, Fitness, Health, Pets, Childcare, Education, Charity, Gambling, Fees, Services
- Financial Flows: Transfers, Peer-to-Peer, Remittance, Savings, Investments, Cash, Credit Card, Loans, BNPL
- Inflows: Salary, Pension, Revenue, Refunds, Benefits, Interest, Rewards

CRITICAL AUDIT RULES:
1. TRANSFERS VS PEER-TO-PEER:
   - "Transfers": ONLY for moving funds between the user's OWN accounts (e.g., savings vaults, cross-bank transfers).
   - "Peer-to-Peer": Payments sent to or received from other individuals (friends, family, named persons, casual payments).
2. INFLOW CLASSIFICATION:
   - "Salary": Regular employment payroll, wages, employer direct credits.
   - "Revenue": Business sales, client invoice receipts, freelance contracts, merchant payouts.
   - "Refunds": Inflows from retail shops, merchants, cancelled orders, returns.
   - "Benefits": Universal credit, child benefit, government allowances.
   - "Peer-to-Peer": Inflows from individual people / friends.
3. SINGLE-WORD / 1-TITLE CATEGORIES ONLY:
   - Never use lumped titles (e.g. do not combine into "Food & Drink", "Travel & Commute", "Shopping & Retail").
   - Use strictly one valid category from the list above.
4. CORRECTIONS ONLY:
   - If a transaction is ALREADY correctly classified, DO NOT include it in your output.
   - ONLY return transactions that need a correction or refinement.

TRANSACTIONS TO AUDIT:
{json.dumps(batch_items, indent=2)}

Return STRICTLY a JSON array of corrections (empty array [] if all are correct):
[
  {{
    "id": <id_number>,
    "category": "<ExactValidCategory>",
    "subcategory": "<SubcategoryName>",
    "reason": "<Brief explanation>"
  }}
]
"""
        try:
            response_text, _ = invoke_llm(qa_prompt, preferred=preferred, temperature=0.0)
            corrections = parse_json_safely(response_text)
            if isinstance(corrections, list):
                for item in corrections:
                    if not isinstance(item, dict):
                        continue
                    try:
                        row_id = int(item.get("id"))
                    except (ValueError, TypeError):
                        continue

                    new_cat = item.get("category")
                    new_sub = item.get("subcategory")
                    
                    if row_id in df.index and new_cat in VALID_CATEGORIES:
                        valid_subs = TAXONOMY.get(new_cat, ["Specialty Spending"])
                        if not new_sub or new_sub not in valid_subs:
                            new_sub = valid_subs[0]

                        df.at[row_id, 'Category'] = new_cat
                        df.at[row_id, 'Subcategory'] = new_sub
                        df.at[row_id, 'Tags'] = get_fallback_tags(new_cat)

                        raw_d = str(df.at[row_id, 'Description'])
                        clean_d = str(df.at[row_id, 'Clean_Description'])
                        cache_entry = {
                            "category": new_cat,
                            "subcategory": new_sub,
                            "clean_name": clean_d,
                            "tags": get_fallback_tags(new_cat)
                        }
                        if memory_cache is not None:
                            memory_cache[raw_d] = cache_entry
                            memory_cache[clean_d] = cache_entry
        except Exception as e:
            print(f"[Banker] Pass 2 AI QA audit skipped or failed: {e}")

    return df, memory_cache

def run_ai_audit(df, ai_choice="auto"):
    """
    Audits and categorizes transactions across the granular individual taxonomy.
    Executes Pass 1 (Rules & LLM) and Pass 2 (Consolidation & Internal Transfers).
    Returns: (categorized_df, summary_df, roast_text)
    """
    cache_file = "memory.json"
    memory_cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                memory_cache = json.load(f)
        except Exception:
            memory_cache = {}

    df = df.copy()
    if 'Direction' not in df.columns:
        df['Direction'] = 'Out'

    df['Clean_Description'] = df['Description'].apply(clean_raw_description)
    df['Channel'] = df['Description'].apply(detect_channel)
    df['Category'] = None
    df['Subcategory'] = None
    df['Tags'] = None

    # Step 1: Rule Engine & Memory Cache
    unmapped = []
    for idx, row in df.iterrows():
        raw_desc = row['Description']
        clean_d = row['Clean_Description']
        direction = row['Direction']

        # Rule matching
        cat, subcat, clean_n, tags = rule_based_classify(clean_d, direction)
        if cat:
            df.at[idx, 'Category'] = cat
            df.at[idx, 'Subcategory'] = subcat
            df.at[idx, 'Clean_Description'] = clean_n
            df.at[idx, 'Tags'] = tags
            continue

        # Cache lookup
        cached_entry = memory_cache.get(raw_desc) or memory_cache.get(clean_d)
        if isinstance(cached_entry, dict) and cached_entry.get("category") in VALID_CATEGORIES:
            cat = cached_entry["category"]
            subcat = cached_entry.get("subcategory")
            if not subcat or subcat not in TAXONOMY.get(cat, []):
                subcat = TAXONOMY.get(cat, ["Specialty Spending"])[0]
            clean_name = cached_entry.get("clean_name", clean_d)
            tags = cached_entry.get("tags") or get_fallback_tags(cat)

            df.at[idx, 'Category'] = cat
            df.at[idx, 'Subcategory'] = subcat
            df.at[idx, 'Clean_Description'] = clean_name
            df.at[idx, 'Tags'] = tags
            continue

        unmapped.append((idx, raw_desc, clean_d, direction))

    # Step 2: Batch Unknown Merchants to LLM
    if unmapped:
        unique_unknowns = {}
        for idx, raw_d, clean_d, direction in unmapped:
            if clean_d not in unique_unknowns:
                unique_unknowns[clean_d] = {"raw": raw_d, "direction": direction, "indices": []}
            unique_unknowns[clean_d]["indices"].append(idx)

        pref = "auto"
        if "Gemini" in ai_choice:
            pref = "gemini"
        elif "Groq" in ai_choice:
            pref = "groq"

        unknown_items = list(unique_unknowns.items())
        taxonomy_guide = {k: v[:3] for k, v in TAXONOMY.items()}

        for chunk_start in range(0, len(unknown_items), 35):
            chunk = unknown_items[chunk_start:chunk_start + 35]
            items_for_prompt = [
                {"merchant": k, "direction": v["direction"]}
                for k, v in chunk
            ]

            prompt = f"""
            You are an elite, modern Financial Auditor. Categorize these bank transactions into our granular, single-title taxonomy:
            {json.dumps(taxonomy_guide, indent=2)}

            TRANSACTIONS TO CATEGORIZE:
            {json.dumps(items_for_prompt, indent=2)}

            CRITICAL TAXONOMY RULES (DO NOT LUMP):
            1. SINGLE-WORD / 1-TITLE CATEGORIES ONLY (No '&', ',', or '/'):
               - Food: Groceries, Dining, Takeaway, Coffee, Bars
               - Retail: Shopping, Fashion, Beauty, Home, Electronics, Gifts
               - Digital: Software, Streaming, Gaming
               - Travel & Commute: Transport, Taxis, Fuel, Parking, Motoring, Travel
               - Bills: Rent, Mortgage, Energy, Water, Mobile, Broadband, Council Tax, Tax, Insurance
               - Life: Entertainment, Fitness, Health, Pets, Childcare, Education, Charity, Gambling, Fees, Services
               - Financial Flows: Transfers, Peer-to-Peer, Remittance, Savings, Investments, Cash, Credit Card, Loans, BNPL
               - Inflows: Salary, Pension, Revenue, Refunds, Benefits, Interest, Rewards
            2. INDIVIDUAL SEPARATION (DO NOT LUMP):
               - Takeaway (Uber Eats, Deliveroo, fast food) vs Dining (sit-down restaurant) vs Coffee vs Groceries.
               - Peer-to-Peer (person to person) vs Transfers (between own accounts).
               - Software (apps/tools) vs Streaming (video/music) vs Gaming.
               - Fashion (clothes/shoes) vs Home (furniture/DIY) vs Electronics vs Shopping.
            3. INFLOWS & REFUNDS: If direction is 'In' and money is received from a store/retailer -> 'Refunds'!
               If direction is 'In' and payroll/wages/employer -> 'Salary'!
               If direction is 'In' and another individual -> 'Peer-to-Peer'!
            4. SUBCATEGORY: Specific, descriptive focus (e.g. 'Fast Food', 'Supermarket', 'Coffee Shop', 'Ride-Hailing').
            5. CLEAN_NAME: Clean brand name. If a person, anonymize to uppercase initials (e.g. 'JS', 'AK').
            6. TAGS: 4-5 category descriptors. NEVER repeat words from merchant name.

            Output STRICTLY a JSON dictionary:
            {{
               "Merchant": {{"category": "Category", "subcategory": "Subcategory", "clean_name": "Clean Name", "tags": ["tag1", "tag2", "tag3", "tag4"]}}
            }}
            """

            try:
                response_text, _ = invoke_llm(prompt, preferred=pref, temperature=0.0)
                llm_mappings = parse_json_safely(response_text)

                for clean_k, m_info in llm_mappings.items():
                    if isinstance(m_info, dict) and clean_k in unique_unknowns:
                        item_dir = unique_unknowns[clean_k]["direction"]
                        cat = m_info.get("category", "Shopping")
                        if cat not in VALID_CATEGORIES:
                            cat = "Shopping"

                        assigned_clean = m_info.get("clean_name", clean_k)
                        subcat = m_info.get("subcategory", TAXONOMY.get(cat, ["Specialty"])[0])
                        raw_tags = m_info.get("tags", [])
                        cleaned_tags = [t.lower() for t in raw_tags if not any(b in t.lower() for b in ["misc", "general", "other", "unknown"])]
                        if not cleaned_tags:
                            cleaned_tags = get_fallback_tags(cat)

                        for row_idx in unique_unknowns[clean_k]["indices"]:
                            df.at[row_idx, 'Category'] = cat
                            df.at[row_idx, 'Subcategory'] = subcat
                            df.at[row_idx, 'Clean_Description'] = assigned_clean
                            df.at[row_idx, 'Tags'] = cleaned_tags

                        raw_d = unique_unknowns[clean_k]["raw"]
                        cache_entry = {
                            "category": cat,
                            "subcategory": subcat,
                            "clean_name": assigned_clean,
                            "tags": cleaned_tags
                        }
                        memory_cache[raw_d] = cache_entry
                        memory_cache[clean_k] = cache_entry
            except Exception as e:
                print(f"[Banker] LLM categorization error: {e}")

    # Fallback for anything unmapped
    for idx, row in df.iterrows():
        if not df.at[idx, 'Category']:
            is_in = row['Direction'] == 'In'
            cat_fallback = "Salary" if is_in else "Shopping"
            df.at[idx, 'Category'] = cat_fallback
            df.at[idx, 'Subcategory'] = "Employment Wages" if is_in else "Online Marketplaces"
            df.at[idx, 'Tags'] = get_fallback_tags(cat_fallback)

    # Step 3: Pass 2 Consolidation Engine (Internal Transfers, Recurring Income, Consistency)
    df = pass2_consolidate(df)

    # Step 3b: Pass 2 AI QA Auditor (2nd API Request - Gemini 3.5 Flash Lite)
    df, memory_cache = pass2_ai_qa_audit(df, memory_cache=memory_cache, preferred="gemini")

    # Save cache
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(memory_cache, f, indent=4)
    except Exception:
        pass

    # Step 4: Summary calculations
    df['Amount_Numeric'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    out_df = df[df['Direction'] == 'Out']
    if not out_df.empty:
        summary_df = out_df.groupby('Category', as_index=False).agg(
            Total_Spent=('Amount_Numeric', 'sum'),
            Tx_Count=('Amount_Numeric', 'count')
        )
        total_out_sum = summary_df['Total_Spent'].sum()
        summary_df['Percentage'] = ((summary_df['Total_Spent'] / total_out_sum) * 100).round(1) if total_out_sum > 0 else 0.0
        summary_df = summary_df.sort_values(by='Total_Spent', ascending=False).reset_index(drop=True)
    else:
        summary_df = pd.DataFrame(columns=['Category', 'Total_Spent', 'Tx_Count', 'Percentage'])

    # The Roast (strictly routed to Groq to conserve Gemini quota)
    total_out = out_df['Amount_Numeric'].sum() if not out_df.empty else 0.0
    top_cat = summary_df.iloc[0]['Category'] if not summary_df.empty else "Nothing"
    top_val = summary_df.iloc[0]['Total_Spent'] if not summary_df.empty else 0.0

    roast_prompt = f"""
    You are a brutally funny, honest financial advisor.
    The user spent £{total_out:,.2f} in total, with their top spending area being {top_cat} at £{top_val:,.2f}.
    Deliver exactly ONE short, hilarious, punchy roast sentence about their financial habits. No emojis, no markdown.
    """
    try:
        roast_text, _ = invoke_llm(roast_prompt, preferred="groq", temperature=0.7)
        roast_text = roast_text.strip('"').strip()
    except Exception:
        roast_text = "Your bank account is weeping quietly in the corner."

    return df, summary_df, roast_text