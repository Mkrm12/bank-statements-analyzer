# 🏦 Pulse AI: Financial Auditor (Web Edition)

Transform your boring bank statements into a brutal, AI-powered financial audit. Now featuring a full Streamlit Web Interface, multi-bank support, and highly secure interactive data visualizations.

🔥 **Live Deployment:** [mkrm-pulse.streamlit.app](https://mkrm-pulse.streamlit.app/)

---

## 🚀 Key Features
- **Modern Web UI**: Drag-and-drop your PDFs directly in your browser with real-time feedback.
- **Smart Multi-Bank Routing**: Automatic column-aware extraction and mathematical reconciliation for HSBC, Santander, Revolut, Starling, and Nationwide statements.
- **2-Pass AI Categorization & QA**: High-precision taxonomy classifier paired with an automated Pass 2 AI auditor to catch and reconcile multi-hop edge cases.
- **Natural-Language DuckDB SQL Engine**: Ask complex questions across multiple accounts and calculate exact totals without LLM arithmetic hallucination.
- **Interactive Visuals & Breakdown**: Dynamic spending cards prioritizing top spend and high-frequency recurring areas.
- **The Roast**: A brutally honest, sarcastic financial reality check based on actual spending.

---

## ⚡ Recent Updates & Technical Improvements
- **2-Pass AI QA Architecture**: Decoupled categorization into a deterministic rule & batch pass followed by a second QA validation pass for critical flows and cross-account transfers.
- **Hybrid Multi-Engine LLM Router**: Intelligent failover across Google Gemini, Groq, and Anthropic Claude endpoints with optional Bring Your Own Key (BYOK) support.
- **Embedded DuckDB SQL Engine**: Upgraded chat querying to execute deterministic SQL queries over in-memory transaction views with companion source audit tables.
- **Zero-Storage Privacy Architecture**: In-memory ephemeral processing (`:memory:`) with zero disk persistence of user transaction records.
- **Security & Injection Shield**: Integrated SQL and prompt injection defenses with strict statement validation, file size guards, and automated PII anonymization.
- **Dynamic Frequency Ordering**: Smart breakdown of secondary spending categories ordered by transaction frequency to highlight recurring habits.
- **Enterprise Test Suite**: Added a 40-test automated verification suite covering PDF extraction, bank reconciliations, and taxonomy integrity.

---

## 📂 Project Structure
- `app.py`: Streamlit web interface, session state management, and dashboard visualization.
- `extractor.py`: Column-aware PDF statement reader and mathematical reconciliation engine.
- `banker.py`: Granular taxonomy mapping, merchant normalizer, Pass 1 categorization, and Pass 2 AI QA auditor.
- `chat_engine.py`: DuckDB SQL query generator and conversational precision analytics engine.
- `llm_router.py`: Multi-provider LLM failover router (Gemini, Groq, Claude) with BYOK handling.
- `dashboard_logic.py`: Dynamic spending categorization and frequency calculation logic.
- `run_tests.py`: Comprehensive test runner covering all core pipelines.

---

## 🛠️ Setup & Installation

```bash
# 1. Clone the repository
git clone https://github.com/Mkrm12/bank-statements-analyzer.git
cd bank-statements-analyzer

# 2. Set up virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env

# 5. Run tests
python run_tests.py

# 6. Launch local server
streamlit run app.py
```

---

## 🔑 Environment Variables (`.env`)

```env
# AI Providers
GOOGLE_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# App Security
MASTER_PASSWORD=your_master_password
RECRUITER_PASSES=code1,code2,code3
```