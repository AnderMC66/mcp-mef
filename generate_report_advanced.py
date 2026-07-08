import sqlite3
import json

def fetch_data():
    conn = sqlite3.connect('mef_data.db')
    cursor = conn.cursor()
    
    # 1. Total por mes
    cursor.execute('''
        SELECT MES_DOC, SUM(CAST(MONTO_RECAUDADO AS REAL)) AS Total 
        FROM canon_minero 
        WHERE MES_DOC IS NOT NULL AND MES_DOC != ''
        GROUP BY MES_DOC 
        ORDER BY CAST(MES_DOC AS INT)
    ''')
    por_mes = cursor.fetchall()
    
    # 2. Top 10 departamentos
    cursor.execute('''
        SELECT DEPARTAMENTO_EJECUTORA_NOMBRE, SUM(CAST(MONTO_RECAUDADO AS REAL)) AS Total 
        FROM canon_minero 
        WHERE DEPARTAMENTO_EJECUTORA_NOMBRE IS NOT NULL AND DEPARTAMENTO_EJECUTORA_NOMBRE != ''
        GROUP BY DEPARTAMENTO_EJECUTORA_NOMBRE 
        ORDER BY Total DESC 
        LIMIT 10
    ''')
    top_deptos = cursor.fetchall()
    
    # 3. Top 15 Municipalidades
    cursor.execute('''
        SELECT EJECUTORA_NOMBRE, SUM(CAST(MONTO_RECAUDADO AS REAL)) AS Total 
        FROM canon_minero 
        WHERE NIVEL_GOBIERNO IN ('M', 'R') AND EJECUTORA_NOMBRE IS NOT NULL
        GROUP BY EJECUTORA_NOMBRE 
        ORDER BY Total DESC 
        LIMIT 15
    ''')
    top_munis = cursor.fetchall()

    # 4. Por Rubro
    cursor.execute('''
        SELECT RUBRO_NOMBRE, SUM(CAST(MONTO_RECAUDADO AS REAL)) AS Total 
        FROM canon_minero 
        WHERE RUBRO_NOMBRE IS NOT NULL AND RUBRO_NOMBRE != ''
        GROUP BY RUBRO_NOMBRE 
        ORDER BY Total DESC
    ''')
    por_rubro = cursor.fetchall()
    
    conn.close()
    
    return por_mes, top_deptos, top_munis, por_rubro

def generar_html(por_mes, top_deptos, top_munis, por_rubro):
    meses_labels = [f"Mes {m[0]}" for m in por_mes]
    meses_data = [m[1] for m in por_mes]
    
    deptos_labels = [d[0] for d in top_deptos]
    deptos_data = [d[1] for d in top_deptos]
    
    rubro_labels = [r[0] for r in por_rubro]
    rubro_data = [r[1] for r in por_rubro]

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Interactivo MEF</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b1120;
            --card-bg: #111827;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --accent: #3b82f6;
            --border: #1f2937;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Outfit', sans-serif; }}
        body {{ background-color: var(--bg-color); color: var(--text-main); padding: 3rem 2rem; }}
        .header {{ text-align: center; margin-bottom: 4rem; }}
        .header h1 {{ font-size: 3rem; font-weight: 800; background: linear-gradient(135deg, #60a5fa, #c084fc, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .header p {{ color: var(--text-muted); margin-top: 1rem; font-size: 1.1rem; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 2rem; margin-bottom: 2rem; max-width: 1400px; margin: 0 auto; }}
        .card {{ background-color: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 25px 30px -5px rgba(0,0,0,0.2); border-color: rgba(59,130,246,0.3); }}
        .card h2 {{ font-size: 1.4rem; font-weight: 600; margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); color: #e5e7eb; }}
        
        .chart-container {{ position: relative; height: 320px; width: 100%; }}
        
        .table-container {{ overflow-x: auto; max-width: 1400px; margin: 2rem auto; }}
        table {{ width: 100%; border-collapse: separate; border-spacing: 0; }}
        th, td {{ padding: 1.25rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 0.1em; }}
        tr:hover td {{ background-color: rgba(255,255,255,0.03); }}
        td {{ color: #d1d5db; }}
        .amount {{ font-family: monospace; font-size: 1.2rem; color: #10b981; font-weight: 600; }}
        .rank {{ width: 40px; color: var(--text-muted); text-align: center; }}
    </style>
</head>
<body>

    <div class="header">
        <h1>Dashboard Interactivo: Canon Minero 2025</h1>
        <p>Análisis integral basado en más de 32,000 registros descargados de la API de Datos Abiertos del MEF.</p>
    </div>

    <div class="grid">
        <div class="card">
            <h2>Evolución de la Recaudación (Mes a Mes)</h2>
            <div class="chart-container">
                <canvas id="chartMeses"></canvas>
            </div>
        </div>

        <div class="card">
            <h2>Top 10 Departamentos</h2>
            <div class="chart-container">
                <canvas id="chartDeptos"></canvas>
            </div>
        </div>
        
        <div class="card">
            <h2>Distribución por Rubro de Financiamiento</h2>
            <div class="chart-container">
                <canvas id="chartRubros"></canvas>
            </div>
        </div>
    </div>

    <div class="table-container">
        <div class="card">
            <h2>Top 15 Gobiernos Locales y Regionales</h2>
            <table>
                <thead>
                    <tr>
                        <th class="rank">#</th>
                        <th>Entidad Ejecutora</th>
                        <th>Total Recaudado (S/)</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f"<tr><td class='rank'>{i+1}</td><td>{m[0]}</td><td class='amount'>S/ {m[1]:,.2f}</td></tr>" for i, m in enumerate(top_munis))}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        Chart.defaults.color = '#9ca3af';
        Chart.defaults.font.family = 'Outfit';

        // Configuración común de tooltips
        const tooltipConfig = {{
            backgroundColor: 'rgba(17, 24, 39, 0.9)',
            titleColor: '#fff',
            bodyColor: '#e5e7eb',
            borderColor: '#374151',
            borderWidth: 1,
            padding: 12,
            callbacks: {{
                label: function(context) {{
                    let value = context.raw;
                    return ' S/ ' + value.toLocaleString('en-US', {{minimumFractionDigits: 2}});
                }}
            }}
        }};

        // Gráfico de Meses
        new Chart(document.getElementById('chartMeses'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(meses_labels)},
                datasets: [{{
                    label: 'Recaudación',
                    data: {json.dumps(meses_data)},
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#3b82f6',
                    pointBorderColor: '#fff',
                    pointRadius: 4,
                    pointHoverRadius: 6
                }}]
            }},
            options: {{ 
                responsive: true, 
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }}, tooltip: tooltipConfig }},
                scales: {{
                    y: {{ grid: {{ color: '#1f2937' }}, beginAtZero: true }},
                    x: {{ grid: {{ display: false }} }}
                }}
            }}
        }});

        // Gráfico de Departamentos
        new Chart(document.getElementById('chartDeptos'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(deptos_labels)},
                datasets: [{{
                    label: 'Recaudación',
                    data: {json.dumps(deptos_data)},
                    backgroundColor: '#8b5cf6',
                    borderRadius: 8,
                    hoverBackgroundColor: '#a78bfa'
                }}]
            }},
            options: {{ 
                responsive: true, 
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }}, tooltip: tooltipConfig }},
                scales: {{
                    y: {{ grid: {{ color: '#1f2937' }}, beginAtZero: true }},
                    x: {{ grid: {{ display: false }} }}
                }}
            }}
        }});
        
        // Gráfico de Rubros
        new Chart(document.getElementById('chartRubros'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(rubro_labels)},
                datasets: [{{
                    data: {json.dumps(rubro_data)},
                    backgroundColor: ['#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899', '#8b5cf6'],
                    borderWidth: 2,
                    borderColor: '#111827',
                    hoverOffset: 10
                }}]
            }},
            options: {{ 
                responsive: true, 
                maintainAspectRatio: false, 
                cutout: '75%',
                plugins: {{
                    legend: {{ position: 'right', labels: {{ padding: 20, usePointStyle: true, pointStyle: 'circle' }} }},
                    tooltip: tooltipConfig
                }}
            }}
        }});
    </script>
</body>
</html>"""
    with open('informe_canon_minero_avanzado.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Informe generado: informe_canon_minero_avanzado.html")

if __name__ == '__main__':
    por_mes, top_deptos, top_munis, por_rubro = fetch_data()
    generar_html(por_mes, top_deptos, top_munis, por_rubro)
