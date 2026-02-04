# Stage 1: Build UI
FROM node:18-alpine as ui-build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend .
RUN npm run build

# Stage 2: Runtime
FROM python:3.11-slim
WORKDIR /app

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Backend deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy logic
COPY backend .

# Copy UI build
COPY --from=ui-build /app/dist /app/frontend_dist

# Env
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
