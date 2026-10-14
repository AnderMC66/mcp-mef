import httpx
import re

BASE_URL_DIARIA = "https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

with httpx.Client(verify=False, headers=headers, timeout=25) as client:
    r = client.get(BASE_URL_DIARIA, params={"_tgt": "json", "_uhc": "yes", "y": "2026", "1": "E", "2": "11", "3": ""})
    print("Status:", r.status_code)
    btns = re.findall(r'name=[\'\"](ctl00\$CPH1\$Btn[^\'\"]*)[\'\"]', r.text)
    print("Buttons:", btns)
    # Check if tr has radio
    tr_matches = re.findall(r'<tr[^>]*id=["\']tr\d+["\'][^>]*>(.*?)</tr>', r.text, re.DOTALL)
    print("Tr count:", len(tr_matches))
    for tr in tr_matches:
        if "011" in tr:
            print("Found 011 in tr:", tr[:200])
