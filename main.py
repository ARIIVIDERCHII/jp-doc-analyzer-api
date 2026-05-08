import os
import io
import time
import asyncio
import logging
import fitz  # PyMuPDF
from PIL import Image
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, UploadFile, File, Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError # Специфичные ошибки Google
from dotenv import load_dotenv

# ---------------- 1. НАСТРОЙКИ, ЛОГИ И ЛИМИТЫ ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "fallback-secret-for-dev")

# Enterprise Guards (можно переопределить в .env)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 10))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
PDF_DPI = int(os.getenv("PDF_DPI", 150))
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", 10)) # Защита от OOM (Out of Memory)
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 5)) # Ограничение нагрузки на API

# Семафор для контроля конкурентности (Не пустит больше N запросов к ИИ одновременно)
ai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# ---------------- 2. БЕЗОПАСНОСТЬ ----------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != APP_SECRET_KEY:
        logger.warning("Блокировка: Неверный API ключ.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Доступ запрещен.")
    return api_key

# Инициализация модели
available_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
best_model = next((m for m in ['gemini-1.5-flash', 'gemini-pro-vision'] if m in available_models), available_models[0])
logger.info(f"Инициализация: {best_model} | Max Concurrent: {MAX_CONCURRENT_REQUESTS} | Max File: {MAX_FILE_SIZE_MB}MB")
model = genai.GenerativeModel(best_model)

app = FastAPI(title="Enterprise JP Doc Analyzer (V4 - High Load & Metrics)")

# ---------------- 3. PYDANTIC СХЕМЫ ----------------
class DocumentItem(BaseModel):
    company_name: Optional[str] = Field(description="Name of the company issuing the document")
    payer_name: Optional[str] = Field(description="Name of the person/company being billed (宛名 - Atena)")
    purchaser_member: Optional[str] = Field(description="Name, email, or ID of the purchasing member (購入会員 / 購入者)")
    expense_category: Optional[str] = Field(description="Categorize the expense (Meals, Travel, Entertainment, etc.)")
    payment_method: Optional[str] = Field(description="How it was paid (Cash, Credit Card, QR Code, Bank Transfer)")
    amount: Optional[float] = Field(description="Numeric value for this specific ticket/receipt. Must be a number.")
    tax_amount: Optional[float] = Field(description="Tax amount. Must be a number.")
    date: Optional[str] = Field(description="Date of the transaction (format YYYY-MM-DD)")
    time: Optional[str] = Field(description="Time of the transaction (e.g., '15:35-15:50' or '20:44:58')")
    document_number: Optional[str] = Field(description="Registration, invoice, or ticket number")

class InvoiceExtractionResult(BaseModel):
    grand_total: Optional[float] = Field(description="Calculate the total sum of all items/tickets found")
    currency: Optional[str] = Field(description="Currency code (e.g., JPY, USD)")
    documents: List[DocumentItem]

# Новый Wrapper для ответа API (Решает баг с потерей route_used и добавляет метрики)
class APIResponse(BaseModel):
    status: str
    route_used: str
    processing_time_sec: float
    total_tokens_used: Optional[int] = None
    data: InvoiceExtractionResult
# ---------------------------------------------------

BASE_PROMPT = "You are an expert AI data extractor for Japanese business documents. Extract the required fields based on the provided JSON schema. Carefully examine the image(s) provided."

# ---------------- 4. RETRY & ASYNC QUEUE ----------------
# Ловим только ошибки Google API и таймауты. Ошибки кода Pydantic падать будут сразу.
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((GoogleAPIError, ConnectionError, TimeoutError)),
    reraise=True
)
async def safe_generate_content(payload, config):
    # Ограничиваем конкурентные вызовы
    async with ai_semaphore:
        logger.info("Отправка запроса в Gemini API (Семафор захвачен)...")
        return await model.generate_content_async(payload, generation_config=config)
# --------------------------------------------------------

@app.post("/api/v1/extract-data", response_model=APIResponse)
async def extract_data(file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    start_time = time.time()
    logger.info(f"Входящий запрос: {file.filename}")
    
    try:
        contents = await file.read()
        
        # GUARD: Проверка размера файла
        if len(contents) > MAX_FILE_SIZE_BYTES:
            logger.warning(f"Отказ: Файл превышает {MAX_FILE_SIZE_MB}MB.")
            raise HTTPException(status_code=413, detail=f"Размер файла превышает лимит в {MAX_FILE_SIZE_MB}MB.")
            
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=InvoiceExtractionResult
        )
        
        payload = [BASE_PROMPT]
        route_used = ""

        if "pdf" in file.content_type:
            pdf_document = fitz.open(stream=contents, filetype="pdf")
            total_pages = len(pdf_document)
            
            # GUARD: Ограничение количества страниц
            pages_to_process = min(total_pages, MAX_PDF_PAGES)
            if total_pages > MAX_PDF_PAGES:
                logger.warning(f"PDF обрезан: Обработка {MAX_PDF_PAGES} из {total_pages} страниц.")
                
            for page_num in range(pages_to_process):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=PDF_DPI)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                payload.append(img)
                
                # OPTIMIZATION: Ручная очистка памяти
                del pix
                del page
                
            pdf_document.close()
            route_used = "PDF Vision Rasterizer"

        elif "image" in file.content_type:
            image = Image.open(io.BytesIO(contents))
            payload.append(image)
            route_used = "Direct Vision Engine"
            
        else:
            raise HTTPException(status_code=400, detail="Поддерживаются только PDF и картинки (JPEG, PNG).")

        # Асинхронный вызов с Retry и Семафором
        response = await safe_generate_content(payload, generation_config)
        
        # METRICS: Подсчет токенов (если модель отдает эти данные)
        tokens_used = None
        if hasattr(response, 'usage_metadata'):
            tokens_used = response.usage_metadata.total_token_count
            
        # Строгая валидация Pydantic
        result_data = InvoiceExtractionResult.model_validate_json(response.text)
        process_time = round(time.time() - start_time, 2)
        
        logger.info(f"Успех. Время: {process_time}с | Токены: {tokens_used} | Сумма: {result_data.grand_total}")
        
        # Формируем безопасный финальный ответ по схеме APIResponse
        return APIResponse(
            status="success",
            route_used=route_used,
            processing_time_sec=process_time,
            total_tokens_used=tokens_used,
            data=result_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Внутренняя ошибка сервера: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Произошла непредвиденная ошибка обработки.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)