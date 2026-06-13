FROM python:3.10-slim

WORKDIR /app

# सिस्टम डिपेंडेंसी (yt-dlp/ffmpeg की ज़रूरत नहीं, क्योंकि एक्सट्रैक्टर सिर्फ लिंक निकालता है)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# हगिंग फेस स्पेस डिफ़ॉल्ट पोर्ट 7860
EXPOSE 7860

CMD ["python", "bot.py"]
