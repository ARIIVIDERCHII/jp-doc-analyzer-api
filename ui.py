import os
import time
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Enterprise Doc AI", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

API_KEY = os.getenv("APP_SECRET_KEY")
if not API_KEY:
    st.error("Критическая ошибка / Critical Error: APP_SECRET_KEY not found in .env")
    st.stop()

# --- СЛОВАРЬ ПЕРЕВОДОВ ---
TRANSLATIONS = {
    "English": {
        "title": "⚡ Enterprise JP Invoice Intelligence",
        "subtitle": "Automated data extraction for Japanese receipts and invoices.",
        "upload_center": "Upload Center",
        "drag_drop": "Drag and drop your file below.",
        "status_online": "System Status: **Online** 🟢",
        "preview": "📄 Document Preview",
        "pdf_ready": "PDF Document ready for rasterization.",
        "process_btn": "🚀 Process Document",
        "init": "Initializing AI Pipeline...",
        "sending": "⏳ Sending file to secure server...",
        "rasterizing": "⚙️ Rasterizing and preparing Vision Engine...",
        "analyzing": "🧠 Analyzing data via Gemini 1.5 Flash...",
        "success_msg": "✅ Structured data extracted successfully.",
        "time": "⏱️ Processing Time",
        "tokens": "🪙 AI Tokens",
        "items": "📑 Items Found",
        "total": "💴 Grand Total",
        "tab_data": "📊 Extracted Data",
        "tab_json": "💻 Raw JSON",
        "download": "📥 Download CSV",
        "no_docs": "No documents found.",
        "error_server": "Server Error",
        "error_conn": "Connection failed",
        "waiting": "👈 Please upload a document via the sidebar to begin."
    },
    "日本語": {
        "title": "⚡ エンタープライズ請求書 AI解析",
        "subtitle": "日本の領収書や請求書からのデータ抽出を自動化します。",
        "upload_center": "アップロードセンター",
        "drag_drop": "以下にファイルをドラッグ＆ドロップしてください。",
        "status_online": "システム状態: **オンライン** 🟢",
        "preview": "📄 ドキュメント プレビュー",
        "pdf_ready": "PDFドキュメントのラスタライズ準備完了。",
        "process_btn": "🚀 ドキュメントを処理",
        "init": "AIパイプラインを初期化中...",
        "sending": "⏳ セキュアサーバーにファイルを送信中...",
        "rasterizing": "⚙️ ビジョンエンジンを準備中...",
        "analyzing": "🧠 Gemini 1.5 Flashでデータを解析中...",
        "success_msg": "✅ 構造化データの抽出に成功しました。",
        "time": "⏱️ 処理時間",
        "tokens": "🪙 消費トークン",
        "items": "📑 検出項目",
        "total": "💴 合計金額",
        "tab_data": "📊 抽出データ",
        "tab_json": "💻 生JSON",
        "download": "📥 CSVをダウンロード",
        "no_docs": "ドキュメントが見つかりませんでした。",
        "error_server": "サーバーエラー",
        "error_conn": "接続に失敗しました",
        "waiting": "👈 開始するには、サイドバーからドキュメントをアップロードしてください。"
    },
    "Русский": {
        "title": "⚡ AI-Анализатор японских документов",
        "subtitle": "Автоматическое извлечение данных из чеков и счетов-фактур.",
        "upload_center": "Центр загрузки",
        "drag_drop": "Перетащите файл в зону ниже.",
        "status_online": "Статус системы: **Онлайн** 🟢",
        "preview": "📄 Предпросмотр",
        "pdf_ready": "PDF готов к растрированию.",
        "process_btn": "🚀 Обработать документ",
        "init": "Инициализация AI Pipeline...",
        "sending": "⏳ Отправка файла на защищенный сервер...",
        "rasterizing": "⚙️ Подготовка Vision Engine...",
        "analyzing": "🧠 Анализ данных через Gemini 1.5 Flash...",
        "success_msg": "✅ Структурированные данные успешно получены.",
        "time": "⏱️ Время обработки",
        "tokens": "🪙 AI Токены",
        "items": "📑 Найдено элементов",
        "total": "💴 Итого",
        "tab_data": "📊 Извлеченные данные",
        "tab_json": "💻 Сырой JSON",
        "download": "📥 Скачать CSV",
        "no_docs": "Документы не найдены.",
        "error_server": "Ошибка сервера",
        "error_conn": "Ошибка соединения",
        "waiting": "👈 Пожалуйста, загрузите документ через панель слева для начала работы."
    }
}

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #0E1117; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 20px; background-color: transparent; border-radius: 6px 6px 0 0; }
    .stTabs [aria-selected="true"] { background-color: #1E2127; border-bottom: 2px solid #00E676 !important; color: #00E676 !important; }
    .hero-title { font-size: 2.8rem; font-weight: 800; color: #FFFFFF; margin-bottom: 0px; letter-spacing: -0.5px; }
    .hero-subtitle { font-size: 1.2rem; color: #8B949E; margin-top: 5px; margin-bottom: 30px; }
    .badge { background-color: #1F6FEB; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; margin-right: 8px; }
    hr { border-color: #30363D; }
    div[data-testid="metric-container"] { transition: transform 0.2s ease; }
    div[data-testid="metric-container"]:hover { transform: translateY(-2px); }
</style>
""", unsafe_allow_html=True)

API_URL = "https://jp-doc-analyzer-api-v2.onrender.com/api/v1/extract-data"

# --- ВЫБОР ЯЗЫКА ---
selected_lang = st.sidebar.selectbox("Language / 言語 / Язык", ["English", "日本語", "Русский"])
t = TRANSLATIONS[selected_lang]

st.markdown(f'<p class="hero-title">{t["title"]}</p>', unsafe_allow_html=True)
st.markdown(f'<p class="hero-subtitle">{t["subtitle"]}</p>', unsafe_allow_html=True)
st.markdown("""
    <span class="badge">FastAPI</span>
    <span class="badge">Gemini Vision AI</span>
    <span class="badge">High-Load Ready</span>
""", unsafe_allow_html=True)
st.divider()

with st.sidebar:
    st.image("123.png", width=50)
    
    st.header(t["upload_center"])
    st.markdown(t["drag_drop"])
    
    uploaded_file = st.file_uploader("", type=["pdf", "png", "jpg", "jpeg"])
    
    st.divider()
    st.caption(t["status_online"])
    st.caption("Region: **US West (Oregon)**")

if uploaded_file:
    col_preview, col_data = st.columns([1, 2], gap="large")
    
    with col_preview:
        st.subheader(t["preview"])
        if uploaded_file.type == "application/pdf":
            st.info(t["pdf_ready"])
        else:
            st.image(uploaded_file, use_container_width=True, caption=uploaded_file.name)
            
        start_btn = st.button(t["process_btn"], type="primary", use_container_width=True)

    with col_data:
        if start_btn:
            status = st.status(t["init"], expanded=True)
            status.write(t["sending"])
            
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                headers = {"X-API-Key": API_KEY}
                
                time.sleep(0.5)
                status.write(t["rasterizing"])
                
                response = requests.post(API_URL, files=files, headers=headers)
                
                if response.status_code == 200:
                    status.write(t["analyzing"])
                    result = response.json()
                    status.update(label=t["success_msg"], state="complete", expanded=False)
                    
                    st.success(t["success_msg"])
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric(label=t["time"], value=f"{result['processing_time_sec']}s")
                    m2.metric(label=t["tokens"], value=result["total_tokens_used"])
                    m3.metric(label=t["items"], value=len(result["data"]["documents"]))
                    m4.metric(label=t["total"], value=f"¥ {result['data']['grand_total']:,}")
                    
                    st.divider()
                    
                    tab_table, tab_json = st.tabs([t["tab_data"], t["tab_json"]])
                    
                    with tab_table:
                        docs_data = result["data"]["documents"]
                        if docs_data:
                            df = pd.DataFrame(docs_data)
                            st.dataframe(df, use_container_width=True, hide_index=True)
                            
                            csv = df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label=t["download"],
                                data=csv,
                                file_name=f"invoice_data.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        else:
                            st.warning(t["no_docs"])
                            
                    with tab_json:
                        st.json(result)
                        
                else:
                    status.update(label=t["error_server"], state="error", expanded=True)
                    st.error(f"{t['error_server']}: {response.status_code}")
                    st.write(response.text)
                    
            except Exception as e:
                status.update(label=t["error_conn"], state="error", expanded=True)
                st.error(f"{t['error_conn']}: {e}")
else:
    st.info(t["waiting"])