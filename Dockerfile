# Используем легковесную версию Python
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    mupdf-tools \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую папку в контейнере
WORKDIR /app

# Копируем список библиотек и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь наш код
COPY . .

# Открываем порт 8000
EXPOSE 8000

# Команда для запуска сервера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]