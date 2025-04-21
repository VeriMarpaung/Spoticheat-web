# Gunakan image dasar dari Python
FROM python:3.10-slim

# Install ffmpeg (dibutuhkan SpotDL)
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Set direktori kerja di container
WORKDIR /app

# Salin file requirements.txt dan install dependensi
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Salin semua file project ke dalam container
COPY . .
# Tentukan port aplikasi Flask
EXPOSE 5000

# Jalankan aplikasi Flask
CMD ["python", "app.py"]
