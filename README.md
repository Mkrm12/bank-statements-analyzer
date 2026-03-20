# 🏦 Pulse AI: Financial Auditor (Web Edition)

Transform your boring bank statements into a brutal, AI-powered financial audit. Now featuring a full **Streamlit Web Interface**, multi-bank support, and highly secure interactive data visualizations. 

🔥 **Live Azure Deployment:** [http://mkrm-bank-analyzer.uksouth.azurecontainer.io:8501/](http://mkrm-bank-analyzer.uksouth.azurecontainer.io:8501/)

## 🚀 Key Features
- **Virtual Statement Generator**: Skeptical about uploading your real PDFs? Instantly generate a hyper-realistic, AI-fabricated bank statement (with custom shop injections) to safely test the app's capabilities.
- **Modern Web UI**: Drag-and-drop your PDFs directly in your browser with a sleek, high-contrast interface.
- **Smart Routing 2.0**: Automatic detection and extraction for **HSBC** and **Santander** statements.
- **Role-Based Access Control (RBAC)**: Secure entry tiers for **Master** (unlimited), **Recruiter** (300 rows, 5 chats), and **Base Users** (1 free chat, 100 rows) to manage features and API usage.
- **Context-Aware AI**: The engine remembers your categories via local caching to keep audits consistent and privacy-focused (automatically redacts personal human names to initials).
- **The Roast**: A brutally honest, sarcastic financial assessment based on your spending habits.

## 🧠 Advanced AI Architecture
- **2-Pass Categorization Engine**: 
  - *Pass 1 (Mapper):* Rapidly categorizes and extracts clean brand names.
  - *Pass 2 (The Detective QC):* Scrutinizes the memory cache to fix semantic outliers (e.g., pulling "Uber Eats" out of Travel and moving it to Food) and censors peer-to-peer personal transfers.
- **2-Pass Chatbot Retrieval (RAG)**: Eliminates LLM hallucinations by using a wide-net retrieval pass, followed by a strict Quality Control pass to filter out false positives before presenting the data to the user.
- **Dynamic LLM Fallbacks**: Built for 100% uptime. Primary queries route through **Gemini 2.5 Flash**, instantly falling back to **GitHub Models (`gpt-4o-mini`)** or **Groq (`llama-3.3-70b`)** if rate limits or server timeouts occur.

## 🛡️ Enterprise-Grade Security & Anti-Abuse
Deployed safely on the public web with strict cost-management protocols:
- **Rolling 36-Hour Global Kill Switch**: Tracks global API usage and automatically pauses the system if 50 audits are reached, rolling off older timestamps natively to prevent $5,000 API bills.
- **3-Strike Upload Ban**: Automatically detects and blocks users who repeatedly upload invalid files or non-bank PDFs.
- **Data Caps & Volatile Memory**: Limits extraction to 150 rows per PDF. Absolutely zero database is used—all data lives in volatile RAM and is wiped the moment the session ends.
- **Prompt Injection Defense**: Input sanitation and strict system instructions protect the AI from malicious prompt overrides.

## 📂 Project Structure
- `app.py`: The Streamlit frontend handling UI state, routing, auth, and the RAG Chatbot.
- `extractor.py`: The engine that parses PDFs natively (zero API calls).
- `banker.py`: The logic for multi-pass AI categorization, semantic filtering, and roasting.
- `global_stats.json`: Local cache tracking the rolling 36-hour limit.

## 🛠️ Setup & Installation

1. **Clone the Repo**:
   ```bash
   git clone [https://github.com/Mkrm12/bank-statements-analyzer.git](https://github.com/Mkrm12/bank-statements-analyzer.git)
   cd bank-statements-analyzer