# Use a lightweight Python 3.11 environment
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy your requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your app files into the container
COPY . .

# Tell Azure which port Streamlit uses
EXPOSE 8501

# The command to run the app when the container starts
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]