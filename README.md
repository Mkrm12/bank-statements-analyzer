# 🏦 Banker: AI-Powered Financial Auditor

Banker is a Python-based tool that extracts transaction data from bank statements and uses the **Google Gemini API** to intelligently categorize your spending habits. 

Forget "General Shopping"—this tool analyzes your descriptions to invent habits like "Fast Fashion," "Gaming Overload," or "Midnight Cravings."

## 🚀 Features
- **PDF Extraction**: Automatically parses bank statements into structured CSV data.
- **AI Categorization**: Uses `gemini-2.0-flash` to dynamically create categories based on *your* specific spending patterns.
- **Local Math**: Performs all financial totals locally using Pandas for speed and privacy.

> [!IMPORTANT]  
> **Currently Supported Banks:** HSBC (UK). More templates coming soon!

---

## 🛠️ Setup & Installation

### 1. Clone the repo
```bash
git clone [https://github.com/YOUR_USERNAME/Banker.git](https://github.com/YOUR_USERNAME/Banker.git)
cd Banker