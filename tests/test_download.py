import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from berlin_trees.download import download_dataset,validate_page,TREE_FIELDS


def feature(i):
    return {'type':'Feature','id':f'tree.{i}',
            'properties':{'gattung_deutsch':'Linde','gattung':'Tilia','bezirk':'Mitte','standalter':20,
                          'strname':'Not retained','eigentuemer':'Not retained'},
            'geometry':{'type':'Point','coordinates':[13.4,52.5]}}


class Response:
    def __init__(self,data=None,count=3):
        self.data=data
        self.content=f'<FeatureCollection numberMatched="{count}"/>'.encode()
    def raise_for_status(self):pass
    def json(self):return self.data


class Client:
    def __init__(self,repeat=False):self.offsets=[];self.repeat=repeat
    def get(self,url,params,timeout):
        if params.get('resultType')=='hits':return Response()
        offset=params['startIndex'];self.offsets.append(offset)
        records=[feature(0),feature(1)] if offset==0 or self.repeat else [feature(2)]
        return Response({'type':'FeatureCollection','numberMatched':3,'features':records})


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)

    @patch('berlin_trees.download.time.sleep')
    def test_short_pages_still_complete_and_cache_is_verified(self,sleep):
        client=Client()
        metadata=download_dataset(client,'street',self.root,page_size=10)
        self.assertEqual(client.offsets,[0,2])
        self.assertEqual(metadata['feature_count'],3)
        target=self.root/'baumbestand_strasse.geojson'
        saved=json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(len(saved['features']),3)
        self.assertEqual(set(saved['features'][0]['properties']),TREE_FIELDS)
        download_dataset(client,'street',self.root)
        self.assertEqual(client.offsets,[0,2])
        target.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'checksum'):
            download_dataset(client,'street',self.root)

    @patch('berlin_trees.download.time.sleep')
    def test_repeated_page_does_not_replace_existing_data(self,sleep):
        target=self.root/'baumbestand_strasse.geojson'
        target.write_text('original',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'repeated'):
            download_dataset(Client(repeat=True),'street',self.root,refresh=True)
        self.assertEqual(target.read_text(encoding='utf-8'),'original')
        self.assertFalse(list(self.root.glob('*.part')))

    def test_schema_and_changing_count_rejected(self):
        with self.assertRaisesRegex(ValueError,'changed'):
            validate_page({'type':'FeatureCollection','numberMatched':4,'features':[]},3,set(),TREE_FIELDS)
        bad=feature(0);del bad['properties']['bezirk']
        with self.assertRaisesRegex(ValueError,'required fields'):
            validate_page({'type':'FeatureCollection','numberMatched':1,'features':[bad]},1,set(),TREE_FIELDS)


if __name__=='__main__':
    unittest.main()
