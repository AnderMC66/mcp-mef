import sqlite3
import json

def generar_informe_html():
    conn = sqlite3.connect('mef_data.db')
    cursor = conn.cursor()
    
    # Obtener el top 10 departamentos por recaudación
    cursor.execute('''
        SELECT DEPARTAMENTO_EJECUTORA_NOMBRE, SUM(CAST(MONTO_RECAUDADO AS REAL)) AS Total 
        FROM canon_minero 
        GROUP BY DEPARTAMENTO_EJECUTORA_NOMBRE 
        ORDER BY Total DESC 
        LIMIT 10;
    ''')
    top_deptos = cursor.fetchall()

    # Obtener el top 10 municipalidades/ejecutoras
    cursor.execute('''
        SELECT EJECUTORA_NOMBRE, SUM(CAST(MONTO_RECAUDADO AS REAL)) AS Total 
        FROM canon_minero 
        WHERE NIVEL_GOBIERNO = 'M' OR NIVEL_GOBIERNO = 'R'
        GROUP BY EJECUTORA_NOMBRE 
        ORDER BY Total DESC 
        LIMIT 10;
    ''')
    top_municipios = cursor.fetchall()
    
    conn.close()

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Informe: Ingresos del Canon Minero</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background-color: #f4f7f6; color: #333; }}
            .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; text-align: center; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #2980b9; margin-top: 30px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #3498db; color: white; }}
            tr:hover {{ background-color: #f1f1f1; }}
            .footer {{ text-align: center; margin-top: 40px; font-size: 12px; color: #7f8c8d; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Informe de Transferencias e Ingresos: Canon Minero 2025</h1>
            
            <h2>Top 10 Departamentos con Mayor Recaudación</h2>
            <table>
                <thead>
                    <tr>
                        <th>Departamento</th>
                        <th>Total Recaudado (S/)</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f"<tr><td>{d[0]}</td><td>{d[1]:,.2f}</td></tr>" for d in top_deptos)}
                </tbody>
            </table>

            <h2>Top 10 Ejecutoras (Gobiernos Locales/Regionales)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Ejecutora</th>
                        <th>Total Recaudado (S/)</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f"<tr><td>{m[0]}</td><td>{m[1]:,.2f}</td></tr>" for m in top_municipios)}
                </tbody>
            </table>

            <div class="footer">
                Generado automáticamente usando el servidor MCP-MEF | Fuente: Portal de Datos Abiertos MEF
            </div>
        </div>
    </body>
    </html>
    """

    with open('informe_canon_minero.html', 'w', encoding='utf-8') as f:
        f.write(html)
        
    print("Informe HTML generado en informe_canon_minero.html")

if __name__ == "__main__":
    generar_informe_html()
