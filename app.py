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

    # Agregar el saldo inicial como el primer punto del gráfico
    dates.append("Inicio")
    capital.append(initial_balance)

    # Continuar con las operaciones acumulativas
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

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, send_from_directory
import json
import websocket
import pandas as pd
import datetime


# Historial de cuadernos y trades
@app.route('/historial')
def historial():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Obtener todos los cuadernos para el selector de filtro
    cursor.execute("SELECT * FROM notebooks WHERE user_id = ?", (session['user_id'],))
    notebooks = cursor.fetchall()
    connection.close()

    return render_template('historial.html', notebooks=notebooks)

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
            "trade_id": trade["id"],
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

@app.route('/eliminar_trade', methods=['POST'])
def eliminar_trade():
    trade_id = request.form.get('trade_id')
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM trades WHERE id = ? AND user_id = ?", (trade_id, session['user_id']))
    connection.commit()
    connection.close()
    return jsonify({"success": "El trade ha sido eliminado con éxito."})

@app.route('/modificar_trade/<int:trade_id>', methods=['GET', 'POST'])
def modificar_trade(trade_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        # Obtener los nuevos datos del formulario
        updated_data = {
            "asset": request.form.get("asset"),
            "lot_size": request.form.get("lot_size"),
            "entry_point": request.form.get("entry_point"),
            "stop_loss": request.form.get("stop_loss"),
            "take_profit": request.form.get("take_profit"),
            "result": request.form.get("result"),
            "emotion": request.form.get("emotion"),
            "activation_routine": request.form.get("activation_routine")
        }
        
        # Actualizar el trade en la base de datos
        cursor.execute("""
            UPDATE trades
            SET asset = ?, lot_size = ?, entry_point = ?, stop_loss = ?, take_profit = ?, result = ?, emotion = ?, activation_routine = ?
            WHERE id = ? AND user_id = ?
        """, (*updated_data.values(), trade_id, session['user_id']))
        connection.commit()
        connection.close()
        return redirect(url_for('historial'))

    # Si es GET, obtener los datos actuales del trade
    cursor.execute("SELECT * FROM trades WHERE id = ? AND user_id = ?", (trade_id, session['user_id']))
    trade = cursor.fetchone()
    connection.close()

    return render_template('modificar_trade.html', trade=trade)



from flask import send_file
import pandas as pd

import os

@app.route('/descargar_historial', methods=['GET'])
def descargar_historial():
    try:
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
        connection.close()

        # Verificar si se obtuvieron resultados
        if not trades:
            return jsonify({"error": "No hay datos disponibles para descargar."}), 404

        # Definir los nombres de las columnas en el orden correcto
        columnas = [
            'Cuaderno', 'Activo Operado', 'Lotaje Operado', 'Punto de Entrada',
            'Stop Loss', 'Take Profit', 'Resultado de la Operación',
            'Fecha de la Operación', 'Emoción al Operar',
            '¿Realizaste la rutina de activación?', 'Ganancia / Pérdida', 'Imagen de Entrada'
        ]

        # Preparar los datos en el orden adecuado para el DataFrame
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
            image_url = trade["entry_image_path"] if trade["entry_image_path"] else 'N/A'

            trade_list.append([
                trade["notebook_name"], trade["asset"], trade["lot_size"],
                trade["entry_point"], trade["stop_loss"], trade["take_profit"],
                trade["result"], trade["trade_date"], trade["emotion"],
                "Sí" if str(trade["activation_routine"]).lower() in ["sí", "si", "yes", "1"] else "No",
                profit_loss_display, image_url
            ])

        # Crear el DataFrame con los nombres de las columnas adecuados
        df = pd.DataFrame(trade_list, columns=columnas)

        # Imprimir la estructura del DataFrame para depuración
        print("Estructura del DataFrame antes de exportar a Excel:")
        print(df.head())

        if df.empty:
            print("El DataFrame está vacío después de crear desde la consulta.")
            return jsonify({"error": "El DataFrame está vacío."}), 500

        # Guardar el archivo Excel en el directorio 'static/uploads'
        uploads_dir = os.path.join(app.root_path, 'static/uploads')
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)
        excel_path = os.path.join(uploads_dir, 'historial_trades.xlsx')
        df.to_excel(excel_path, index=False)

        # Enviar el archivo Excel al usuario
        return send_file(excel_path, as_attachment=True, download_name='historial_trades.xlsx')

    except Exception as e:
        print(f"Error al descargar el historial: {str(e)}")
        return jsonify({"error": "Hubo un error al descargar el historial."}), 500


    

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
        # Obtener la fecha de hace 12 horas
        fecha_12_horas_atras = int((datetime.now() - timedelta(hours=12)).timestamp())

        request_data = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 500,  # Más datos para mejorar la detección de máximos y mínimos
            "end": "latest",
            "start": fecha_12_horas_atras,
            "style": "candles",
            "granularity": 1800  # Granularidad de 30 minutos
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

        # Detectar máximos y mínimos que no han sido cortados
        high_prices = df['High']
        low_prices = df['Low']
        close_prices = df['Close']

        # Detectar los picos máximos y mínimos
        max_peaks, _ = find_peaks(high_prices, distance=3)
        min_peaks, _ = find_peaks(-low_prices, distance=3)

        # Filtrar los máximos y mínimos que no han sido rotos por el precio de cierre
        max_not_broken = [peak for peak in max_peaks if high_prices.iloc[peak] > max(close_prices.iloc[peak:])]
        min_not_broken = [valley for valley in min_peaks if low_prices.iloc[valley] < min(close_prices.iloc[valley:])]

        # Crear el gráfico de velas japonesas con mplfinance
        mc = mpf.make_marketcolors(up='g', down='r', wick='i', edge='i')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=False)

        fig, axlist = mpf.plot(df, type='candle', style=s, returnfig=True, figsize=(14, 8))

        # Añadir líneas horizontales para máximos y mínimos no cortados
        ax = axlist[0]  # Obtener el eje principal de la gráfica
        for peak in max_not_broken:
            ax.axhline(y=high_prices.iloc[peak], color='blue', linestyle='--', linewidth=1, alpha=0.6, label='Máximo sin cortar' if peak == max_not_broken[0] else "")

        for valley in min_not_broken:
            ax.axhline(y=low_prices.iloc[valley], color='purple', linestyle='--', linewidth=1, alpha=0.6, label='Mínimo sin cortar' if valley == min_not_broken[0] else "")

        # Configurar leyenda para mostrar solo una vez
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys())

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

# Módulo de Gestión de Riesgo

from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import numpy as np
import sqlite3


app.secret_key = 'clave_super_secreta'

def get_db_connection():
    connection = sqlite3.connect('trading_system.db')
    connection.row_factory = sqlite3.Row
    return connection

# Ruta para mostrar el módulo de Gestión de Riesgo
@app.route('/gestion_riesgo')
def gestion_riesgo():
    return render_template('gestion_riesgo.html')

# Cálculo de lotaje basado en riesgo fijo
@app.route('/calcular_lotaje', methods=['POST'])
def calcular_lotaje():
    try:
        # Datos de entrada
        balance = request.form.get('balance', type=float)
        riesgo_por_trade = request.form.get('riesgo_por_trade', type=float)  # Riesgo en porcentaje
        stop_loss_pips = request.form.get('stop_loss_pips', type=float)
        valor_por_pip = request.form.get('valor_por_pip', type=float)

        # Cálculo del riesgo en USD
        riesgo_usd = (balance * (riesgo_por_trade / 100))

        # Cálculo del lotaje
        lotaje = riesgo_usd / (stop_loss_pips * valor_por_pip)

        return jsonify({"lotaje": round(lotaje, 2)})
    except Exception as e:
        print(f"Error al calcular lotaje: {str(e)}")
        return jsonify({"error": "Hubo un error al calcular el lotaje."}), 500

# Cálculo del nivel de exposición total y diversificación
@app.route('/nivel_exposicion', methods=['GET'])
def nivel_exposicion():
    try:
        user_id = session['user_id']
        connection = get_db_connection()
        cursor = connection.cursor()

        # Obtener todas las operaciones abiertas del usuario
        cursor.execute("SELECT asset, lot_size, entry_point FROM trades WHERE user_id = ? AND status = 'Abierta'", (user_id,))
        trades = cursor.fetchall()
        connection.close()

        # Calcular la exposición total por activo
        exposicion_por_activo = {}
        for trade in trades:
            asset = trade['asset']
            lot_size = trade['lot_size']
            exposicion_por_activo[asset] = exposicion_por_activo.get(asset, 0) + lot_size

        exposicion_total = sum(exposicion_por_activo.values())

        return jsonify({"exposicion_por_activo": exposicion_por_activo, "exposicion_total": exposicion_total})
    except Exception as e:
        print(f"Error al calcular el nivel de exposición: {str(e)}")
        return jsonify({"error": "Hubo un error al calcular el nivel de exposición."}), 500

# Análisis de Drawdown
@app.route('/analisis_drawdown', methods=['GET'])
def analisis_drawdown():
    try:
        user_id = session['user_id']
        connection = get_db_connection()
        cursor = connection.cursor()

        # Obtener el historial de capital de la cuenta del usuario
        cursor.execute("SELECT trade_date, capital FROM capital_history WHERE user_id = ? ORDER BY trade_date", (user_id,))
        capital_data = cursor.fetchall()
        connection.close()

        if not capital_data:
            return jsonify({"error": "No hay datos de capital disponibles."}), 404

        # Convertir los datos en un DataFrame para realizar el análisis
        df = pd.DataFrame(capital_data, columns=['trade_date', 'capital'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df.set_index('trade_date', inplace=True)

        # Cálculo del drawdown
        capital_max = df['capital'].cummax()
        drawdown = (capital_max - df['capital']) / capital_max
        drawdown_actual = drawdown.iloc[-1]
        drawdown_maximo = drawdown.max()

        # Convertir datos para la visualización del gráfico
        fechas = df.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
        balances = df['capital'].tolist()
        drawdowns = (drawdown * 100).tolist()

        return jsonify({
            "drawdown_actual": round(drawdown_actual * 100, 2),
            "drawdown_maximo": round(drawdown_maximo * 100, 2),
            "fechas": fechas,
            "balances": balances,
            "drawdowns": drawdowns
        })
    except Exception as e:
        print(f"Error al realizar el análisis de drawdown: {str(e)}")
        return jsonify({"error": "Hubo un error al realizar el análisis de drawdown."}), 500

from flask import Flask, render_template, jsonify, request, session
import pandas as pd
import os
import sqlite3

app.secret_key = 'secret_key'

@app.route('/gamificacion', methods=['GET', 'POST'])
def gamificacion():
    try:
        user_id = session['user_id']
        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == 'POST':
            selected_month = request.form['selected_month']
            
            # Obtener el historial de trades para el mes seleccionado
            cursor.execute("""
                SELECT result, lot_size, entry_point, take_profit, stop_loss, trade_date, emotion
                FROM trades 
                WHERE user_id = ? AND strftime('%Y-%m', trade_date) = ?
                ORDER BY trade_date
            """, (user_id, selected_month))
            trades = cursor.fetchall()

            if not trades:
                return jsonify({"error": "No hay datos disponibles para el mes seleccionado."}), 404

            # Crear estructura de gamificación
            metas = [
                {"id": 1, "descripcion": "Conseguir 3 operaciones ganadoras consecutivas", "cumplida": False, "progreso": 0},
                {"id": 2, "descripcion": "Lograr un 20% de rentabilidad en un mes", "cumplida": False, "progreso": 0},
                {"id": 3, "descripcion": "Gestionar mejor mis emociones al operar", "cumplida": False, "progreso": 0},
                {"id": 4, "descripcion": "Registrar cada trade correctamente por 1 mes", "cumplida": False, "progreso": 0},
                {"id": 5, "descripcion": "Mantener un drawdown inferior al 5% durante un mes", "cumplida": False, "progreso": 0}
            ]

            # Variables auxiliares para calcular el progreso de las metas
            consecutivas_ganadoras = 0
            total_trades = len(trades)
            ganancia_total = 0
            drawdown_maximo = 0
            emociones_positivas = ["Confianza", "Tranquilidad"]
            emociones_positivas_count = 0

            # Análisis de los trades
            for trade in trades:
                # Meta 1: Conseguir 3 operaciones ganadoras consecutivas
                if trade['result'] == 'Ganadora':
                    consecutivas_ganadoras += 1
                else:
                    consecutivas_ganadoras = 0

                if consecutivas_ganadoras >= 3:
                    metas[0]['cumplida'] = True
                    metas[0]['progreso'] = 100
                else:
                    metas[0]['progreso'] = min((consecutivas_ganadoras / 3) * 100, 100)

                # Meta 2: Lograr un 20% de rentabilidad en un mes (simple aproximación)
                if trade['result'] == 'Ganadora':
                    ganancia_total += abs(trade['take_profit'] - trade['entry_point']) * trade['lot_size']
                elif trade['result'] == 'Perdedora':
                    ganancia_total -= abs(trade['entry_point'] - trade['stop_loss']) * trade['lot_size']

                # Meta 3: Gestionar mejor mis emociones (contar emociones positivas)
                if trade['emotion'] in emociones_positivas:
                    emociones_positivas_count += 1

            # Rentabilidad del 20%
            rentabilidad_porcentaje = (ganancia_total / (trades[0]['entry_point'] * trades[0]['lot_size'])) * 100
            metas[1]['progreso'] = min(max((rentabilidad_porcentaje / 20) * 100, 0), 100)
            if rentabilidad_porcentaje >= 20:
                metas[1]['cumplida'] = True

            # Emociones positivas durante el mes
            metas[2]['progreso'] = min((emociones_positivas_count / total_trades) * 100, 100)
            if metas[2]['progreso'] >= 80:
                metas[2]['cumplida'] = True

            # Meta 4: Registrar cada trade correctamente por 1 mes
            metas[3]['progreso'] = min((total_trades / 30) * 100, 100)
            if total_trades >= 30:
                metas[3]['cumplida'] = True

            # Meta 5: Mantener un drawdown inferior al 5% durante un mes (simplificado)
            drawdown_maximo = max(0.05 - (ganancia_total / total_trades), 0)
            metas[4]['progreso'] = min((1 - drawdown_maximo) * 100, 100)
            if drawdown_maximo <= 0.05:
                metas[4]['cumplida'] = True

            return render_template('gamificacion.html', metas=metas, selected_month=selected_month)

        else:
            # Obtener los meses disponibles en los que se han realizado operaciones
            cursor.execute("""
                SELECT DISTINCT strftime('%Y-%m', trade_date) as month
                FROM trades
                WHERE user_id = ?
                ORDER BY month DESC
            """, (user_id,))
            months = [row['month'] for row in cursor.fetchall()]

            connection.close()

            return render_template('gamificacion.html', months=months)

    except Exception as e:
        print(f"Error en el módulo de gamificación: {str(e)}")
        return jsonify({"error": "Hubo un error en el módulo de gamificación."}), 500



from flask import Flask, render_template, jsonify, request
import json
import websocket
import pandas as pd
import datetime

indices_sinteticos = {
    "1": "BOOM1000",
    "2": "BOOM500",
    "3": "BOOM300N",
    "4": "CRASH1000",
    "5": "CRASH500",
    "6": "CRASH300N",
}

@app.route('/estrategias', methods=['GET'])
def estrategias():
    temporalidades = [
        {"value": 1, "label": "1 minuto"},
        {"value": 5, "label": "5 minutos"},
        {"value": 15, "label": "15 minutos"},
        {"value": 30, "label": "30 minutos"},
    ]
    return render_template('estrategias.html', indices_sinteticos=indices_sinteticos, temporalidades=temporalidades)

@app.route('/ejecutar_estrategias', methods=['POST'])
def ejecutar_estrategias():
    try:
        activo_seleccionado = request.form.get("indice")
        temporalidad = int(request.form.get("temporalidad"))
        if not activo_seleccionado or not temporalidad:
            return jsonify({"error": "No se seleccionó un índice o una temporalidad"}), 400

        activo = indices_sinteticos.get(activo_seleccionado)
        if not activo:
            return jsonify({"error": "Índice no válido"}), 400

        resultados = []

        # Ejecutar Estrategia de Caza de Spikes
        resultado_spike, razon, tiempo_estimado = check_spike_hunting_strategy(activo, temporalidad)
        if resultado_spike:
            resultados.append(resultado_spike)
        else:
            resultados.append({
                "strategy_name": "Caza de Spikes", 
                "asset": activo, 
                "status": "No se encontró oportunidad",
                "reason": razon,
                "estimated_time": tiempo_estimado
            })
        print(f"Resultado Caza de Spikes: {resultado_spike if resultado_spike else razon}")

        # Guardar los resultados en una variable global para obtenerlos luego
        app.config['ULTIMAS_OPORTUNIDADES'] = resultados

        return jsonify({"message": "Las estrategias se están ejecutando. Verifica los resultados en unos segundos."})

    except Exception as e:
        print(f"Error al ejecutar las estrategias: {str(e)}")
        return jsonify({"error": f"Hubo un error al ejecutar las estrategias: {str(e)}"}), 500

@app.route('/resultado_estrategias', methods=['GET'])
def resultado_estrategias():
    resultados = app.config.get('ULTIMAS_OPORTUNIDADES', [])
    return jsonify({"resultados": resultados})

@app.route('/logs_estrategias', methods=['GET'])
def logs_estrategias():
    logs = app.config.get('LOGS_ESTRATEGIAS', [])
    return jsonify({"logs": logs})

def obtener_datos_indice_vivo(symbol, granularity):
    try:
        # Obtener la fecha de un mes atrás
        fecha_mes_atras = int((datetime.datetime.now() - datetime.timedelta(days=30)).timestamp())

        # Conexión WebSocket para obtener datos históricos
        ws = websocket.create_connection("wss://ws.binaryws.com/websockets/v3?app_id=64422")
        request_data = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 100,  # Cantidad de datos para analizar
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
            return pd.DataFrame(data['candles'])
        else:
            return pd.DataFrame()
    except Exception as e:
        print(f"Error al obtener datos del índice: {str(e)}")
        return pd.DataFrame()

# Estrategia de Caza de Spikes
def check_spike_hunting_strategy(asset, temporalidad):
    df = obtener_datos_indice_vivo(asset, temporalidad)
    if df.empty:
        log_estrategia("Caza de Spikes", asset, "Datos insuficientes para el análisis")
        return None, "Datos insuficientes para el análisis", "Próxima revisión en 15 minutos"

    # Calcular Soportes y Resistencias
    soporte = df['low'].rolling(window=20).min().iloc[-1]
    resistencia = df['high'].rolling(window=20).max().iloc[-1]

    # Calcular Retrocesos de Fibonacci
    max_price = df['high'].max()
    min_price = df['low'].min()
    df['fibonacci_38'] = min_price + (max_price - min_price) * 0.382
    df['fibonacci_61'] = min_price + (max_price - min_price) * 0.618

    # Calcular RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Calcular EMA de 200
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()

    # Log de detalles del análisis
    log_estrategia("Caza de Spikes", asset, f"Soporte: {soporte}, Resistencia: {resistencia}, RSI: {df['RSI'].iloc[-1]}, EMA_200: {df['EMA_200'].iloc[-1]}, Precio actual: {df['close'].iloc[-1]}")

    # Condiciones de entrada
    entry_point = df['close'].iloc[-1]
    if "CRASH" in asset:
        if (entry_point >= resistencia or entry_point >= df['fibonacci_61'].iloc[-1]) and df['RSI'].iloc[-1] > 75 and entry_point < df['EMA_200'].iloc[-1]:
            log_estrategia("Caza de Spikes", asset, "Condiciones cumplidas para entrada en venta")
            return calcular_puntos_entrada("Caza de Spikes - Crash", asset, df), None, None
        else:
            razon = "No se cumplen las condiciones de resistencia, RSI o EMA para una entrada en venta"
            tiempo_estimado = calcular_tiempo_estimado(temporalidad)
            log_estrategia("Caza de Spikes", asset, razon)
            return None, razon, tiempo_estimado
    elif "BOOM" in asset:
        if (entry_point <= soporte or entry_point <= df['fibonacci_38'].iloc[-1]) and df['RSI'].iloc[-1] < 25 and entry_point > df['EMA_200'].iloc[-1]:
            log_estrategia("Caza de Spikes", asset, "Condiciones cumplidas para entrada en compra")
            return calcular_puntos_entrada("Caza de Spikes - Boom", asset, df), None, None
        else:
            razon = "No se cumplen las condiciones de soporte, RSI o EMA para una entrada en compra"
            tiempo_estimado = calcular_tiempo_estimado(temporalidad)
            log_estrategia("Caza de Spikes", asset, razon)
            return None, razon, tiempo_estimado

    log_estrategia("Caza de Spikes", asset, "Condiciones de activo no reconocidas")
    return None, "Condiciones de activo no reconocidas", "Próxima revisión en 15 minutos"

# Función auxiliar para calcular TP y SL de acuerdo al tipo de activo
def calcular_puntos_entrada(strategy_name, asset, df, soporte=None, resistencia=None):
    entry_point = df['close'].iloc[-1]

    # Ajustar la relación riesgo-beneficio y gestionar el tamaño de posición
    if "CRASH" in asset:
        stop_loss = entry_point + 15
        take_profit = entry_point - 20
    elif "BOOM" in asset:
        stop_loss = entry_point - 15
        take_profit = entry_point + 20
    else:
        return None

    # Filtrar operaciones donde la relación TP/SL no es al menos de 1.5:1
    if abs(take_profit - entry_point) / abs(entry_point - stop_loss) < 1.5:
        log_estrategia(strategy_name, asset, "La relación TP/SL no es favorable (menor a 1.5:1)")
        return None

    return {
        "strategy_name": strategy_name,
        "asset": asset,
        "entry_point": entry_point,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "win_rate": 75,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# Función auxiliar para calcular el tiempo estimado para la próxima oportunidad
def calcular_tiempo_estimado(temporalidad):
    ahora = datetime.datetime.now()
    minutos_extra = temporalidad * 2
    proxima_revision = ahora + datetime.timedelta(minutes=minutos_extra)
    return proxima_revision.strftime("%H:%M")

# Función auxiliar para registrar logs de las estrategias
def log_estrategia(strategy_name, asset, message):
    log_message = {
        "strategy_name": strategy_name,
        "asset": asset,
        "message": message,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if 'LOGS_ESTRATEGIAS' not in app.config:
        app.config['LOGS_ESTRATEGIAS'] = []
    app.config['LOGS_ESTRATEGIAS'].append(log_message)

from flask import Flask, render_template, jsonify, request, redirect, url_for
import sqlite3
from config import DB_PATH

# Definición de meses y hábitos
meses = {
    "1": "Enero", "2": "Febrero", "3": "Marzo", "4": "Abril", "5": "Mayo", "6": "Junio",
    "7": "Julio", "8": "Agosto", "9": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
}
habitos = [
    "Ir al GYM", "Meditar", "NDP", "Vida social", "Estado de ánimo",
    "Relación familiar", "Lectura", "Inglés", "Trabajo", "Trading"
]


@app.route('/control_habitos', methods=['GET'])
def control_habitos():
    return render_template('control_habitos.html', meses=meses, habitos=habitos)

@app.route('/habitos/<mes>', methods=['GET'])
def obtener_habitos(mes):
    try:
        user_id = 1
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        cursor.execute('''
            SELECT habito, dia, cumplido FROM habitos WHERE user_id = ? AND mes = ?
        ''', (user_id, mes))
        registros = cursor.fetchall()

        habitos_data = {}
        for habito, dia, cumplido in registros:
            if habito not in habitos_data:
                habitos_data[habito] = []
            habitos_data[habito].append({"dia": dia, "cumplido": cumplido})

        habitos_list = [{"nombre": habito, "dias": dias} for habito, dias in habitos_data.items()]

        return jsonify({"habitos": habitos_list})
    except Exception as e:
        print(f"Error al obtener hábitos: {str(e)}")
        return jsonify({"error": "Error al obtener hábitos"}), 500
    finally:
        connection.close()

@app.route('/habitos/<mes>/actualizar', methods=['POST'])
def actualizar_habito(mes):
    try:
        user_id = 1
        data = request.get_json()
        habito = data.get("habito")
        dia = data.get("dia")

        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        cursor.execute('''
            SELECT id FROM habitos WHERE user_id = ? AND mes = ? AND habito = ? AND dia = ?
        ''', (user_id, mes, habito, dia))
        registro = cursor.fetchone()

        if registro:
            cursor.execute('''
                UPDATE habitos SET cumplido = NOT cumplido WHERE id = ?
            ''', (registro[0],))
        else:
            cursor.execute('''
                INSERT INTO habitos (user_id, mes, habito, dia, cumplido) VALUES (?, ?, ?, ?, ?)
            ''', (user_id, mes, habito, dia, True))

        connection.commit()
        return jsonify({"message": "Hábito actualizado correctamente"})
    except Exception as e:
        print(f"Error al actualizar hábito: {str(e)}")
        return jsonify({"error": "Error al actualizar hábito"}), 500
    finally:
        connection.close()

@app.route('/estadisticas_habitos/<mes>', methods=['GET'])
def estadisticas_habitos(mes):
    try:
        user_id = 1
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        cursor.execute('''
            SELECT habito, COUNT(*) as cumplidos FROM habitos WHERE user_id = ? AND mes = ? AND cumplido = 1 GROUP BY habito
        ''', (user_id, mes))
        registros = cursor.fetchall()

        habitos_data = [{"nombre": registro[0], "cumplimiento": registro[1]} for registro in registros]

        return render_template("estadisticas_habitos.html", habitos=habitos_data, mes=meses.get(mes, ""))
    except Exception as e:
        print(f"Error al obtener estadísticas: {str(e)}")
        return jsonify({"error": "Error al obtener estadísticas"}), 500
    finally:
        connection.close()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)



 








