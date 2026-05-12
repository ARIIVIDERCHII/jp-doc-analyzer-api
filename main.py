import os
import io
import time
import asyncio
import logging
import fitz
from PIL import Image
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, UploadFile, File, Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "fallback-secret-for-dev")

# ОПТИМИЗАЦИЯ ПАМЯТИ ДЛЯ RENDER (Free Tier 512MB)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 10))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
PDF_DPI = int(os.getenv("PDF_DPI", 110)) 
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", 5)) 
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 3)) 

ai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != APP_SECRET_KEY:
        logger.warning("Access Denied: Invalid API key provided.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access denied.")
    return api_key

# Умный поиск актуальной модели (безопасно для Сингапура)
try:
    available_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    best_model = next((m for m in ['gemini-1.5-flash-latest', 'gemini-1.5-flash', 'gemini-pro-vision'] if m in available_models), 'gemini-1.5-flash-latest')
except Exception as e:
    logger.warning(f"List models API blocked or failed, using fallback. Error: {e}")
    best_model = 'gemini-1.5-flash-latest'

logger.info(f"Initialized: {best_model} | Max Concurrent: {MAX_CONCURRENT_REQUESTS} | PDF DPI: {PDF_DPI}")
model = genai.GenerativeModel(best_model)

app = FastAPI(title="Enterprise JP Doc Analyzer (V4.3 - Stable Release)")

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

# ЖЕСТКИЙ ПРОМПТ С ЗАПРЕТОМ ДЕДУПЛИКАЦИИ
BASE_PROMPT = """You are an expert AI data extractor for Japanese business documents. 
Extract the required fields based on the JSON schema. 
I am providing you with multiple images representing pages of a document. Each image is preceded by a "--- PAGE X ---" text marker.

CRITICAL RULES:
1. Scan EVERY SINGLE PAGE.
2. DO NOT DEDUPLICATE. Even if the tickets/receipts look EXACTLY identical (same company, same date, same price), if they are on different pages or are separate physical items, you MUST treat them as completely separate items.
3. NEVER MERGE items. If you see 3 identical tickets, you MUST output 3 separate objects in the 'documents' array.
4. The 'amount' field MUST be the price of THAT SPECIFIC TICKET alone, do not sum them up inside the 'amount' field."""

class APIResponse(BaseModel):
    status: str
    route_used: str
    processing_time_sec: float
    total_tokens_used: Optional[int] = None
    data: InvoiceExtractionResult

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((GoogleAPIError, ConnectionError, TimeoutError)),
    reraise=True
)
async def safe_generate_content(payload, config):
    async with ai_semaphore:
        logger.info("Sending request to Gemini API (Semaphore acquired)...")
        return await model.generate_content_async(payload, generation_config=config)

@app.post("/api/v1/extract-data", response_model=APIResponse)
async def extract_data(file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    start_time = time.time()
    logger.info(f"Incoming request: {file.filename}")
    
    try:
        contents = await file.read()
        
        if len(contents) > MAX_FILE_SIZE_BYTES:
            logger.warning(f"Rejected: File exceeds {MAX_FILE_SIZE_MB}MB limit.")
            raise HTTPException(status_code=413, detail=f"File size exceeds the {MAX_FILE_SIZE_MB}MB limit.")
            
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=InvoiceExtractionResult
        )
        
        payload = [BASE_PROMPT]
        route_used = ""

        if "pdf" in file.content_type:
            pdf_document = fitz.open(stream=contents, filetype="pdf")
            total_pages = len(pdf_document)
            
            pages_to_process = min(total_pages, MAX_PDF_PAGES)
            if total_pages > MAX_PDF_PAGES:
                logger.warning(f"PDF truncated: Processing {MAX_PDF_PAGES} out of {total_pages} pages.")
                
            for page_num in range(pages_to_process):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=PDF_DPI)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                payload.append(f"--- PAGE {page_num + 1} ---")
                payload.append(img)
                
                del pix
                del page
                
            pdf_document.close()
            route_used = f"PDF Vision Rasterizer ({pages_to_process} pages)"

        elif "image" in file.content_type:
            image = Image.open(io.BytesIO(contents))
            payload.append("--- SINGLE IMAGE ---")
            payload.append(image)
            route_used = "Direct Vision Engine"
            
        else:
            raise HTTPException(status_code=400, detail="Only PDF and image files (JPEG, PNG) are supported.")

        response = await safe_generate_content(payload, generation_config)
        
        tokens_used = None
        if hasattr(response, 'usage_metadata'):
            tokens_used = response.usage_metadata.total_token_count
            
        result_data = InvoiceExtractionResult.model_validate_json(response.text)
        process_time = round(time.time() - start_time, 2)
        
        logger.info(f"Success. Time: {process_time}s | Tokens: {tokens_used} | Grand Total: {result_data.grand_total}")
        
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
        logger.error(f"Internal server error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected processing error occurred.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)