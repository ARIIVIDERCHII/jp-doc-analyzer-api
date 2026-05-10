import os
import time
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Enterprise Doc AI", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# Безопасно достаем ключ (никакого хардкода!)
API_KEY = os.getenv("APP_SECRET_KEY")
if not API_KEY:
    st.error("Критическая ошибка: APP_SECRET_KEY не найден в переменных окружения (.env).")
    st.stop()

# --- CUSTOM CSS (Премиальный вид + Шрифт Inter) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
    }
    
    /* Темный фон и стилизация вкладок */
    .stApp { background-color: #0E1117; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 20px; background-color: transparent; border-radius: 6px 6px 0 0; }
    .stTabs [aria-selected="true"] { background-color: #1E2127; border-bottom: 2px solid #00E676 !important; color: #00E676 !important; }
    
    /* Hero Section */
    .hero-title { font-size: 2.8rem; font-weight: 800; color: #FFFFFF; margin-bottom: 0px; letter-spacing: -0.5px; }
    .hero-subtitle { font-size: 1.2rem; color: #8B949E; margin-top: 5px; margin-bottom: 30px; }
    .badge { background-color: #1F6FEB; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; margin-right: 8px; }
    
    /* Разделитель */
    hr { border-color: #30363D; }
    
    /* Легкая анимация при наведении на метрики */
    div[data-testid="metric-container"] {
        transition: transform 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
    }
</style>
""", unsafe_allow_html=True)

# --- КОНФИГУРАЦИЯ ---
API_URL = "https://jp-doc-analyzer-api-v2.onrender.com/api/v1/extract-data"

# --- HERO SECTION ---
st.markdown('<p class="hero-title">⚡ Enterprise JP Invoice Intelligence</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-subtitle">Automated data extraction for Japanese receipts and invoices.</p>', unsafe_allow_html=True)
st.markdown("""
    <span class="badge">FastAPI</span>
    <span class="badge">Gemini Vision AI</span>
    <span class="badge">High-Load Ready</span>
""", unsafe_allow_html=True)
st.divider()

# --- SIDEBAR (Dashboard Feel) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/1200px-Python-logo-notext.svg.png", width=50)
    st.header("Upload Center")
    st.markdown("Перетащите файл в зону ниже.")
    
    uploaded_file = st.file_uploader("", type=["pdf", "png", "jpg", "jpeg"])
    
    st.divider()
    st.caption("System Status: **Online** 🟢")
    st.caption("Region: **US West (Oregon)**")

# --- MAIN WORKSPACE ---
if uploaded_file:
    col_preview, col_data = st.columns([1, 2], gap="large")
    
    with col_preview:
        st.subheader("📄 Document Preview")
        if uploaded_file.type == "application/pdf":
            st.info("PDF Document ready for rasterization.")
        else:
            st.image(uploaded_file, use_container_width=True, caption=uploaded_file.name)
            
        start_btn = st.button("🚀 Process Document", type="primary", use_container_width=True)

    with col_data:
        if start_btn:
            # Processing Timeline
            status = st.status("Инициализация AI Pipeline...", expanded=True)
            status.write("⏳ Отправка файла на защищенный сервер...")
            
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                headers = {"X-API-Key": API_KEY}
                
                time.sleep(0.5) # Имитация шага для UX
                status.write("⚙️ Растрирование и подготовка Vision Engine...")
                
                response = requests.post(API_URL, files=files, headers=headers)
                
                if response.status_code == 200:
                    status.write("🧠 Анализ данных через Gemini 1.5 Flash...")
                    result = response.json()
                    status.update(label="Анализ успешно завершен!", state="complete", expanded=False)
                    
                    st.success("✅ Структурированные данные получены.")
                    
                    # KPI Cards
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric(label="⏱️ Processing Time", value=f"{result['processing_time_sec']}s")
                    m2.metric(label="🪙 AI Tokens", value=result["total_tokens_used"])
                    m3.metric(label="📑 Items Found", value=len(result["data"]["documents"]))
                    m4.metric(label="💴 Grand Total", value=f"¥ {result['data']['grand_total']:,}")
                    
                    st.divider()
                    
                    # Tabs (Разделение данных)
                    tab_table, tab_json = st.tabs(["📊 Extracted Data", "💻 Raw JSON"])
                    
                    with tab_table:
                        docs_data = result["data"]["documents"]
                        if docs_data:
                            df = pd.DataFrame(docs_data)
                            st.dataframe(df, use_container_width=True, hide_index=True)
                            
                            # Экспорт в CSV
                            csv = df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Скачать CSV",
                                data=csv,
                                file_name=f"invoice_data_{result['data'].get('currency', 'JPY')}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        else:
                            st.warning("Документы не найдены.")
                            
                    with tab_json:
                        st.json(result)
                        
                else:
                    status.update(label="Ошибка обработки", state="error", expanded=True)
                    st.error(f"Server Error: {response.status_code}")
                    st.write(response.text)
                    
            except Exception as e:
                status.update(label="Ошибка соединения", state="error", expanded=True)
                st.error(f"Connection failed: {e}")
else:
    st.info("👈 Пожалуйста, загрузите документ через панель слева для начала работы.")