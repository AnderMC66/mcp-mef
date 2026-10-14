import httpx
import re

BASE_URL_DIARIA = "https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

with httpx.Client(verify=False, headers=headers, timeout=25) as client:
    r = client.get(BASE_URL_DIARIA, params={"_tgt": "json", "_uhc": "yes", "y": "2026", "1": "E", "2": "11", "3": ""})
    for line in r.text.splitlines():
        if "actualiz" in line.lower() or "fecha" in line.lower() or "corte" in line.lower():
            print(line.strip())
