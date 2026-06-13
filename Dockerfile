# Use official Python image with all system libraries for Playwright
FROM python:3.10-slim

# Install system dependencies required by Playwright Chromium
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libxcb1 \
    fonts-liberation libappindicator3-1 libu2f-udev \
    xdg-utils wget curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Pehle sirf requirements copy karo (taaki docker cache efficiently kaam kare)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser for Playwright
RUN python -m playwright install chromium

# Ab baaki saare files copy karo
COPY . .

# Hugging Face health check ke liye port expose karna zaruri hai
EXPOSE 7860

# Environment variables (Hugging Face secrets will override these)
ENV BOT_TOKEN=""
ENV MONGO_URI=""

# Command to run your main script (Humari file bot.py hai)
CMD ["python", "bot.py"]
