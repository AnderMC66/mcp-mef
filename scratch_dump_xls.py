import glob
import re

for f in sorted(glob.glob('C:/semestre 2026-B/Contabilidad gerencial y tributacion/*.xls')):
    print('==============================')
    print('FILE:', f)
    with open(f, 'r', encoding='latin1', errors='ignore') as fp:
        html = fp.read()
        match = re.search(r'<table[^>]*class=["\']Data["\'][^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
        if match:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', match.group(1), re.DOTALL | re.IGNORECASE)
            for r in rows:
                cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL | re.IGNORECASE)
                clean = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', '') for c in cells]
                if clean:
                    print(clean)
