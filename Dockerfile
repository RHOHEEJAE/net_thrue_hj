# net_thrue_01 (헥토 행동 데이터 수집) 앱 이미지
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# 설정/DB 마이그레이션은 기동 시 또는 별도 스크립트에서 수행

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
