import os
import sqlite3
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import websocket
from config import DB_PATH

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuración de la carpeta de carga
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)  # Espera hasta 10 segundos si la base de datos está bloqueada
    connection.row_factory = sqlite3.Row
    return connection

@app.route('/')
def home():
    if 'user_id' in session:
        username = session.get('username')
        welcome_message = session.pop('welcome', None)
        return render_template('base.html', username=username, welcome_message=welcome_message, show_video=True)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if len(password) < 4:
            flash('La contraseña debe tener al menos 4 caracteres.', 'error')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            connection.commit()
            flash('User created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Try a different one.', 'error')
            return redirect(url_for('register'))
        finally:
            connection.close()

    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        connection.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = username
            session['welcome'] = f'Bienvenido, {username}!'
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'login_error')

    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Logged out successfully!')
    return redirect(url_for('login'))

@app.route('/create_notebook', methods=['POST'])
def create_notebook():
    if 'user_id' not in session:
        return jsonify({"error": "Please log in to create a notebook."}), 403

    user_id = session['user_id']
    name = request.form['name']
    initial_balance = request.form['initial_balance']
    account_type = request.form['account_type']

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('INSERT INTO notebooks (user_id, name, initial_balance, account_type) VALUES (?, ?, ?, ?)',
                   (user_id, name, initial_balance, account_type))
    connection.commit()
    notebook_id = cursor.lastrowid
    connection.close()

    return jsonify({"id": notebook_id, "name": name, "initial_balance": initial_balance, "account_type": account_type})

@app.route('/register_trade', methods=['GET', 'POST'])
def register_trade():
    if 'user_id' not in session:
        flash('Please log in to access this page.')
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        # Obtener datos del formulario
        user_id = session['user_id']
        notebook_id = request.form['notebook_id']
        asset = request.form['asset']
        lot_size = request.form['lot_size']
        entry_point = request.form['entry_point']
        stop_loss = request.form['stop_loss']
        take_profit = request.form['take_profit']
        result = request.form['result']
        trade_date = request.form['trade_date']
        emotion = request.form['emotion']
        activation_routine = request.form.get('activation_routine') == 'yes'
        entry_image = request.files['entry_image']

        # Guardar imagen si se proporciona
        entry_image_path = None
        if entry_image and entry_image.filename != '':
            entry_image_filename = secure_filename(entry_image.filename)
            entry_image_path = os.path.join(app.config['UPLOAD_FOLDER'], entry_image_filename)
            entry_image.save(entry_image_path)

        # Insertar datos en la base de datos, incluyendo user_id
        cursor.execute('''INSERT INTO trades (user_id, notebook_id, asset, lot_size, entry_point, 
                        stop_loss, take_profit, result, trade_date, emotion, activation_routine, entry_image_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (user_id, notebook_id, asset, lot_size, entry_point, stop_loss, take_profit, result,
                        trade_date, emotion, activation_routine, entry_image_path))
        connection.commit()
        connection.close()

        flash('Trade registrado exitosamente.')
        return redirect(url_for('home'))

    # Obtener cuadernos para el selector
    cursor.execute('SELECT * FROM notebooks WHERE user_id = ?', (session['user_id'],))
    notebooks = cursor.fetchall()
    connection.close()

    return render_template('register_trade.html', notebooks=notebooks)

@app.route('/estadisticas')
def estadisticas():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Obtener información de los cuadernos para el selector
    cursor.execute("SELECT * FROM notebooks WHERE user_id = ?", (session['user_id'],))
    notebooks = cursor.fetchall()

    # Obtener los meses disponibles con trades
    cursor.execute("""
        SELECT DISTINCT strftime('%Y-%m', trade_date) as month
        FROM trades
        WHERE user_id = ?
        ORDER BY month DESC
    """, (session['user_id'],))
    months = [row['month'] for row in cursor.fetchall()]
    
    connection.close()

    return render_template('estadisticas.html', notebooks=notebooks, months=months, notebook_id=None)

@app.route('/obtener_meses', methods=['GET'])
def obtener_meses():
    notebook_id = request.args.get('notebook_id')

    if not notebook_id:
        return jsonify({"error": "No se proporcionó el ID del cuaderno"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    # Obtener los meses disponibles con trades para el cuaderno seleccionado
    cursor.execute("""
        SELECT DISTINCT strftime('%Y-%m', trade_date) as month
        FROM trades
        WHERE user_id = ? AND notebook_id = ?
        ORDER BY month DESC
    """, (session['user_id'], notebook_id))
    months = cursor.fetchall()
    connection.close()

    # Convertir los resultados en una lista de strings
    months_list = [row["month"] for row in months]

    return jsonify({"months": months_list})

@app.route('/cargar_datos_estadisticas', methods=['GET'])
def cargar_datos_estadisticas():
    notebook_id = request.args.get('notebook_id')
    mes = request.args.get('mes')

    if not notebook_id or not mes:
        return jsonify({"error": "No se proporcionó el ID del cuaderno o el mes"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    # Obtener capital inicial del cuaderno seleccionado
    cursor.execute("SELECT initial_balance FROM notebooks WHERE id = ? AND user_id = ?", (notebook_id, session['user_id']))
    notebook = cursor.fetchone()
    if not notebook:
        return jsonify({"error": "No se encontró el cuaderno seleccionado"}), 404

    initial_balance = notebook["initial_balance"]

    # Cálculo del capital en cuenta en base a cada trade, de forma acumulativa
    cursor.execute("""
        SELECT trade_date, result, entry_point, stop_loss, take_profit, lot_size, asset
        FROM trades
        WHERE notebook_id = ? AND user_id = ? AND strftime('%Y-%m', trade_date) = ?
        ORDER BY trade_date
    """, (notebook_id, session['user_id'], mes))
    
    trades = cursor.fetchall()
    dates = []
    capital = []

    current_balance = initial_balance
    for trade in trades:
        asset = trade["asset"].lower()
        lot_size = trade["lot_size"]
        entry_point = trade["entry_point"]
        take_profit = trade["take_profit"]
        stop_loss = trade["stop_loss"]

        # Ajustar las ganancias o pérdidas en función del tipo de índice y del tamaño del pip
        if "boom" in asset:  # Boom - Solo Compras
            if trade["result"] == "Ganadora":
                gain = (take_profit - entry_point) * lot_size
                current_balance += gain
            elif trade["result"] == "Perdedora":
                loss = (entry_point - stop_loss) * lot_size
                current_balance -= loss
        elif "crash" in asset:  # Crash - Solo Ventas
            if trade["result"] == "Ganadora":
                gain = (entry_point - take_profit) * lot_size
                current_balance += gain
            elif trade["result"] == "Perdedora":
                loss = (stop_loss - entry_point) * lot_size
                current_balance -= loss

        dates.append(trade["trade_date"])
        capital.append(current_balance)

    performance_data = {
        "dates": dates,
        "capital": capital
    }

    # Otros cálculos estadísticos
    cursor.execute("""
        SELECT result, COUNT(*) as count
        FROM trades
        WHERE user_id = ? AND notebook_id = ? AND strftime('%Y-%m', trade_date) = ?
        GROUP BY result
    """, (session['user_id'], notebook_id, mes))
    result_counts = cursor.fetchall()
    results_distribution = {
        "wins": sum(row["count"] for row in result_counts if row["result"] == "Ganadora"),
        "losses": sum(row["count"] for row in result_counts if row["result"] == "Perdedora")
    }

    cursor.execute("""
        SELECT 
            AVG(CASE WHEN result = 'Ganadora' AND asset LIKE 'boom%' THEN (take_profit - entry_point) * lot_size
                     WHEN result = 'Ganadora' AND asset LIKE 'crash%' THEN (entry_point - take_profit) * lot_size
                     ELSE NULL END) AS avg_gain,
            AVG(CASE WHEN result = 'Perdedora' AND asset LIKE 'boom%' THEN (entry_point - stop_loss) * lot_size
                     WHEN result = 'Perdedora' AND asset LIKE 'crash%' THEN (stop_loss - entry_point) * lot_size
                     ELSE NULL END) AS avg_loss
        FROM trades
        WHERE user_id = ? AND notebook_id = ? AND strftime('%Y-%m', trade_date) = ?
    """, (session['user_id'], notebook_id, mes))
    avg_data = cursor.fetchone()
    average_win_loss = {
        "avg_win": avg_data["avg_gain"] if avg_data["avg_gain"] is not None else 0,
        "avg_loss": avg_data["avg_loss"] if avg_data["avg_loss"] is not None else 0
    }

    cursor.execute("""
        SELECT strftime('%W', trade_date) AS week, SUM((CASE 
            WHEN result = 'Ganadora' AND asset LIKE 'boom%' THEN (take_profit - entry_point)
            WHEN result = 'Ganadora' AND asset LIKE 'crash%' THEN (entry_point - take_profit)
            WHEN result = 'Perdedora' AND asset LIKE 'boom%' THEN (entry_point - stop_loss) * -1
            WHEN result = 'Perdedora' AND asset LIKE 'crash%' THEN (stop_loss - entry_point) * -1
            END) * lot_size) AS profit
        FROM trades
        WHERE user_id = ? AND notebook_id = ? AND strftime('%Y-%m', trade_date) = ?
        GROUP BY week
    """, (session['user_id'], notebook_id, mes))
    weekly_performance_data = cursor.fetchall()
    weekly_performance = {
        "weeks": [row["week"] for row in weekly_performance_data],
        "profits": [row["profit"] for row in weekly_performance_data]
    }

    cursor.execute("""
        SELECT emotion, 
               COUNT(*) AS total, 
               ROUND(SUM(CASE WHEN result = 'Ganadora' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 2) AS success_rate
        FROM trades
        WHERE user_id = ? AND notebook_id = ? AND strftime('%Y-%m', trade_date) = ?
        GROUP BY emotion
    """, (session['user_id'], notebook_id, mes))
    emotion_data = cursor.fetchall()
    emotion_performance = {
        "emotions": [row["emotion"] for row in emotion_data],
        "success_rates": [row["success_rate"] for row in emotion_data]
    }

    # Nuevo cálculo: Activo más operado
    cursor.execute("""
        SELECT asset, COUNT(*) as total
        FROM trades
        WHERE user_id = ? AND notebook_id = ? AND strftime('%Y-%m', trade_date) = ?
        GROUP BY asset
        ORDER BY total DESC
    """, (session['user_id'], notebook_id, mes))
    asset_data = cursor.fetchall()
    asset_distribution = {
        "assets": [row["asset"] for row in asset_data],
        "counts": [row["total"] for row in asset_data]
    }

    connection.close()

    # Devolver datos como JSON
    data = {
        "performance_data": performance_data,
        "results_distribution": results_distribution,
        "average_win_loss": average_win_loss,
        "weekly_performance": weekly_performance,
        "emotion_performance": emotion_performance,
        "asset_distribution": asset_distribution,
    }

    print("Datos enviados al frontend:", data)
    
    return jsonify(data)

@app.route('/historial')
def historial():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Obtener todos los cuadernos para el selector de filtro
    cursor.execute("SELECT * FROM notebooks WHERE user_id = ?", (session['user_id'],))
    notebooks = cursor.fetchall()
    connection.close()

    return render_template('historial.html', notebooks=notebooks)

from flask import send_from_directory

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)

@app.route('/cargar_historial', methods=['GET'])
def cargar_historial():
    notebook_id = request.args.get('notebook_id')

    connection = get_db_connection()
    cursor = connection.cursor()

    # Consulta para obtener los trades según el filtro de cuaderno
    if notebook_id:
        cursor.execute("""
            SELECT t.*, n.name as notebook_name
            FROM trades t
            JOIN notebooks n ON t.notebook_id = n.id
            WHERE t.user_id = ? AND t.notebook_id = ?
            ORDER BY t.trade_date DESC
        """, (session['user_id'], notebook_id))
    else:
        cursor.execute("""
            SELECT t.*, n.name as notebook_name
            FROM trades t
            JOIN notebooks n ON t.notebook_id = n.id
            WHERE t.user_id = ?
            ORDER BY t.trade_date DESC
        """, (session['user_id'],))

    trades = cursor.fetchall()

    # Formatear los datos para devolver como JSON
    trade_list = []
    for trade in trades:
        # Calcular ganancia/pérdida
        if trade['result'] == 'Ganadora':
            profit_loss = abs((trade['take_profit'] - trade['entry_point']) * trade['lot_size']) if 'Boom' in trade['asset'] else abs((trade['entry_point'] - trade['take_profit']) * trade['lot_size'])
        elif trade['result'] == 'Perdedora':
            profit_loss = abs((trade['entry_point'] - trade['stop_loss']) * trade['lot_size']) if 'Boom' in trade['asset'] else abs((trade['stop_loss'] - trade['entry_point']) * trade['lot_size'])
        else:
            profit_loss = 0

        # Mostrar la ganancia/pérdida sin signos
        profit_loss_display = f"{profit_loss} USD"

        # Generar la URL manualmente
        image_url = f"/static/uploads/{trade['entry_image_path']}" if trade["entry_image_path"] else None
        trade_list.append({
            "notebook_name": trade["notebook_name"],
            "asset": trade["asset"],
            "lot_size": trade["lot_size"],
            "entry_point": trade["entry_point"],
            "stop_loss": trade["stop_loss"],
            "take_profit": trade["take_profit"],
            "result": trade["result"],
            "trade_date": trade["trade_date"],
            "emotion": trade["emotion"],
            "activation_routine": "Sí" if str(trade["activation_routine"]).lower() in ["sí", "si", "yes", "1"] else "No",
            "profit_loss": profit_loss_display,
            "entry_image_url": image_url  # Aquí pasamos la URL manual sin usar url_for
        })

    connection.close()

    return jsonify({"trades": trade_list})

@app.route('/eliminar_cuaderno', methods=['POST'])
def eliminar_cuaderno():
    notebook_id = request.form.get('notebook_id')

    if not notebook_id:
        return jsonify({"error": "No se proporcionó un cuaderno para eliminar."}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    # Eliminar todos los registros relacionados con el cuaderno
    cursor.execute("DELETE FROM trades WHERE notebook_id = ?", (notebook_id,))
    cursor.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))

    connection.commit()
    connection.close()

    return jsonify({"success": "Cuaderno eliminado correctamente."})

import json
import websocket
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from flask import Flask, render_template, request, jsonify, send_file, session
from scipy.signal import find_peaks
import threading
import os
import uuid
from datetime import datetime, timedelta

# Configurar backend de matplotlib para evitar problemas con tkinter
plt.switch_backend('Agg')

app.secret_key = 'clave_super_secreta'  # Necesario para la sesión

indices_sinteticos = {
    "1": "BOOM1000",
    "2": "BOOM500",
    "3": "BOOM300N",
    "4": "CRASH1000",
    "5": "CRASH500",
    "6": "CRASH300N",
}

# Ruta para el módulo de scripts
@app.route('/scripts')
def scripts():
    # Borrar la imagen previa si existe
    if 'grafico' in session:
        try:
            os.remove(session['grafico'])
        except FileNotFoundError:
            pass
        session.pop('grafico', None)

    return render_template('scripts.html', indices_sinteticos=indices_sinteticos)

# Ruta para ejecutar el script de análisis
@app.route('/ejecutar_script', methods=['POST'])
def ejecutar_script():
    try:
        data = request.get_json()
        indice_seleccionado = data.get("indice")
        api_token = data.get("api_token")

        if not indice_seleccionado or not api_token:
            return jsonify({"error": "No se seleccionó un índice o no se proporcionó el token de API."}), 400

        # Generar un nombre de archivo único para el gráfico
        img_filename = f"static/img/grafico_{uuid.uuid4().hex}.png"
        session['grafico'] = img_filename

        # Ejecutar la conexión en un hilo separado para evitar que se bloquee la respuesta
        thread = threading.Thread(target=conectar_y_analizar_indice, args=(api_token, indice_seleccionado, img_filename))
        thread.start()

        return jsonify({"success": "Análisis en proceso. Puedes ver el gráfico cuando esté listo."})
    except Exception as e:
        print(f"Error en /ejecutar_script: {str(e)}")
        return jsonify({"error": "Hubo un error al ejecutar el script. Verifica los datos ingresados y vuelve a intentarlo."}), 500

def conectar_y_analizar_indice(api_token, indice_sintetico, img_filename):
    try:
        ws = websocket.WebSocketApp("wss://ws.binaryws.com/websockets/v3?app_id=64422",
                                    on_open=lambda ws: on_open_wrapper(ws, api_token, indice_sintetico),
                                    on_message=lambda ws, message: on_message(ws, message, img_filename, indice_sintetico),
                                    on_error=on_error,
                                    on_close=on_close)
        ws.run_forever(ping_interval=30, ping_timeout=10)
    except Exception as e:
        print(f"Error al conectar y analizar índice: {str(e)}")

def on_open_wrapper(ws, api_token, indice_sintetico):
    try:
        # Autenticación con el API token
        auth_request = {
            "authorize": api_token
        }
        ws.send(json.dumps(auth_request))
    except Exception as e:
        print(f"Error en on_open_wrapper: {str(e)}")

def on_message(ws, message, img_filename, indice_sintetico):
    try:
        data = json.loads(message)
        if 'error' in data:
            print(f"Error en la API: {data['error']['message']}")
        elif 'authorize' in data:
            print(f"Autenticación exitosa para el usuario {data['authorize']['loginid']}")
            # Después de la autenticación exitosa, enviar la solicitud de datos del índice
            obtener_datos_indice_sintetico(ws, indice_sintetico)
        elif 'candles' in data:
            analizar_indice(data['candles'], img_filename)
        else:
            print("Respuesta inesperada de la API:", json.dumps(data, indent=4))
    except Exception as e:
        print(f"Error en on_message: {str(e)}")

def on_error(ws, error):
    print(f"Error en la conexión: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Conexión WebSocket cerrada con código: {close_status_code} y mensaje: {close_msg}")

def obtener_datos_indice_sintetico(ws, symbol):
    try:
        # Obtener la fecha de hace 24 horas
        fecha_24_horas_atras = int((datetime.now() - timedelta(hours=24)).timestamp())

        request_data = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 24,  # 24 velas para 24 horas (una por hora)
            "end": "latest",
            "start": fecha_24_horas_atras,
            "style": "candles",
            "granularity": 3600  # Granularidad de 1 hora para que se vean 24 velas en total
        }
        print(f"Enviando solicitud para el índice: {symbol}")
        ws.send(json.dumps(request_data))
    except Exception as e:
        print(f"Error en obtener_datos_indice_sintetico: {str(e)}")

def analizar_indice(candles, img_filename):
    try:
        # Convertir los datos a un formato que pueda ser utilizado por mplfinance
        ohlc_data = {
            'Date': [pd.to_datetime(candle['epoch'], unit='s') for candle in candles],
            'Open': [candle['open'] for candle in candles],
            'High': [candle['high'] for candle in candles],
            'Low': [candle['low'] for candle in candles],
            'Close': [candle['close'] for candle in candles]
        }
        df = pd.DataFrame(ohlc_data)
        df.set_index('Date', inplace=True)

        # Detectar máximos y mínimos no cortados
        prices = df['Close'].values
        peaks, _ = find_peaks(prices, distance=2)
        min_peaks, _ = find_peaks(-prices, distance=2)

        # Crear el gráfico de velas japonesas con mplfinance
        mc = mpf.make_marketcolors(up='g', down='r', wick={'up': 'g', 'down': 'r'}, edge={'up': 'g', 'down': 'r'})
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=False)

        fig, axlist = mpf.plot(df, type='candle', style=s, returnfig=True, figsize=(14, 8))

        # Graficar los máximos y mínimos no cortados
        ax = axlist[0]  # Obtener el eje principal de la gráfica
        ax.scatter(df.index[peaks], df['High'].iloc[peaks], color='red', s=50, label='Máximos sin cortar', alpha=0.8)
        ax.scatter(df.index[min_peaks], df['Low'].iloc[min_peaks], color='green', s=50, label='Mínimos sin cortar', alpha=0.8)

        # Configurar leyenda
        ax.legend()

        # Guardar la imagen
        plt.savefig(img_filename, format='png', bbox_inches='tight', dpi=200)
        plt.close()
    except Exception as e:
        print(f"Error en analizar_indice: {str(e)}")

@app.route('/mostrar_grafico')
def mostrar_grafico():
    # Devolver la imagen generada al frontend
    if 'grafico' in session and os.path.exists(session['grafico']):
        return send_file(session['grafico'], mimetype='image/png')
    else:
        return "Gráfico no disponible.", 404


# Rutas para el gráfico en vivo
@app.route('/inicio')
def inicio():
    return render_template('inicio.html', indices_sinteticos=indices_sinteticos)

@app.route('/datos_grafico')
def datos_grafico():
    indice = request.args.get('indice')
    temporalidad = request.args.get('temporalidad', type=int)

    if not indice or not temporalidad:
        return jsonify({"error": "No se proporcionó un índice o temporalidad."}), 400

    try:
        # Obtener datos del índice desde la API según la temporalidad
        datos = obtener_datos_indice_vivo(indice, temporalidad)
        if datos is None:
            return jsonify({"error": "Error al obtener datos del índice."}), 500

        tiempos = [pd.to_datetime(candle['epoch'], unit='s').strftime('%Y-%m-%d %H:%M:%S') for candle in datos]
        open_prices = [candle['open'] for candle in datos]
        high_prices = [candle['high'] for candle in datos]
        low_prices = [candle['low'] for candle in datos]
        close_prices = [candle['close'] for candle in datos]

        return jsonify({"tiempos": tiempos, "open": open_prices, "high": high_prices, "low": low_prices, "close": close_prices})
    except Exception as e:
        print(f"Error en /datos_grafico: {str(e)}")
        return jsonify({"error": "Hubo un error al obtener los datos del gráfico."}), 500

def obtener_datos_indice_vivo(symbol, granularity):
    try:
        # Obtener la fecha de un mes atrás
        fecha_mes_atras = int((datetime.now() - timedelta(days=30)).timestamp())

        # Conexión WebSocket para obtener datos históricos
        ws = websocket.create_connection("wss://ws.binaryws.com/websockets/v3?app_id=64422")
        request_data = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 5000,  # Cantidad aumentada para obtener más datos
            "end": "latest",
            "start": fecha_mes_atras,
            "style": "candles",
            "granularity": granularity * 60  # Temporalidad en segundos (M1 = 60, M5 = 300, etc.)
        }
        ws.send(json.dumps(request_data))
        response = ws.recv()
        data = json.loads(response)
        ws.close()

        if 'candles' in data:
            return data['candles']
        else:
            return None
    except Exception as e:
        print(f"Error al obtener datos del índice: {str(e)}")
        return None

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)

