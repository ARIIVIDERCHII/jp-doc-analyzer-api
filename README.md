# Enterprise JP Doc Analyzer 📄⚡

[English](#english) | [日本語](#日本語)

---

<a name="english"></a>
## English Version

An enterprise-grade, high-load microservice for extracting strictly structured JSON data from Japanese business documents (請求書 - Invoices, 領収書 - Receipts). 

Built with **FastAPI** and **Gemini Vision AI**, this service features hybrid document routing, strict schema validation, and asynchronous processing, making it ready for production environments.

### 🚀 Key Features
* **Hybrid Vision Engine:** Automatically routes standard images directly to AI, while PDFs are rasterized in-memory using `PyMuPDF` for accurate multi-page processing.
* **Strict Data Validation:** Enforces a 100% predictable JSON structure using `Pydantic` schemas.
* **Fault Tolerance:** Implements exponential backoff and retry mechanisms (`Tenacity`) for network failures.
* **High-Load Guardrails:** Uses `asyncio.Semaphore` to control concurrent API requests, protecting against rate limits.
* **Dockerized:** Fully containerized for instant deployment.

### 🛠️ Tech Stack
* **Backend:** Python 3.11, FastAPI
* **AI Engine:** Google Generative AI (Gemini 1.5 Flash)
* **Processing:** PyMuPDF, Pillow

---

<a name="日本語"></a>
## 日本語版

日本のビジネス書類（請求書、領収書）から構造化されたJSONデータを抽出するための、エンタープライズ向け高負荷対応マイクロサービスです。

**FastAPI**と**Gemini Vision AI**をベースに構築されており、ハイブリッドルーティング、厳格なスキーマ検証、および非同期処理を備え、本番環境に即座に導入可能な設計となっています。

### 🚀 主な機能
* **ハイブリッド・ビジョンエンジン:** 標準的な画像はAIに直接ルーティングし、PDFは`PyMuPDF`を使用してメモリ内でラスタライズ（画像化）することで、複数ページの正確な解析を実現します。
* **厳格なデータ検証:** `Pydantic`スキーマを使用して、100%予測可能なJSON構造を強制します。
* **耐障害性:** ネットワークやAPIの失敗に対し、指数関数的バックオフとリトライメカニズム（`Tenacity`）を実装しています。
* **高負荷ガードレール:** `asyncio.Semaphore`を使用して同時APIリクエスト数を制御し、レートリミットやメモリ不足（OOM）を防ぎます。
* **Docker対応:** コンテナ化されており、あらゆるクラウド環境に即座にデプロイ可能です。

### 🛠️ 技術スタック
* **バックエンド:** Python 3.11, FastAPI
* **AIエンジン:** Google Generative AI (Gemini 1.5 Flash)
* **ドキュメント処理:** PyMuPDF (fitz), Pillow (PIL)

---

## 🐳 Local Setup (Docker)

Run this single block of commands in your terminal to set up and launch the project:

```bash
# 1. Create .env file (replace 'your_google_api_key' with your actual key)
echo "GEMINI_API_KEY=your_google_api_key" > .env
echo "APP_SECRET_KEY=super-secret-key-123" >> .env

# 2. Build and run the Docker container
docker build -t jp-doc-analyzer . && docker run -p 8000:8000 --env-file .env jp-doc-analyzer
```

3. Access the interactive Swagger UI at `http://localhost:8000/docs`