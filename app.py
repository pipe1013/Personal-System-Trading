import os
import sqlite3
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
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

if __name__ == '__main__':
    app.run(debug=True)
