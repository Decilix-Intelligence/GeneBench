# -*- coding: utf-8 -*-
import zipfile, os, io, csv, sys
B="/data/financial_data/ripple_alpha/extracted/ripple alpha/chinascope"
OUT=os.path.expanduser("~/genebench_inventory/tmp"); os.makedirs(OUT, exist_ok=True)
def listz(p, n=14):
    try:
        with zipfile.ZipFile(p) as z:
            ii=z.infolist()
            print(f"   entries={len(ii)}")
            for i in ii[:n]: print(f"    {i.filename}  raw={i.file_size:,}  zip={i.compress_size:,}")
    except Exception as e: print("   ERR", str(e)[:140])
print("========= sam_pit zip listings")
d=os.path.join(B,"sam_pit_v1.0_a_2014Q2_2024Q4")
for f in sorted(os.listdir(d)):
    print(f"-- {f}  ({os.path.getsize(os.path.join(d,f)):,} B)"); listz(os.path.join(d,f))
print("\n========= Smartag dictionary")
d2=os.path.join(B,"Smartag_v4.2_20080101-20240901","dictionary")
for f in sorted(os.listdir(d2)):
    p=os.path.join(d2,f)
    if f.endswith(".zip"):
        print(f"-- {f}  ({os.path.getsize(p):,} B)"); listz(p, 8)
    else: print(f"-- {f}  ({os.path.getsize(p):,} B)  [non-zip]")
print("\n========= one news zip")
p=os.path.join(B,"Smartag_v4.2_20080101-20240901","news_company_label_20080101-20090101.zip")
print(f"-- {os.path.basename(p)}"); listz(p, 8)
