import httpx
import re

BASE_URL_DIARIA = 'https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

with httpx.Client(verify=False, headers=headers, timeout=25) as client:
    r = client.get(BASE_URL_DIARIA, params={'_tgt': 'json', '_uhc': 'yes', 'y': '2026', '1': 'E', '2': ''})
    tr_matches = re.findall(r'<tr[^>]*id=[\'"]tr\d+[\'"][^>]*>(.*?)</tr>', r.text, re.DOTALL)
    print('Tr count in 1=E, 2="":', len(tr_matches))
    for tr in tr_matches:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', '') for c in cells]
        if len(clean) >= 2:
            print(clean[1])
