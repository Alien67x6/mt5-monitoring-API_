from fastapi import FastAPI
import MetaTrader5 as mt5
import pandas as pd
import time
from collections import deque
from twilio.rest import Client
import threading
from dotenv import load_dotenv  # Importar dotenv
import os  # Para leer variables de entorno

# Cargar variables desde el archivo .env
load_dotenv()

app = FastAPI()

# 🔹 Configuración de Twilio (AHORA desde el .env)
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
MI_WHATSAPP_NUMBER = os.getenv("MI_WHATSAPP_NUMBER")

def enviar_mensaje_whatsapp(mensaje):
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        body=mensaje,
        to=MI_WHATSAPP_NUMBER
    )
    return f"✅ Mensaje enviado: {message.sid}"

# Conectar a MetaTrader 5
if not mt5.initialize():
    raise Exception("❌ Error al conectar con MetaTrader 5")

# 🔹 Lista de activos a monitorear
tickers = ["EURUSD", "GBPUSD", "USDJPY"]
cruces_detectados = {symbol: deque(maxlen=10) for symbol in tickers}

def calcular_medias(df):
    df["SMA_150"] = df["close"].rolling(window=150).mean()
    df["SMA_75"] = df["close"].rolling(window=75).mean()
    df["EMA_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["EMA_20"] = df["close"].ewm(span=20, adjust=False).mean()
    return df

def detectar_cruce_precio(df):
    if len(df) < 2:
        return False
    prev, last = df.iloc[-2], df.iloc[-1]
    cruzaron_precio = (
        (prev["SMA_150"] > prev["close"] and prev["SMA_75"] > prev["close"] and prev["EMA_50"] > prev["close"] and prev["EMA_20"] > prev["close"])
        and
        (last["SMA_150"] < last["close"] and last["SMA_75"] < last["close"] and last["EMA_50"] < last["close"] and last["EMA_20"] < last["close"])
    ) or (
        (prev["SMA_150"] < prev["close"] and prev["SMA_75"] < prev["close"] and prev["EMA_50"] < prev["close"] and prev["EMA_20"] < prev["close"])
        and
        (last["SMA_150"] > last["close"] and last["SMA_75"] > last["close"] and last["EMA_50"] > last["close"] and last["EMA_20"] > last["close"])
    )
    return cruzaron_precio

def detectar_cruce_entre_medias(df):
    if len(df) < 2:
        return False
    prev, last = df.iloc[-2], df.iloc[-1]
    return (
        (prev["SMA_150"] > prev["SMA_75"] > prev["EMA_50"] > prev["EMA_20"] and last["SMA_150"] < last["SMA_75"] < last["EMA_50"] < last["EMA_20"])
    ) or (
        (prev["SMA_150"] < prev["SMA_75"] < prev["EMA_50"] < prev["EMA_20"] and last["SMA_150"] > last["SMA_75"] > last["EMA_50"] > last["EMA_20"])
    )

@app.get("/")
def home():
    return {"mensaje": "API de monitoreo de MetaTrader 5 en ejecución"}

@app.get("/monitorear")
def monitorear():
    alertas = []
    for symbol in tickers:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 200)
        if rates is None:
            continue

        df = pd.DataFrame(rates)
        df = calcular_medias(df)

        if detectar_cruce_precio(df):
            cruces_detectados[symbol].append(time.time())

        if cruces_detectados[symbol] and detectar_cruce_entre_medias(df):
            tiempo_espera = time.time() - cruces_detectados[symbol][0]
            if tiempo_espera < 600:
                mensaje = f"🚀 ALERTA en {symbol}: Cruce COMPLETO detectado (Precio + Medias)."
                enviar_mensaje_whatsapp(mensaje)
                alertas.append(mensaje)
                cruces_detectados[symbol].clear()

    return {"alertas": alertas or "No se detectaron cruces."}

# 🔹 Definir la función monitoreo_continuo ANTES de llamarla
def monitoreo_continuo():
    while True:
        print("🔄 Ejecutando monitoreo...")
        monitorear()  # Llama la función monitorear periódicamente
        time.sleep(60)  # Espera 60 segundos antes de la siguiente ejecución

# 🔹 Ahora, después de definir TODAS las funciones, iniciamos el hilo:
if __name__ == "__main__":
    threading.Thread(target=monitoreo_continuo, daemon=True).start()
