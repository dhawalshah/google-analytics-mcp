# Use a slim Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Cloud Run sets PORT automatically; default to 8080
ENV PORT=8080

# Start the server
CMD ["python", "main.py"]
