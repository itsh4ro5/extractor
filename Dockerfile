FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium
COPY . /app
EXPOSE 7860
CMD ["python", "bot.py"]
