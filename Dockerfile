FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python domain.py && useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
ENV HOST=0.0.0.0 PORT=5050 ALLOW_IMPORTS=0 PYTHONUNBUFFERED=1
EXPOSE 5050
CMD ["python", "app.py"]
