FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

EXPOSE 8001

CMD ["uvicorn", "context_api:app", "--host", "0.0.0.0", "--port", "8001"]