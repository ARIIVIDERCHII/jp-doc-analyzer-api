import os
import io
import json
import logging
import fitz  # PyMuPDF
from PIL import Image
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, UploadFile, File, Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError
from dotenv import load_dotenv

# ---------------- НАСТРОЙКА ЛОГИРОВАНИЯ ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)
# -------------------------------------------------------

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != APP_SECRET_KEY:
        logger.warning("Попытка несанкционированного доступа (Неверный API ключ).")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Доступ запрещен. Неверный X-API-Key.",
        )
    return api_key

available_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
best_model = next((m for m in ['gemini-1.5-flash', 'gemini-pro-vision'] if m in available_models), available_models[0])
logger.info(f"Сервер инициализирован. Выбрана ИИ-модель: {best_model}")
model = genai.GenerativeModel(best_model)

app = FastAPI(title="Enterprise JP Doc Analyzer (V3 - Production)")

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

BASE_PROMPT = "You are an expert AI data extractor for Japanese business documents. Extract the required fields based on the provided JSON schema. Carefully examine the image(s) provided."

# ---------------- МЕХАНИЗМ RETRY (ОТКАЗОУСТОЙЧИВОСТЬ) ----------------
# Если Google API упадет, код подождет 2 секунды, потом 4, потом 8, и только на 4-й раз выдаст ошибку.
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception), # В реальном проекте тут ловят конкретные GoogleAPIError
    reraise=True
)
async def safe_generate_content(payload, config):
    logger.info("Отправка запроса в Gemini API...")
    return await model.generate_content_async(payload, generation_config=config)
# ---------------------------------------------------------------------

@app.post("/api/v1/extract-data", response_model=InvoiceExtractionResult)
async def extract_data(file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    logger.info(f"Получен файл: {file.filename} (Тип: {file.content_type})")
    try:
        file_type = file.content_type
        contents = await file.read()
        
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=InvoiceExtractionResult
        )
        
        payload = [BASE_PROMPT]
        route_used = ""

        if "pdf" in file_type:
            logger.info("Включен маршрут обработки PDF (Растеризация)...")
            pdf_document = fitz.open(stream=contents, filetype="pdf")
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                payload.append(img)
            route_used = "PDF Vision Rasterizer"
            logger.info(f"PDF обработан: {len(pdf_document)} страниц сконвертировано в изображения.")

        elif "image" in file_type:
            logger.info("Включен маршрут обработки Изображений...")
            image = Image.open(io.BytesIO(contents))
            payload.append(image)
            route_used = "Direct Vision Engine"
            
        else:
            logger.error(f"Неподдерживаемый формат файла: {file_type}")
            raise HTTPException(status_code=400, detail="Поддерживаются только PDF и картинки (JPEG, PNG).")

        # Вызываем ИИ через нашу безопасную обертку с Retry
        response = await safe_generate_content(payload, generation_config)
        logger.info("Ответ от Gemini успешно получен.")
        
        result_data = InvoiceExtractionResult.model_validate_json(response.text)
        final_response = result_data.model_dump()
        final_response["route_used"] = route_used
        
        logger.info(f"Успешно обработано. Итоговая сумма: {final_response.get('grand_total')} {final_response.get('currency')}")
        return final_response
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обработке: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)