import unittest
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from berlin_trees.analysis import clean_trees,diversity,summarize,spatial_summary,UNKNOWN


class AnalysisTests(unittest.TestCase):
    def frame(self, genera=None):
        genera=genera or ['LINDE','AHORN',None,'LINDE']
        return gpd.GeoDataFrame({'gattung_deutsch':genera,'bezirk':['Mitte',None,'Mitte','Mitte'],
            'standalter':[10,None,-99,861]},geometry=[Point(13.4,52.5)]*4,crs=4326)

    def test_missing_values_do_not_remove_records(self):
        clean,q=clean_trees(self.frame(),'Straße')
        composition,districts,ages=summarize(clean)
        self.assertEqual(composition['count'].sum(),4)
        self.assertEqual(districts['count'].sum(),4)
        self.assertEqual(ages['count'].sum(),4)
        self.assertEqual(q['unknown_genus'],1)
        self.assertEqual(q['missing_or_invalid_age'],2)
        self.assertEqual(q['age_over_200'],1)
        self.assertEqual(clean.age_class.iloc[3],'140+')
        self.assertIn(UNKNOWN,districts.district.values)

    def test_diversity_known_cases(self):
        self.assertEqual(diversity([5]),(0.,1.))
        entropy,effective=diversity([10,10,10])
        self.assertAlmostEqual(entropy,np.log(3))
        self.assertAlmostEqual(effective,3)
        self.assertTrue(np.isnan(diversity([])[0]))

    def test_unknown_is_not_a_genus(self):
        frame=self.frame(['LINDE',None,None,'LINDE'])
        frame['bezirk']='Mitte'
        clean,_=clean_trees(frame,'Straße')
        _,districts,_=summarize(clean)
        self.assertEqual(districts.effective_genera.iloc[0],1)
        self.assertEqual(districts.known_genus_share.iloc[0],.5)

    def test_ties_and_spatial_count_conservation(self):
        frame=self.frame(['LINDE','AHORN','AHORN','LINDE'])
        clean,_=clean_trees(frame,'Straße')
        hexagons=spatial_summary(clean)
        self.assertEqual(hexagons['count'].sum(),4)
        self.assertEqual(hexagons.dominant_genus.iloc[0],'Gleichstand')
        self.assertAlmostEqual(hexagons.dominant_share_known.iloc[0],.5)
        self.assertGreater(hexagons.area_km2.iloc[0],0)

    def test_invalid_geometry_only_excluded_from_map(self):
        frame=self.frame()
        frame.loc[0,'geometry']=None
        clean,q=clean_trees(frame,'Straße')
        self.assertEqual(q['invalid_or_missing_geometry'],1)
        self.assertEqual(summarize(clean)[0]['count'].sum(),4)
        self.assertEqual(spatial_summary(clean)['count'].sum(),3)

    def test_all_unknown_cells_survive(self):
        clean,_=clean_trees(self.frame([None]*4),'Straße')
        hexagons=spatial_summary(clean)
        self.assertEqual(hexagons['count'].sum(),4)
        self.assertEqual(hexagons.dominant_genus.iloc[0],UNKNOWN)

    def test_missing_schema_is_an_error(self):
        with self.assertRaisesRegex(ValueError,'missing fields'):
            clean_trees(self.frame().drop(columns='bezirk'),'Straße')


if __name__=='__main__':
    unittest.main()
