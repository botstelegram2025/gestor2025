FROM node:18-bullseye

# Install Python
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Node dependencies
COPY package.json package-lock.json* ./
RUN npm install --production || npm install --production --legacy-peer-deps

# Python dependencies
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

CMD ["python3", "bot.py"]
