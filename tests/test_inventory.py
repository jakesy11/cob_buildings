import importlib.util
import unittest
import io
import zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location("inventory",Path(__file__).resolve().parents[1]/"scripts/build_inventory.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class IntegrityTests(unittest.TestCase):
    def test_parcel_leading_zeroes(self):
        self.assertEqual(m.parcel_id({"Major":"1234","Minor":"12"}),"0012340012")
        self.assertEqual(m.pin("001234-0012"),"0012340012")
        self.assertEqual(m.pin("multiple parcels"),"")
    def test_city_internal_id_is_not_county_parcel_number(self):
        self.assertEqual(m.parcel_id({"LISParcelI":4296,"ParcelAFN":"8964800760"}),"8964800760")
        self.assertEqual(m.parcel_id({"LISParcelI":4296}),"")
    def test_missing_numeric_data_is_not_zero(self):
        for value in ["",None,"unknown","0"]:
            self.assertIsNone(m.num(value))
    def test_mixed_use_and_unknown(self):
        self.assertEqual(m.classify("459"),"Mixed-use")
        self.assertEqual(m.classify(None),"Unclassified")
        self.assertEqual(m.classify("300"),"Multifamily")
        self.assertEqual(m.classify("345"),"Parking")
    def test_multiple_tables_in_official_archive(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as archive:
            archive.writestr("EXTR_CommBldg.csv","Major,Minor,BldgNbr\n001234,0012,1\n")
            archive.writestr("EXTR_CommBldgSection.csv","Major,Minor,SectionUse\n001234,0012,300\n")
        rows=m.read_table(stream.getvalue(),"EXTR_CommBldg.csv")
        self.assertEqual(rows[0]["BldgNbr"],"1")
        with self.assertRaises(RuntimeError): m.read_table(stream.getvalue())
    def test_csv_keeps_identifiers(self):
        rows=m.csv_bytes(b"\xef\xbb\xbfMajor,Minor,BLDGNBR\n001234,0012,1\n")
        self.assertEqual(m.parcel_id(rows[0]),"0012340012")

if __name__=="__main__":unittest.main()
