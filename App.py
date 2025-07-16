import ccxt
import pandas as pd
import ta
import time
from datetime import datetime, timedelta
from flask import Flask, render_template
import json
import threading
import os

app = Flask(__name__)

# Configurare Bybit API (mainnet)
exchange = ccxt.bybit({
    'apiKey': 'Lan13he2ndUGDmjF0z',
    'secret': 'JdNIc1JGajTPxeZHE3dgDbxWRqyE85OpwBOE',
    'enableRateLimit': True,
    'urls': {
        'api': {
            'public': 'https://api.bybit.com',
            'private': 'https://api.bybit.com'
        }
    }
})

# Setări bot
symbol = 'XRP/USDT'
leverage = 10
balance = 75000  # Balans virtual în USDT
position_size = 0.1  # 10% din balans per tranzacție
position = None  # Poziție curentă: None, 'long' sau 'short'
current_position_qty = 0  # Cantitatea poziției curente
entry_price = 0  # Prețul de intrare al poziției curente
profit_data = []  # Stocare profit pentru grafice
indicators = {}   # Stocare indicatori
last_signal = 'hold'  # Inițializare semnal
current_price = 0  # Preț curent
predictions = {'1m': 0, '5m': 0, '15m': 0}  # Inițializare predicții
bot_initialized = False  # Indicator pentru inițializarea botului
last_analysis_time = None  # Timestamp-ul ultimei analize

# Funcție pentru a valida datele OHLCV
def validate_ohlcv(df):
    if df is None or df.empty:
        print("DataFrame OHLCV este gol sau None")
        return False
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_columns):
        print("Coloane lipsă în DataFrame OHLCV")
        return False
    if df[required_columns].isna().any().any():
        print("Valori NaN detectate în datele OHLCV")
        return False
    # Verifică variația prețurilor
    if df['close'].nunique() <= 1 or (df['close'].max() - df['close'].min()) < 1e-6:
        print("Date OHLCV constante sau variație prea mică")
        return False
    # Verifică golurile în timestamp
    df['time_diff'] = df['timestamp'].diff().dt.total_seconds()
    if (df['time_diff'] > 60).any():
        print("Goluri detectate în timestamp-urile OHLCV")
    print(f"Sumar OHLCV: close min={df['close'].min()}, max={df['close'].max()}, nunique={df['close'].nunique()}")
    return True

# Funcție pentru a obține date OHLCV
def fetch_ohlcv(symbol, timeframe, limit=75):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Convertește coloanele numerice la float64
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Elimină rândurile cu NaN
        if df[numeric_columns].isna().any().any():
            print(f"Valori NaN detectate în datele OHLCV pentru {timeframe}, eliminăm rândurile afectate")
            df = df.dropna()
        
        if validate_ohlcv(df):
            print(f"Date OHLCV valide obținute pentru {timeframe}: {len(df)} lumânări")
            print(f"Primele 5 rânduri din df:\n{df.head()}")
            print(f"Ultimele 5 rânduri din df:\n{df.tail()}")
            return df
        else:
            return None
    except Exception as e:
        print(f"Eroare la obținerea datelor OHLCV pentru {timeframe}: {e}")
        return None

# Funcție pentru a calcula indicatorii tehnici
def calculate_indicators(df):
    try:
        if df is None or len(df) < 50:
            print(f"Date insuficiente pentru calculul indicatorilor: {len(df) if df is not None else 0} lumânări")
            return None, None
        
        indicators = {}
        # Asigură-te că datele sunt numerice
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        
        # EMA 10
        try:
            df['ema10'] = ta.trend.EMAIndicator(df['close'], window=10).ema_indicator()
            if df['ema10'].isna().all():
                print("Toate valorile ema10 sunt NaN")
            else:
                indicators['ema10'] = df['ema10'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul ema10: {e}")
        
        # EMA 20
        try:
            df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
            if df['ema20'].isna().all():
                print("Toate valorile ema20 sunt NaN")
            else:
                indicators['ema20'] = df['ema20'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul ema20: {e}")
        
        # RSI
        try:
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
            if df['rsi'].isna().all():
                print("Toate valorile rsi sunt NaN")
            else:
                indicators['rsi'] = df['rsi'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul rsi: {e}")
        
        # MACD
        try:
            macd = ta.trend.MACD(df['close'])
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            if df[['macd', 'macd_signal']].isna().all().all():
                print("Toate valorile macd sau macd_signal sunt NaN")
            else:
                indicators['macd'] = df['macd'].iloc[-1]
                indicators['macd_signal'] = df['macd_signal'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul macd: {e}")
        
        # Bollinger Bands
        try:
            bb = ta.volatility.BollingerBands(df['close'], window=20)
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_lower'] = bb.bollinger_lband()
            if df[['bb_upper', 'bb_lower']].isna().all().all():
                print("Toate valorile bb_upper sau bb_lower sunt NaN")
            else:
                indicators['bb_upper'] = df['bb_upper'].iloc[-1]
                indicators['bb_lower'] = df['bb_lower'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul Bollinger Bands: {e}")
        
        # Stochastic Oscillator
        try:
            stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14)
            df['stoch_k'] = stoch.stoch()
            df['stoch_d'] = stoch.stoch_signal()
            if df[['stoch_k', 'stoch_d']].isna().all().all():
                print("Toate valorile stoch_k sau stoch_d sunt NaN")
            else:
                indicators['stoch_k'] = df['stoch_k'].iloc[-1]
                indicators['stoch_d'] = df['stoch_d'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul Stochastic: {e}")
        
        # ATR
        try:
            df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close']).average_true_range()
            if df['atr'].isna().all():
                print("Toate valorile atr sunt NaN")
            else:
                indicators['atr'] = df['atr'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul atr: {e}")
        
        # SAR
        try:
            df['sar'] = ta.trend.PSARIndicator(df['high'], df['low'], df['close']).psar()
            if df['sar'].isna().all():
                print("Toate valorile sar sunt NaN")
            else:
                indicators['sar'] = df['sar'].iloc[-1]
        except Exception as e:
            print(f"Eroare la calculul sar: {e}")
        
        if indicators:
            print(f"Indicatori calculați cu succes: {list(indicators.keys())}")
            return df, indicators
        else:
            print("Niciun indicator valid calculat")
            return df, None
    except Exception as e:
        print(f"Eroare generală la calculul indicatorilor: {e}")
        return df, None

# Funcție pentru a genera semnal (cu condiții relaxate)
def generate_signal(df, indicators):
    global last_signal
    try:
        if df is None or len(df) < 2 or indicators is None:
            print("Date insuficiente pentru generarea semnalului")
            return 'hold'
        
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        print(f"Valori indicatori: {indicators}")
        required_indicators = ['ema10', 'ema20', 'sar']
        missing_indicators = [ind for ind in required_indicators if ind not in indicators]
        print(f"Indicatori lipsă: {missing_indicators}")
        
        # Logică simplificată dacă lipsește orice indicator esențial
        if missing_indicators:
            if 'sar' in indicators and 'atr' in indicators:
                print(f"Close: {last_row['close']}, SAR: {indicators['sar']}, ATR: {indicators['atr']}, Prev ATR: {prev_row['atr']}")
                if last_row['close'] > indicators['sar'] and indicators['atr'] > prev_row['atr']:
                    print("Semnal generat: buy (logică simplificată)")
                    return 'buy'
                elif last_row['close'] < indicators['sar'] and indicators['atr'] > prev_row['atr']:
                    print("Semnal generat: sell (logică simplificată)")
                    return 'sell'
            print("Semnal generat: hold (lipsește indicator esențial)")
            return 'hold'
        
        # Logică relaxată bazată pe EMA și SAR
        print(f"EMA10: {indicators['ema10']}, EMA20: {indicators['ema20']}, Close: {last_row['close']}, SAR: {indicators['sar']}")
        if indicators['ema10'] > indicators['ema20'] and last_row['close'] > indicators['sar']:
            print("Semnal generat: buy (logică EMA + SAR)")
            return 'buy'
        elif indicators['ema10'] < indicators['ema20'] and last_row['close'] < indicators['sar']:
            print("Semnal generat: sell (logică EMA + SAR)")
            return 'sell'
        
        print("Semnal generat: hold")
        return 'hold'
    except Exception as e:
        print(f"Eroare la generarea semnalului: {e}")
        return 'hold'

# Funcție pentru predicție simplă
def predict_price(df, timeframe):
    if df is None or len(df) < 2:
        print(f"Date insuficiente pentru predicție pe {timeframe}")
        return 0
    last_row = df.iloc[-1]
    df, indicators = calculate_indicators(df)
    if indicators is None:
        return last_row['close'] if not pd.isna(last_row['close']) else 0
    signal = generate_signal(df, indicators)
    if signal == 'buy':
        return last_row['close'] * 1.005
    elif signal == 'sell':
        return last_row['close'] * 0.995
    return last_row['close']

# Funcție pentru a simula tranzacții (îmbunătățită)
def execute_trade(signal, price, balance, position_size):
    global position, current_position_qty, entry_price, profit_data
    try:
        if price == 0 or pd.isna(price):
            print("Preț invalid pentru tranzacție")
            return balance, 0
        
        # Calculează cantitatea pentru o nouă poziție
        qty = (balance * position_size * leverage) / price
        
        # Închide poziția existentă și calculează profitul/pierderea
        if position is not None and current_position_qty > 0:
            if (signal == 'buy' and position == 'short') or (signal == 'sell' and position == 'long'):
                # Calculează profitul/pierderea
                if position == 'long':
                    profit = (price - entry_price) * current_position_qty
                else:  # position == 'short'
                    profit = (entry_price - price) * current_position_qty
                balance += profit
                print(f"[{datetime.now()}] Închid poziție {position} la {price}, Profit/Pierdere: {profit:.2f} USDT, Balans nou: {balance:.2f} USDT")
                profit_data.append({'timestamp': datetime.now().isoformat(), 'balance': balance})
                position = None
                current_position_qty = 0
                entry_price = 0
        
        # Deschide o nouă poziție
        if signal == 'buy' and position is None:
            position = 'long'
            current_position_qty = qty
            entry_price = price
            print(f"[{datetime.now()}] Deschid poziție long la {price}, Cantitate: {qty:.2f} XRP")
            return balance, qty
        elif signal == 'sell' and position is None:
            position = 'short'
            current_position_qty = qty
            entry_price = price
            print(f"[{datetime.now()}] Deschid poziție short la {price}, Cantitate: {qty:.2f} XRP")
            return balance, qty
        
        print(f"[{datetime.now()}] Nicio tranzacție executată: Signal={signal}, Position={position}")
        return balance, 0
    except Exception as e:
        print(f"Eroare la executarea tranzacției: {e}")
        return balance, 0

# Funcție pentru a salva datele de profit
def save_profit_data():
    try:
        with open('data/profit_data.json', 'w') as f:
            json.dump(profit_data, f)
    except Exception as e:
        print(f"Eroare la salvarea datelor de profit: {e}")

# Funcție pentru a rula botul (analiză la fiecare 5 secunde)
def run_bot():
    global balance, indicators, last_signal, current_price, predictions, bot_initialized, last_analysis_time, current_position_qty
    print("Botul pornește...")
    time.sleep(5)  # Așteaptă 5 secunde pentru inițializare
    while True:
        try:
            last_analysis_time = datetime.now().isoformat()
            df_1m = fetch_ohlcv(symbol, '1m', limit=75)
            df_5m = fetch_ohlcv(symbol, '5m', limit=75)
            df_15m = fetch_ohlcv(symbol, '15m', limit=75)
            
            if df_1m is None or df_5m is None or df_15m is None:
                print("Eroare: date OHLCV lipsă, încerc din nou...")
                time.sleep(5)
                continue
            
            # Setează current_price chiar dacă indicatorii eșuează
            current_price = df_1m['close'].iloc[-1] if not df_1m.empty and not pd.isna(df_1m['close'].iloc[-1]) else 0
            print(f"Preț curent obținut: {current_price}")
            
            df_1m, ind_1m = calculate_indicators(df_1m)
            if df_1m is None or ind_1m is None:
                print("Eroare: indicatorii nu au fost calculați pentru 1m")
                indicators = {}
                last_signal = 'hold'
                predictions = {'1m': current_price, '5m': current_price, '15m': current_price}
            else:
                indicators = ind_1m
                last_signal = generate_signal(df_1m, indicators)
                predictions = {
                    '1m': predict_price(df_1m, '1m'),
                    '5m': predict_price(df_5m, '5m'),
                    '15m': predict_price(df_15m, '15m')
                }
            
            balance, qty = execute_trade(last_signal, current_price, balance, position_size)
            print(f"Balans curent: {balance:.2f} USDT | Cantitate: {qty:.2f} XRP | Poziție: {position} | Ultima analiză: {last_analysis_time}")
            
            profit_data.append({'timestamp': last_analysis_time, 'balance': balance})
            save_profit_data()
            
            bot_initialized = True
            time.sleep(5)  # Analiză la fiecare 5 secunde
        except Exception as e:
            print(f"Eroare în bucla botului: {e}")
            time.sleep(5)

# Rute Flask
@app.route('/')
def index():
    global bot_initialized, last_analysis_time, position, current_position_qty
    if not bot_initialized:
        print("Botul nu este încă inițializat")
        return render_template('index.html', 
                             balance=balance,
                             current_price=current_price,
                             indicators={},
                             last_signal='hold',
                             predictions={'1m': 0, '5m': 0, '15m': 0},
                             profit_1d=[],
                             profit_1w=[],
                             profit_1m=[],
                             last_analysis_time='N/A',
                             position=position,
                             current_position_qty=current_position_qty)
    
    now = datetime.now()
    one_day_ago = now - timedelta(days=1)
    one_week_ago = now - timedelta(days=7)
    one_month_ago = now - timedelta(days=30)
    
    profit_1d = [d for d in profit_data if datetime.fromisoformat(d['timestamp']) > one_day_ago]
    profit_1w = [d for d in profit_data if datetime.fromisoformat(d['timestamp']) > one_week_ago]
    profit_1m = [d for d in profit_data]
    
    return render_template('index.html', 
                         balance=balance,
                         current_price=current_price,
                         indicators=indicators,
                         last_signal=last_signal,
                         predictions=predictions,
                         profit_1d=profit_1d,
                         profit_1w=profit_1w,
                         profit_1m=profit_1m,
                         last_analysis_time=last_analysis_time,
                         position=position,
                         current_position_qty=current_position_qty)

# Pornire bot în thread separat
if __name__ == '__main__':
    if not os.path.exists('data'):
        os.makedirs('data')
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=5000)
