from mcp.server.fastmcp import FastMCP
import httpx
import sqlite3
import json
import urllib.parse
import csv
import os

# Inicializamos el servidor FastMCP
mcp = FastMCP("MEF_SIAF")

# Ruta de la base de datos local
DB_PATH = "mef_data.db"

@mcp.tool()
async def fetch_mef_dataset(resource_id: str, table_name: str, limit: int = 1000) -> str:
    """
    Descarga un dataset específico del MEF usando su `resource_id` (el cual puedes obtener 
    desde el portal datosabiertos.mef.gob.pe) y lo guarda en la base de datos 
    local (SQLite) bajo el nombre de tabla `table_name`. 
    Si la tabla ya existe, la sobrescribe.
    """
    url = f"https://api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/datastore_search?resource_id={resource_id}&limit={limit}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            if response.status_code != 200:
                return f"Error HTTP {response.status_code}: {response.text}"
                
            data = response.json()
            
            # La API del MEF tiene la particularidad de devolver los "records" en la raíz
            # y en ocasiones usar "sucess": "true" (con un solo c).
            records = data.get("records", [])
            if not records and "result" in data and "records" in data["result"]:
                records = data["result"]["records"]
                
            if not records:
                return "No se encontraron registros o la API del MEF indicó error."
                
            # Extraemos los nombres de las columnas del primer registro
            columns = list(records[0].keys())
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Crear tabla dinámicamente en SQLite (Typeless)
            cols_def = ", ".join([f'"{col}" TEXT' for col in columns])
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            cursor.execute(f'CREATE TABLE "{table_name}" ({cols_def})')
            
            # Insertar datos
            placeholders = ", ".join(["?" for _ in columns])
            insert_query = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
            
            for row in records:
                values = [str(row.get(col, "")) for col in columns]
                cursor.execute(insert_query, values)
                
            conn.commit()
            conn.close()
            
            return f"Éxito: Se crearon {len(records)} registros reales en la tabla '{table_name}' desde la API del MEF."
            
    except Exception as e:
        return f"Excepción al descargar dataset: {str(e)}"

@mcp.tool()
async def mef_search_datasets(query: str) -> str:
    """
    Busca datasets dinámicamente en el portal de datos abiertos.
    Retorna los títulos y los 'resource_id' listos para descargar.
    """
    # Usamos la API pública de CKAN del portal de Perú
    url = f"https://www.datosabiertos.gob.pe/api/3/action/package_search?q={urllib.parse.quote(query)}"
    
    try:
        # Agregamos headers y verify=False en caso de problemas con SSL en portales gubernamentales
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30.0)
            if response.status_code != 200:
                return f"Error HTTP {response.status_code}: {response.text}"
                
            data = response.json()
            if data.get("success"):
                results = data.get("result", {}).get("results", [])
                out = []
                for pkg in results[:10]: # Top 10 datasets
                    resources = pkg.get("resources", [])
                    for res in resources:
                        if res.get("format", "").upper() in ["CSV", "JSON", "XLS", "XLSX"]:
                            out.append({
                                "titulo_dataset": pkg.get("title"),
                                "recurso": res.get("name") or res.get("description"),
                                "formato": res.get("format"),
                                "resource_id": res.get("id")
                            })
                if not out:
                    return "No se encontraron recursos en formato tabular (CSV, JSON, XLS) para tu búsqueda."
                return json.dumps(out[:20], indent=2)
            else:
                return "La API de datos abiertos devolvió un error en la búsqueda."
    except Exception as e:
        return f"Excepción al buscar dataset: {str(e)}"

@mcp.tool()
def sql_mef_db(query: str) -> str:
    """
    Ejecuta una consulta SQL nativa en la base de datos local del MEF (mef_data.db).
    Puedes hacer JOINs entre tablas que hayas descargado previamente.
    Retorna los resultados en formato JSON.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        
        if query.strip().upper().startswith("SELECT"):
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            return json.dumps({"columnas": columns, "filas": results}, indent=2)
        else:
            conn.commit()
            conn.close()
            return json.dumps({"status": "success", "message": "Consulta ejecutada correctamente."})
            
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def mef_get_schema() -> str:
    """
    Retorna la estructura de la base de datos local: una lista de las tablas disponibles 
    y sus respectivas columnas. Útil para saber qué consultar con sql_mef_db.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema = {}
        for table in tables:
            cursor.execute(f"PRAGMA table_info('{table}')")
            columns = [row[1] for row in cursor.fetchall()]
            schema[table] = columns
            
        conn.close()
        return json.dumps(schema, indent=2)
    except Exception as e:
        return f"Error al obtener el esquema: {str(e)}"

@mcp.tool()
def mef_generate_chart(query: str, chart_type: str, title: str) -> str:
    """
    Ejecuta una consulta SQL y genera un gráfico a través de QuickChart.
    chart_type puede ser 'bar', 'pie', o 'line'.
    La consulta DEBE retornar 2 columnas: la primera para las etiquetas (labels) y la segunda para los valores numéricos.
    Retorna una URL directa a la imagen del gráfico.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            return "La consulta no retornó datos."
            
        labels = [str(r[0]) for r in results]
        try:
            values = [float(r[1]) for r in results]
        except (ValueError, TypeError):
            return "La segunda columna de la consulta SQL debe ser numérica para poder graficar."
            
        chart_config = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": title,
                    "data": values
                }]
            },
            "options": {
                "title": {
                    "display": True,
                    "text": title
                }
            }
        }
        
        config_json = json.dumps(chart_config)
        encoded_config = urllib.parse.quote(config_json)
        url = f"https://quickchart.io/chart?c={encoded_config}"
        
        return f"Gráfico generado con éxito. URL: {url}"
    except Exception as e:
        return f"Error al generar gráfico: {str(e)}"

@mcp.tool()
def mef_export_csv(query: str, filename: str) -> str:
    """
    Ejecuta una consulta SQL en la base de datos local y exporta los resultados a un archivo CSV.
    filename debe terminar en .csv, por ejemplo 'reporte.csv'.
    """
    try:
        if not filename.endswith('.csv'):
            filename += '.csv'
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        filepath = os.path.join(os.getcwd(), filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(results)
            
        return f"Éxito. Datos exportados correctamente a {filepath} ({len(results)} filas)."
    except Exception as e:
        return f"Error al exportar CSV: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
