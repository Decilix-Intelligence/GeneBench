# -*- coding: utf-8 -*-
import zipfile, os, io
B="/data/financial_data/ripple_alpha/extracted/ripple alpha/chinascope"
SAM=os.path.join(B,"sam_pit_v1.0_a_2014Q2_2024Q4")
SMT=os.path.join(B,"Smartag_v4.2_20080101-20240901")
OUT=os.path.expanduser("~/genebench_inventory/tmp"); os.makedirs(OUT, exist_ok=True)

def peek(zp, nrows=3, nbytes=24000):
    """stream-read the first bytes of the single member; no full extraction"""
    with zipfile.ZipFile(zp) as z:
        m=z.infolist()[0]
        with z.open(m) as f:
            raw=f.read(nbytes)
    for enc in ("utf-8","gb18030","utf-8-sig"):
        try: txt=raw.decode(enc); break
        except Exception: continue
    else: txt=raw.decode("utf-8","replace"); enc="utf-8/replace"
    lines=txt.splitlines()
    return enc, lines[0] if lines else "", lines[1:1+nrows]

def show(label, zp, nrows=2):
    print(f"\n===== {label}")
    try:
        enc,hdr,rows=peek(zp,nrows)
        cols=hdr.split(",") if "," in hdr else hdr.split("\t")
        print(f"  encoding={enc}  ncols={len(cols)}")
        print(f"  HEADER: {hdr[:900]}")
        for r in rows: print(f"  ROW: {r[:520]}")
    except Exception as e: print("  ERR", str(e)[:200])

show("sam_pit / fin_secu_sam_period_pit  (期间级 PIT 财务)", f"{SAM}/fin_secu_sam_period_pit.zip")
show("sam_pit / fin_secu_sam_product_pit (产品级 PIT)",      f"{SAM}/fin_secu_sam_product_pit.zip")
show("sam_pit / fin_secu_sam_product_calc_pit (产品级测算 PIT)", f"{SAM}/fin_secu_sam_product_calc_pit.zip")
show("sam_pit / supply_chain_relation (供应链关系)",          f"{SAM}/supply_chain_relation.zip")
show("sam_pit / base_stock",                                  f"{SAM}/base_stock.zip")
show("sam_pit / base_company",                                f"{SAM}/base_company.zip")
show("sam_pit / dict_industry",                               f"{SAM}/dict_industry.zip")
show("sam_pit / dict_product_rs",                             f"{SAM}/dict_product_rs.zip")
show("sam_pit / sam_release_notes_tree",                      f"{SAM}/sam_release_notes_tree.zip")
show("Smartag / news_company_label 2008-2009", f"{SMT}/news_company_label_20080101-20090101.zip", 3)
show("Smartag / news_company_label 2024 (末段)", f"{SMT}/news_company_label_20240601-20240901.zip", 2)
show("Smartag dict / concept_dictionary", f"{SMT}/dictionary/concept_dictionary.zip")
show("Smartag dict / concept_stock",      f"{SMT}/dictionary/concept_stock.zip")
show("Smartag dict / event_dictionary",   f"{SMT}/dictionary/event_dictionary.zip")
show("Smartag dict / region_dictionary",  f"{SMT}/dictionary/region_dictionary.zip")
show("Smartag dict / base_stock",         f"{SMT}/dictionary/base_stock.zip")

# authorized exception: extract 3 small files (<10MB each) for the record
print("\n===== extracted to ~/genebench_inventory/tmp (3 files, authorized)")
for zp,name in [(f"{SAM}/dict_industry.zip","dict_industry.csv"),
                (f"{SMT}/dictionary/concept_dictionary.zip","concept_dictionary.csv"),
                (f"{SMT}/dictionary/event_dictionary.zip","event_dictionary.csv")]:
    with zipfile.ZipFile(zp) as z:
        m=z.infolist()[0]
        assert m.file_size < 10*1024*1024, (name, m.file_size)
        z.extract(m, OUT)
    print(f"  {name}  {m.file_size:,} B")
