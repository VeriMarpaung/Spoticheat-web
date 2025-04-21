# Gunakan image dasar dari Python
FROM python:3.10-slim

# Set direktori kerja di container
WORKDIR /app

# Salin file requirements.txt dan install dependensi
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin semua file project ke dalam container
COPY . .

# Tentukan port aplikasi Flask
EXPOSE 5000

# Jalankan aplikasi Flask
CMD ["python", "app.py"]
