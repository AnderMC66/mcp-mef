import httpx
import re

BASE_URL_DIARIA = 'https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def parse_data_table(html):
    match = re.search(r'<table[^>]*class=["\']Data["\'][^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    if not match: return []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', match.group(1), re.DOTALL | re.IGNORECASE)
    out = []
    for r in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL | re.IGNORECASE)
        clean = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', '') for c in cells]
        if len(clean) >= 9:
            desc = clean[1]
            def to_float(val):
                if not val: return 0.0
                try: return float(val.replace(',', '').strip())
                except: return 0.0
            out.append({
                "descripcion": desc,
                "pia": to_float(clean[2]),
                "pim": to_float(clean[3]),
                "certificacion": to_float(clean[4]),
                "compromiso_anual": to_float(clean[5]),
                "compromiso_mensual": to_float(clean[6]),
                "devengado": to_float(clean[7]),
                "girado": to_float(clean[8]),
                "avance": to_float(clean[9]) if len(clean) > 9 else (round(to_float(clean[7]) / to_float(clean[3]) * 100, 2) if to_float(clean[3]) else 0.0)
            })
    return out

with httpx.Client(verify=False, headers=headers, timeout=25) as client:
    # 1. Obtener fila del Sector 26: DEFENSA
    r_sector = client.get(BASE_URL_DIARIA, params={'_tgt': 'json', '_uhc': 'yes', 'y': '2026', '1': 'E', '2': ''})
    print("=== SECTOR 26 EN GOBIERNO NACIONAL ===")
    for row in parse_data_table(r_sector.text):
        if 'DEFENSA' in row['descripcion']:
            print(row)

    # 2. Pliegos de DEFENSA (1=E, 2=26, 3="")
    r_pliegos = client.get(BASE_URL_DIARIA, params={'_tgt': 'json', '_uhc': 'yes', 'y': '2026', '1': 'E', '2': '26', '3': ''})
    pliegos = parse_data_table(r_pliegos.text)
    print("=== PLIEGOS DEL SECTOR 26: DEFENSA ===")
    for p in pliegos:
        print(p)
