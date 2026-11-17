"""Retrieve public source data; preserve ambiguous joins and missing attributes."""
import csv
import io
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

BASE = "https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/"
ASSESSOR = "https://info.kingcounty.gov/assessor/DataDownload/default.aspx"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "BellevueBuildingStockResearch/1.0 (public municipal planning)"
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504])))
QUERY_BOUNDS = None
REPORT = {"retrieved_at":datetime.now(timezone.utc).isoformat(),"sources":{},"warnings":[]}

def get_json(url, params=None):
    r=SESSION.get(url,params=params,timeout=45)
    r.raise_for_status()
    data=r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data

def pin(value):
    text=str(value or "").strip()
    if text.endswith(".0"): text=text[:-2]
    text=re.sub(r"[\s-]","",text)
    return text.zfill(10) if text.isdigit() and len(text)<=10 else ""

def norm(row):
    return {re.sub("[^A-Z0-9]","",str(k).upper()):v for k,v in row.items() if k}

def parcel_id(row):
    row=norm(row)
    for key in ("PIN","PARCELNUMBER","PARCELID","PARCELNO","LISPARCELI"):
        if row.get(key): return pin(row[key])
    if row.get("MAJOR") is not None and row.get("MINOR") is not None:
        return pin(str(row["MAJOR"]).strip().zfill(6)+str(row["MINOR"]).strip().zfill(4))
    return ""

def num(value):
    try:
        result=float(str(value).replace(",","").strip())
        return result if result>0 else None
    except (TypeError, ValueError): return None

def field(row,*keys):
    row=norm(row)
    for key in keys:
        if row.get(key) not in (None,""): return row[key]
    return None

def service_layer(name):
    url=BASE+name+"/FeatureServer"
    meta=get_json(url,{"f":"json"})
    layers=meta.get("layers",[])
    if not layers: raise RuntimeError("No public layers: "+name)
    # Services listed here are single-purpose. Save actual selected layer metadata.
    return url+"/"+str(layers[0]["id"])

def fetch_features(name,url=None):
    url=url or service_layer(name)
    meta=get_json(url,{"f":"json"})
    query={"f":"json","where":"1=1","returnIdsOnly":"true"}
    if QUERY_BOUNDS and name!="City_Limits":
        query.update({"geometry":",".join(map(str,QUERY_BOUNDS)),"geometryType":"esriGeometryEnvelope","inSR":"4326","spatialRel":"esriSpatialRelIntersects"})
    ids=get_json(url+"/query",query)
    ids=sorted(ids.get("objectIds") or [])
    features=[]
    fields=[x["name"] for x in meta.get("fields",[])]
    # Public permit export deliberately excludes owner/applicant/billing fields.
    if name=="Bellevue_Permits":
        allowed={"ObjectId","PERMITNUMBER","PERMITTYPE","PERMITTYPEDESCRIPTION","SITEADDRESS","CITY","PERMITSTATUS","PARCELNUMBER","PROJECTNAME","PROJECTDESCRIPTION","APPLIEDDATE","ISSUEDDATE","FINALEDDATE","PERMITYEAR","DWELLINGUNITSCREATED","OCCUPANCYGROUP1","SQFOOTAGE1"}
        fields=[x for x in fields if x in allowed]
    oid=ids and (meta.get("objectIdField") or next(f["name"] for f in meta["fields"] if f["type"]=="esriFieldTypeOID"))
    def batch(chunk):
        params={k:v for k,v in query.items() if k not in {"returnIdsOnly","where"}}
        params.update({"f":"geojson","where":f"{oid} >= {chunk[0]} AND {oid} <= {chunk[-1]}","outFields":",".join(fields) if name=="Bellevue_Permits" else "*","outSR":"4326","returnGeometry":"true","resultRecordCount":1000})
        part=get_json(url+"/query",params)
        if part.get("exceededTransferLimit"): raise RuntimeError("Truncated query: "+name)
        result=part.get("features",[])
        actual={int(f.get("id",f["properties"].get(oid))) for f in result}
        if actual!=set(chunk): raise RuntimeError("Batch ID mismatch: "+name)
        return result
    print(name,"querying",len(ids),"records",flush=True)
    chunks=[ids[i:i+500] for i in range(0,len(ids),500)]
    if chunks:
        features.extend(batch(chunks[0]))
        with ThreadPoolExecutor(max_workers=4) as pool:
            for part in pool.map(batch,chunks[1:]): features.extend(part)
    if len(features)!=len(ids): raise RuntimeError(f"{name}: expected {len(ids)} records, received {len(features)}")
    REPORT["sources"][name]={"url":url,"records":len(features),"status":"retrieved","fields":fields,"source_edit_date":meta.get("editingInfo",{}).get("lastEditDate")}
    print(name,len(features),flush=True)
    return features

def optional(name,func):
    try: return func()
    except Exception as exc:
        REPORT["sources"][name]={"status":"unavailable","error":str(exc)[:500]}
        REPORT["warnings"].append(name+": "+str(exc)[:250])
        print("UNAVAILABLE",name,str(exc)[:250],flush=True)
        return []

def csv_bytes(content):
    text=content.decode("utf-8-sig",errors="replace")
    try: dialect=csv.Sniffer().sniff(text[:20000],delimiters=",\t|")
    except csv.Error: dialect=csv.excel
    return list(csv.DictReader(io.StringIO(text),dialect=dialect))

def read_table(content,member_hint=None):
    if content[:2]==b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            candidates=[n for n in archive.namelist() if n.lower().endswith((".csv",".txt"))]
            if member_hint: candidates=[n for n in candidates if Path(n).name.lower()==member_hint.lower()]
            if len(candidates)!=1: raise RuntimeError("Expected one CSV/TXT in source archive; found "+str(candidates))
            return csv_bytes(archive.read(candidates[0]))
    return csv_bytes(content)

def assessor_links():
    r=SESSION.get(ASSESSOR,timeout=90);r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    # Standard public-use acknowledgement, not authentication or owner authorization.
    checkbox=soup.select_one('input[type="checkbox"]')
    if checkbox:
        form=checkbox.find_parent("form")
        if form:
            payload={x.get("name"):x.get("value","") for x in form.select('input[type="hidden"]') if x.get("name")}
            payload[checkbox.get("name")]="on"
            payload["__EVENTTARGET"]=checkbox.get("name")
            payload["__EVENTARGUMENT"]=""
            r=SESSION.post(urljoin(r.url,form.get("action") or r.url),data=payload,timeout=90)
            r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser")
    links=[(a.get_text(" ",strip=True),urljoin(r.url,a["href"])) for a in soup.select("a[href]") if ".zip" in a["href"].lower()]
    print("Assessor public ZIP links:",json.dumps(links),flush=True)
    if not links: print("Assessor public download-page links:",json.dumps([(a.get_text(" ",strip=True),a["href"]) for a in soup.select("a[href]") if re.search("download|extract|commercial|apartment",a.get_text(" ",strip=True)+" "+a["href"],re.I)]),flush=True)
    return links

ASSESSOR_CONTENT={}

def assessor_table(kind,links):
    local=ROOT/"inputs"/(kind+".csv")
    if local.exists():
        rows=read_table(local.read_bytes())
        REPORT["sources"][kind]={"status":"provided","records":len(rows),"url":str(local.relative_to(ROOT))}
        return rows
    patterns={"commercial":r"commercial.*build|commbldg","apartments":r"apartment|aptcomplex","sections":r"commercial.*build|commbldg"}
    matches=[url for label,url in links if re.search(patterns[kind],label+" "+url,re.I)]
    if kind in {"commercial","sections"}: matches=[u for u in matches if not re.search("section|feature",u,re.I)]
    if len(matches)!=1: raise RuntimeError(f"Cannot uniquely discover {kind} public download ({len(matches)} matches); place official CSV at inputs/{kind}.csv for local use.")
    if matches[0] not in ASSESSOR_CONTENT:
        r=SESSION.get(matches[0],timeout=180);r.raise_for_status()
        ASSESSOR_CONTENT[matches[0]]=r.content
    hints={"commercial":"EXTR_CommBldg.csv","sections":"EXTR_CommBldgSection.csv"}
    rows=read_table(ASSESSOR_CONTENT[matches[0]],hints.get(kind))
    print(kind,"columns",list(rows[0]) if rows else [],flush=True)
    if not rows or not parcel_id(rows[0]): raise RuntimeError("Unexpected assessor schema")
    REPORT["sources"][kind]={"status":"retrieved","url":matches[0],"records":len(rows)}
    print(kind,len(rows),flush=True)
    return rows

HEAT={1:"Electric",2:"Electric wall",3:"Forced air unit",4:"Hot water",5:"Hot water-radiant",6:"Space heaters",7:"Steam",8:"Steam without boiler",9:"Ventilation",10:"Wall furnace",11:"Package unit",12:"Warmed and cooled air",13:"Hot and chilled water",14:"Heat pump",15:"Floor furnace",16:"Through-wall heat pump",17:"Complete HVAC",18:"Evaporative cooling",19:"Refrigerated cooling",20:"No heat"}
USES={300:"Apartment",344:"Office",353:"Retail",352:"Multiple residence",451:"Senior multiple residence",459:"Mixed retail and residential",341:"Medical office",350:"Restaurant",349:"Fast food",406:"Storage warehouse",407:"Distribution warehouse",453:"Industrial flex",494:"Light manufacturing",495:"Heavy manufacturing",841:"Hotel",332:"Limited-service hotel"}
def classify(code):
    try: code=int(float(code))
    except (TypeError,ValueError): return "Unclassified"
    if code in {300,352,451}: return "Multifamily"
    if code==459: return "Mixed-use"
    if code in {345,388,850,851,706}: return "Parking"
    if code==0: return "Unclassified"
    if code==348: return "Residential—review"
    return "Commercial / institutional"

def safe_shape(feature):
    return shape(feature["geometry"]).buffer(0)

def output_json(name,data):
    (OUT/name).write_text(json.dumps(data,separators=(",",":"),allow_nan=False),encoding="utf-8")

def build():
    global QUERY_BOUNDS
    OUT.mkdir(exist_ok=True)
    boundary=fetch_features("City_Limits")
    named=[f for f in boundary if any(str(v).strip().upper() in {"BELLEVUE","CITY OF BELLEVUE"} for v in f["properties"].values())]
    if named: boundary=named
    elif len(boundary)>1: raise RuntimeError("Boundary service contains multiple features without an exact Bellevue name; manual source selection required")
    city=unary_union([safe_shape(f) for f in boundary if f.get("geometry")])
    if city.is_empty: raise RuntimeError("City boundary is empty")
    QUERY_BOUNDS=city.bounds
    buildings=fetch_features("Buildings")
    buildings=[f for f in buildings if f.get("geometry") and safe_shape(f).intersects(city)]
    parcels=optional("City_of_Bellevue_Parcels",lambda:fetch_features("City_of_Bellevue_Parcels"))
    parcels=[f for f in parcels if f.get("geometry") and safe_shape(f).intersects(city)]
    parcel_geoms=[safe_shape(f) for f in parcels]
    parcel_tree=STRtree(parcel_geoms)
    geometry_by_pin=defaultdict(list)
    for f,g in zip(parcels,parcel_geoms):
        p=parcel_id(f["properties"])
        if p: geometry_by_pin[p].append(g)
    links=optional("assessor_download_discovery",assessor_links)
    commercial=optional("commercial",lambda:assessor_table("commercial",links))
    apartments=optional("apartments",lambda:assessor_table("apartments",links))
    sections=optional("sections",lambda:assessor_table("sections",links))
    by_pin=defaultdict(list)
    for row in commercial:
        p=parcel_id(row)
        if p in geometry_by_pin: by_pin[p].append(row)
    sections_by_building=defaultdict(list)
    for row in sections:
        key=(parcel_id(row),str(field(row,"BLDGNBR") or "").strip())
        sections_by_building[key].append(row)
    apartments_by_pin=defaultdict(list)
    for row in apartments: apartments_by_pin[parcel_id(row)].append(row)
    permit_rows=optional("Bellevue_Permits",lambda:fetch_features("Bellevue_Permits"))
    permit_by_pin=defaultdict(list)
    export_permits=[]
    terms=re.compile(r"heat\s*pump|HVAC|boiler|furnace|water\s*heat|electrif|solar|insulat|weatheriz",re.I)
    for feature in permit_rows:
        p=parcel_id(feature["properties"])
        if p not in geometry_by_pin: continue
        r=norm(feature["properties"])
        item={"permit_number":r.get("PERMITNUMBER"),"parcel_id":p,"address":r.get("SITEADDRESS"),"type":r.get("PERMITTYPEDESCRIPTION"),"status":r.get("PERMITSTATUS"),"description":r.get("PROJECTDESCRIPTION"),"issued_date":r.get("ISSUEDDATE"),"finaled_date":r.get("FINALEDDATE"),"energy_keyword":bool(terms.search(str(r.get("PROJECTDESCRIPTION",""))+" "+str(r.get("PERMITTYPEDESCRIPTION",""))))}
        permit_by_pin[p].append(item);export_permits.append(item)
    records=[]
    for p,rows in sorted(by_pin.items()):
        for row in rows:
            b=str(field(row,"BLDGNBR") or "").strip()
            code=field(row,"PREDOMINANTUSE")
            section_rows=sections_by_building[(p,b)]
            section_codes={str(field(x,"SECTIONUSE")) for x in section_rows}
            category=classify(code)
            if section_codes.intersection({"300","352","451","707"}) and any(classify(x)=="Commercial / institutional" for x in section_codes):
                category="Mixed-use"
            aggregate=num(field(row,"NBRBLDGS"))
            heat=num(field(row,"HEATINGSYSTEM"))
            geom=unary_union(geometry_by_pin[p]).representative_point()
            records.append({"inventory_id":p+":"+b,"parcel_id":p,"assessor_building_number":b,"category":category,"use_code":code,"use_description":USES.get(int(float(code)),"Assessor use "+str(code)) if num(code) else "Unknown","address":field(row,"SITUSADDRESS"),"gross_sqft":num(field(row,"BLDGGROSSSQFT")),"year_built":num(field(row,"YRBUILT")),"effective_year":num(field(row,"EFFYR")),"stories":num(field(row,"NBRSTORIES")),"heating_system":HEAT.get(int(heat),"Unknown") if heat else "Unknown","heating_fuel":None,"aggregate_buildings":aggregate,"apartment_complex_units":sum(num(field(x,"NUMUNITS")) or 0 for x in apartments_by_pin[p]) or None,"unit_count_scope":"parcel/complex; do not sum across building records","permit_count":len(permit_by_pin[p]),"energy_permit_count":sum(x["energy_keyword"] for x in permit_by_pin[p]),"permit_match":"parcel only; building unverified","wa_building_id":None,"compliance_status":"Not obtained","site_eui_kbtu_sqft":None,"reporting_year":None,"longitude":geom.x,"latitude":geom.y,"location_method":"parcel representative point; not exact building"})
    # Same parcel + building key must be unique. Never silently drop a duplicate.
    counts=Counter(r["inventory_id"] for r in records)
    if any(n>1 for n in counts.values()): raise RuntimeError("Duplicate Assessor building keys; source review required")
    commerce=ROOT/"inputs/commerce.csv"
    if commerce.exists():
        verified={r["inventory_id"]:r for r in records}
        incoming=csv_bytes(commerce.read_bytes())
        seen=set()
        for row in incoming:
            key=row.get("inventory_id")
            if key not in verified or key in seen: raise RuntimeError("Commerce crosswalk missing, duplicate, or invalid inventory_id: "+str(key))
            seen.add(key)
            target=verified[key]
            for key in ("wa_building_id","reporting_year","compliance_status","source_date"):
                if row.get(key): target[key]=row[key]
            for key in ("site_eui_kbtu_sqft","energy_kwh","natural_gas_therms"):
                if row.get(key): target[key]=float(row[key])
        REPORT["sources"]["commerce"]={"status":"provided","records":len(incoming),"matching":"explicit inventory_id crosswalk"}
    else:
        REPORT["sources"]["commerce"]={"status":"not obtained","url":"https://www.commerce.wa.gov/cbps/portal/","note":"Public dashboard is not a building-level compliance export. No compliance inferred."}
    records_by_pin=defaultdict(list)
    for record in records: records_by_pin[record["parcel_id"]].append(record)
    footprints=[]
    for f in buildings:
        g=safe_shape(f)
        candidates=[int(i) for i in parcel_tree.query(g,predicate="intersects")]
        overlap=[(g.intersection(parcel_geoms[i]).area/max(g.area,1e-20),i) for i in candidates]
        overlap.sort(reverse=True)
        match=overlap[0] if overlap else None
        confident=bool(match and match[0]>=0.9 and sum(x[0]>=0.1 for x in overlap)==1)
        p=parcel_id(parcels[match[1]]["properties"]) if confident else ""
        rs=records_by_pin[p] if p else []
        categories={r["category"] for r in rs}
        category=next(iter(categories)) if len(categories)==1 else "Unclassified"
        footprints.append({"type":"Feature","geometry":mapping(g),"properties":{"footprint_id":f["properties"].get("BuildingID") or f["properties"].get("OBJECTID"),"parcel_id":p,"category":category,"classification_basis":"parcel-associated Assessor use; exact footprint match unverified" if rs else "No linked Assessor use","parcel_match":"90% overlap, unique" if confident else "Ambiguous / unmatched","assessor_record_count":len(rs),"inventory_ids":[r["inventory_id"] for r in rs]}})
    REPORT["summary"]={"footprints_in_city":len(footprints),"assessor_records_in_city_parcels":len(records),"categories":dict(Counter(r["category"] for r in records)),"footprint_categories":dict(Counter(f["properties"]["category"] for f in footprints)),"permit_records_on_city_parcels":len(export_permits),"records_missing_heating_system":sum(r["heating_system"]=="Unknown" for r in records),"records_with_reported_eui":sum(r["site_eui_kbtu_sqft"] is not None for r in records)}
    REPORT["warnings"].append("Condominium complexes and 2–3 unit residential properties require additional Assessor tables; coverage is not yet complete.")
    if not records: REPORT["warnings"].append("No Assessor records linked. Map is a footprint and permit exploration layer, not a classified building stock inventory.")
    output_json("source_report.json",REPORT)
    output_json("buildings.geojson",{"type":"FeatureCollection","features":footprints})
    output_json("inventory.json",records)
    output_json("permits.json",export_permits)
    if records:
        with (OUT/"inventory.csv").open("w",newline="",encoding="utf-8") as stream:
            writer=csv.DictWriter(stream,fieldnames=sorted({k for r in records for k in r}));writer.writeheader();writer.writerows(records)
    data={"report":REPORT,"buildings":{"type":"FeatureCollection","features":footprints},"boundary":{"type":"FeatureCollection","features":[{"type":"Feature","geometry":mapping(city),"properties":{}}]},"inventory":records,"permits":export_permits}
    template=(ROOT/"web/index.html").read_text(encoding="utf-8")
    # JSON must not be able to close the HTML script element.
    embedded=json.dumps(data,separators=(",",":"),allow_nan=False).replace("<","\\u003c")
    (OUT/"index.html").write_text(template.replace("/*__DATA__*/null",embedded),encoding="utf-8")
    areas=defaultdict(float)
    for record in records:
        if record["gross_sqft"] is not None: areas[record["category"]]+=record["gross_sqft"]
    REPORT["summary"]["assessor_gross_sqft_by_category"]=dict(areas)
    output_json("source_report.json",REPORT)
    lines=["# Bellevue building stock: preliminary source findings","", "Retrieved: "+REPORT["retrieved_at"],"", "## Inventory coverage","", "| Assessor category | Records | Reported gross floor area (sq ft) |","|---|---:|---:|"]
    for category,count in sorted(REPORT["summary"]["categories"].items()): lines.append(f"| {category} | {count:,} | {areas[category]:,.0f} |")
    lines+=["","Counts describe Assessor records, including aggregated records. Gross area includes source-defined areas and is not a state covered-floor-area determination. Unit totals are not summed across complex records.","","## Outstanding data gaps",""]+["- "+w for w in REPORT["warnings"]]
    lines+=["","Commerce building-level reporting has not been obtained unless documented in source_report.json. Missing reports are not interpreted as noncompliance. No energy or emissions totals are estimated.","","## Source availability",""]+["- "+name+": "+source["status"] for name,source in REPORT["sources"].items()]
    (OUT/"analysis.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(REPORT["summary"],indent=2),flush=True)
    if not footprints: raise RuntimeError("No footprints retrieved")
    return REPORT

if __name__=="__main__":
    try: build()
    except Exception as exc:
        OUT.mkdir(exist_ok=True)
        REPORT["fatal_error"]=str(exc)
        output_json("source_report.json",REPORT)
        raise
