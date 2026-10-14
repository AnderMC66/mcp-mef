import httpx
import re
import json

BASE_URL_DIARIA = "https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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
    r_pliegos = client.get(BASE_URL_DIARIA, params={"_tgt": "json", "_uhc": "yes", "y": "2026", "1": "E", "2": "11", "3": ""})
    radio_minsa = None
    for tr in re.finditer(r'<tr[^>]*id=["\']tr\d+["\'][^>]*>(.*?)</tr>', r_pliegos.text, re.DOTALL):
        if "011: M. DE SALUD" in tr.group(1):
            radio_minsa = re.search(r'value=["\']([^"\']*)["\']', tr.group(1)).group(1)
            break
    print("Radio MINSA:", radio_minsa)

    vs = re.search(r'name="__VIEWSTATE" id="__VIEWSTATE" value="([^"]*)"', r_pliegos.text).group(1)
    ev = re.search(r'name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="([^"]*)"', r_pliegos.text).group(1)

    # Cuadro 4: MINSA por Fuente
    r_fte = client.post(str(r_pliegos.url), data={
        "__VIEWSTATE": vs,
        "__EVENTVALIDATION": ev,
        "grp1": radio_minsa,
        "ctl00$CPH1$BtnFuenteAgregada": "Fuente"
    })
    print("=== DIARIA: MINSA POR FUENTE ===")
    for row in parse_data_table(r_fte.text):
        print(row)

    # Cuadro 5: MINSA por Genérica
    r_gen = client.post(str(r_pliegos.url), data={
        "__VIEWSTATE": vs,
        "__EVENTVALIDATION": ev,
        "grp1": radio_minsa,
        "ctl00$CPH1$BtnGenerica": "Genérica"
    })
    print("=== DIARIA: MINSA POR GENERICA ===")
    for row in parse_data_table(r_gen.text):
        print(row)

    # Cuadro 6: MINSA por Programa Presupuestal
    r_ppto = client.post(str(r_pliegos.url), data={
        "__VIEWSTATE": vs,
        "__EVENTVALIDATION": ev,
        "grp1": radio_minsa,
        "ctl00$CPH1$BtnProgramaPpto": "Programa"
    })
    print("=== DIARIA: MINSA POR PROGRAMA ===")
    for row in parse_data_table(r_ppto.text):
        print(row)
