"""Quick status of the creator store and any running pipeline. python scripts/status.py"""
import sqlite3, os, sys
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c = sqlite3.connect(os.path.join(BASE, "creator_intelligence.db"))
q = lambda s: c.execute(s).fetchone()[0]
has = lambda t: c.execute("select name from sqlite_master where name=?", (t,)).fetchone() is not None

print(f"status at {datetime.now().strftime('%H:%M:%S')}")
print(f"creators in store           {q('select count(*) from creators'):>8,}")
print(f"  kolkata leads             {q(chr(34).join(['select count(distinct handle) from observations where region=', 'kolkata', ''])):>8,}")
print(f"  exact-verified, 10K+      {q(chr(34).join(['select count(*) from creators where followers_precision=', 'exact', ' and followers>=10000'])):>8,}")
print(f"  pending audit             {q(chr(34).join(['select count(*) from creators where audit_status=', 'PENDING_AUDIT', ''])):>8,}")
print(f"geo evidence rows           {q('select count(*) from geo_evidence'):>8,}")
if has("swept_locations"):
    print(f"kolkata locations swept     {q(chr(34).join(['select count(*) from swept_locations where region=', 'kolkata', ''])):>8,}")
print(f"creators with 2+ places     {q(chr(34).join(['select count(*) from (select handle from geo_evidence where region=', 'kolkata', ' group by handle having count(distinct place_pk)>=2)'])):>8,}")
if has("creator_deep_scan"):
    print(f"deep scanned (OK)           {q(chr(34).join(['select count(*) from creator_deep_scan where status=', 'OK', ''])):>8,}")
print(f"brand collab rows           {q('select count(*) from brand_collabs'):>8,}")
