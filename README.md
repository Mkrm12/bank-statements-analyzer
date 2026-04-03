# 🏦 Pulse AI: Financial Auditor (Web Edition)

Transform your boring bank statements into a brutal, AI-powered financial audit. Now featuring a full **Streamlit Web Interface**, multi-bank support, and highly secure interactive data visualizations. 

🔥 **Live Deployment:** [mkrm-pulse.streamlit.app](https://mkrm-pulse.streamlit.app/)

## 🚀 Key Features
- **Modern Web UI**: Drag-and-drop your PDFs directly in your browser.
- **Smart Routing 2.0**: Automatic detection and extraction for **HSBC**, **Santander**, **Revolut**, **Starling**, and now **Nationwide** statements.
- **Context-Aware AI**: The engine remembers your categories via `memory.json` to keep audits consistent across months.
- **Interactive Visuals**: View your spending through dynamic bar charts and expandable category breakdowns.
- **The Roast**: A brutally honest, sarcastic financial assessment.

## ⚡ Recent Updates & Optimizations
- **Engine Buff**: Added Nationwide bank support and updated 2-Pass RAG prompts.
- **Cloud Migration**: Transitioned hosting from **Azure** to **Streamlit Community Cloud** for a leaner, zero-maintenance architecture and faster CI/CD deployment cycles.
- **AI Router Upgrade**: Integrated GitHub Models (`gpt-4o`) for elite categorization and Groq (`llama-3.3-70b` & `llama-3.1-8b`) as a lightning-fast fallback for chat.
- **Docker Support**: Added a `Dockerfile` for seamless containerized deployment (can be deployed anywhere).

## 📂 Project Structure
- `app.py`: The Streamlit frontend (run this to start the app).
- `extractor.py`: The engine that parses PDFs.
- `banker.py`: The logic for AI categorization and roasting.
- `memory.json`: Local cache for shop-to-category mapping (auto-generated).

## 🛠️ Setup & Installation

1. **Clone the Repo**:
   ```bash
   git clone [https://github.com/Mkrm12/bank-statements-analyzer.git](https://github.com/Mkrm12/bank-statements-analyzer.git)
   cd bank-statements-analyzer