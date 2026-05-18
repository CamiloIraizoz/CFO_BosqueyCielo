FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*

# Descargar el binario de Composio directamente para Linux x64
RUN curl -fsSL "https://github.com/ComposioHQ/composio/releases/download/%40composio%2Fcli%400.2.28/composio-linux-x64.zip" \
    -o /tmp/composio.zip && \
    mkdir -p /root/.composio && \
    unzip /tmp/composio.zip -d /root/.composio/ && \
    chmod +x /root/.composio/composio && \
    rm /tmp/composio.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY execution/ execution/
COPY Directivas/ Directivas/
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
