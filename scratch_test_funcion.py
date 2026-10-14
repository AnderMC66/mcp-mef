import httpx
import re

BASE_URL_DIARIA = 'https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

with httpx.Client(verify=False, headers=headers, timeout=25) as client:
    r_init = client.get(BASE_URL_DIARIA, params={'_tgt': 'json', '_uhc': 'yes', 'y': '2026'})
    vs = re.search(r'name="__VIEWSTATE" id="__VIEWSTATE" value="([^"]*)"', r_init.text).group(1)
    ev = re.search(r'name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="([^"]*)"', r_init.text).group(1)
    
    r_func = client.post(str(r_init.url), data={
        '__VIEWSTATE': vs,
        '__EVENTVALIDATION': ev,
        'ctl00$CPH1$BtnFuncion': 'Función'
    })
    
    # Find radio for 20: SALUD
    radio_salud = None
    for tr in re.finditer(r'<tr[^>]*id=[\'"]tr\d+[\'"][^>]*>(.*?)</tr>', r_func.text, re.DOTALL):
        if '20: SALUD' in tr.group(1):
            radio_salud = re.search(r'value=[\'"]([^\'"]*)[\'"]', tr.group(1)).group(1)
            break
    
    vs2 = re.search(r'name="__VIEWSTATE" id="__VIEWSTATE" value="([^"]*)"', r_func.text).group(1)
    ev2 = re.search(r'name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="([^"]*)"', r_func.text).group(1)
    
    r_tipo = client.post(str(r_func.url), data={
        '__VIEWSTATE': vs2,
        '__EVENTVALIDATION': ev2,
        'grp1': radio_salud,
        'ctl00$CPH1$BtnTipoGobierno': 'Nivel'
    })
    print("Tipo status:", r_tipo.status_code)
    for tr in re.finditer(r'<tr[^>]*id=[\'"]tr\d+[\'"][^>]*>(.*?)</tr>', r_tipo.text, re.DOTALL):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr.group(1), re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', '') for c in cells]
        if clean:
            print("Row Tipo:", clean)
