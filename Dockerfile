# Usa uma imagem oficial do Python, versão slim para ser mais leve
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Variável de ambiente para que os logs do Python apareçam em tempo real
ENV PYTHONUNBUFFERED=1

# Copia o arquivo de dependências e instala o que for necessário (requests)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código-fonte para dentro do container
COPY src/ ./src/

# Comando que será executado quando o container iniciar
CMD ["python", "src/main.py"]