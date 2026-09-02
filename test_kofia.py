import requests
import xml.etree.ElementTree as ET
from datetime import datetime

def test_kofia_yields():
    url = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
    today_str = datetime.today().strftime("%Y%m%d")
    
    xml_data = f"""<message>
        <proframeHeader>
            <pfmAppName>BIS-KOFIABOND</pfmAppName>
            <pfmSvcName>BISLastAskPrcROPSrchSO</pfmSvcName>
            <pfmFnName>selectList</pfmFnName>
        </proframeHeader>
        <systemHeader></systemHeader>
        <BISComDspDatDTO>
            <val1>{today_str}</val1>
        </BISComDspDatDTO>
    </message>"""
    
    headers = {
        "Content-Type": "application/xml; charset=UTF-8",
        "User-Agent": "Mozilla/5.0"
    }
    
    resp = requests.post(url, data=xml_data.encode('utf-8'), headers=headers)
    print("Status:", resp.status_code)
    try:
        root = ET.fromstring(resp.text)
        items = root.findall(".//dbioList") or root.findall(".//BISLastAskPrcROPDTO") or root.findall(".//item")
        print(f"Found {len(items)} items")
        for item in items[:15]:
            data = {child.tag: child.text for child in item}
            print(data)
    except Exception as e:
        print("XML Parse Error:", e)
        print("Response excerpt:", resp.text[:500])

if __name__ == "__main__":
    test_kofia_yields()
