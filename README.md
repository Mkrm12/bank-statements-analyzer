# 🏦 AI Financial Auditor (Web Edition)

Transform your boring bank statements into a brutal, AI-powered financial audit. Now featuring a full **Streamlit Web Interface**, multi-bank support, and interactive data visualizations.

## 🚀 Key Features
- **Modern Web UI**: Drag-and-drop your PDFs directly in your browser with a sleek, high-contrast interface.
- **Role-Based Access Control**: Secure entry tiers for **Master**, **Recruiter**, and **Base Users** to manage features and API usage.
- **Smart Routing 2.0**: Automatic detection and extraction for **HSBC** and **Santander** statements.
- **Context-Aware AI**: The engine remembers your categories via `memory.json` to keep audits consistent and privacy-focused (automatically initializes personal names).
- **Interactive Visuals**: View your spending through dynamic bar/pie charts and expandable category breakdowns.
- **The Roast**: A brutally honest, sarcastic financial assessment.

## ⚡ Recent Updates & Optimizations
- **Sidebar Authentication**: Unified login system with single-use recruiter passcodes and injection-protected inputs.
- **Abuse Prevention**: Implemented a **Global Audit Limit** (50 runs) and per-user transaction caps to manage cloud costs.
- **Azure ACI Deployment**: Added a `Dockerfile` for seamless containerized deployment to Azure Container Instances.
- **AI Router Upgrade**: Integrated GitHub Models (`gpt-4o`) for elite 3-pass categorization and Groq (`llama-3.3-70b` & `llama-3.1-8b`) as a lightning-fast Gemini fallback for chat.
- *Dev Note: Currently tracking a few minor visual bugs with the DuckDB/Plotly chart rendering and edge-case chatbot queries.*

## 📂 Project Structure
- `app.py`: The Streamlit frontend (run this to start the app).
- `extractor.py`: The engine that parses PDFs.
- `banker.py`: The logic for multi-pass AI categorization, semantic filtering, and roasting.
- `memory.json`: Local cache for shop-to-category mapping (auto-generated).

## 🛠️ Setup & Installation

1. **Clone the Repo**:
   ```bash
   git clone [https://github.com/Mkrm12/bank-statements-analyzer.git](https://github.com/Mkrm12/bank-statements-analyzer.git)
   cd bank-statements-analyzer
