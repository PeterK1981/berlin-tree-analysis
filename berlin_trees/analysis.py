"""Counts, data quality, genus-group diversity and spatial summaries."""
import json
from pathlib import Path

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from .download import DATASETS, sha256

UNKNOWN = 'Unbekannt'
AGE_LABELS = ['0–19', '20–39', '40–59', '60–79', '80–99', '100–139', '140+', UNKNOWN]
MISSING_LABELS = {'', 'NAN', 'NONE', '<NA>', 'UNBEKANNT', 'KEINE ANGABE', 'KEINE_ANGABE', '-'}


def clean_trees(frame, kind):
    required = {'gattung_deutsch', 'bezirk', 'standalter', 'geometry'}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'{kind}: missing fields {sorted(missing)}')
    if frame.crs is None:
        raise ValueError(f'{kind}: source CRS is missing')
    trees = frame[['gattung_deutsch', 'bezirk', 'standalter', 'geometry']].copy().to_crs(4326)
    trees['kind'] = kind
    genus = trees['gattung_deutsch'].astype('string').str.strip().str.upper()
    trees['genus'] = genus.mask(genus.isna() | genus.isin(MISSING_LABELS), UNKNOWN)
    district = trees['bezirk'].astype('string').str.strip()
    trees['district'] = district.mask(district.isna() | district.str.upper().isin(MISSING_LABELS), UNKNOWN)
    age = pd.to_numeric(trees['standalter'], errors='coerce')
    trees['age'] = age.where(np.isfinite(age) & age.ge(0))
    # All nonnegative source ages are retained, including very old records.
    trees['age_class'] = pd.cut(trees['age'], [0,20,40,60,80,100,140,np.inf],
                               labels=AGE_LABELS[:-1], right=False).astype('string').fillna(UNKNOWN)
    valid = trees.geometry.notna() & ~trees.geometry.is_empty & trees.geom_type.eq('Point')
    valid &= trees.geometry.is_valid
    candidates = trees.loc[valid]
    coordinates = (candidates.geometry.x.between(-180, 180) & candidates.geometry.y.between(-90, 90))
    valid.loc[candidates.index] = coordinates
    trees['valid_point'] = valid
    quality = {'records': len(trees), 'unknown_genus': int(trees.genus.eq(UNKNOWN).sum()),
               'unknown_district': int(trees.district.eq(UNKNOWN).sum()),
               'missing_or_invalid_age': int(trees.age.isna().sum()),
               'age_over_200': int(trees.age.gt(200).sum()),
               'invalid_or_missing_geometry': int((~valid).sum())}
    return trees, quality


def diversity(counts):
    values = np.asarray(counts, dtype=float)
    values = values[values > 0]
    if not len(values):
        return np.nan, np.nan
    proportions = values / values.sum()
    entropy = float(-(proportions*np.log(proportions)).sum())
    return entropy, float(np.exp(entropy))


def summarize(trees):
    composition = trees.groupby(['kind','genus'], dropna=False).size().rename('count').reset_index()
    composition['share'] = composition['count'] / composition.groupby('kind')['count'].transform('sum')
    rows = []
    for (kind, district), group in trees.groupby(['kind','district'], dropna=False):
        known = group.loc[group.genus.ne(UNKNOWN), 'genus']
        entropy, effective = diversity(known.value_counts())
        rows.append({'kind':kind, 'district':district, 'count':len(group), 'known_genus_count':len(known),
                     'known_genus_share':len(known)/len(group), 'genus_richness':known.nunique(),
                     'shannon':entropy, 'effective_genera':effective,
                     'known_age_count':int(group.age.notna().sum()),
                     'median_age':group.age.median() if group.age.notna().any() else np.nan})
    districts = pd.DataFrame(rows)
    ages = trees.groupby(['kind','age_class'], dropna=False).size().rename('count').reset_index()
    ages['share'] = ages['count']/ages.groupby('kind')['count'].transform('sum')
    return composition, districts, ages


def cell_for(lat, lon, resolution):
    if hasattr(h3, 'latlng_to_cell'):
        return h3.latlng_to_cell(lat, lon, resolution)
    return h3.geo_to_h3(lat, lon, resolution)


def cell_polygon(cell):
    boundary = h3.cell_to_boundary(cell) if hasattr(h3, 'cell_to_boundary') else h3.h3_to_geo_boundary(cell)
    return Polygon([(lon,lat) for lat,lon in boundary])


def spatial_summary(street, resolution=9):
    points = street.loc[street.valid_point].copy()
    if points.empty:
        raise ValueError('No valid street-tree coordinates available')
    points['cell'] = [cell_for(lat, lon, resolution) for lat,lon in
                      zip(points.geometry.y, points.geometry.x)]
    totals = points.groupby('cell').size().rename('count').to_frame()
    known = points.loc[points.genus.ne(UNKNOWN)]
    counts = known.groupby(['cell','genus']).size().rename('n').reset_index()
    if counts.empty:
        totals['dominant_genus'] = UNKNOWN
        totals['dominant_count'] = 0
    else:
        counts['maximum'] = counts.groupby('cell')['n'].transform('max')
        leaders = counts.loc[counts.n.eq(counts.maximum)]
        winners = leaders.groupby('cell').agg(dominant_genus=('genus','first'),
                                             dominant_count=('n','first'), ties=('genus','size'))
        winners.loc[winners.ties.gt(1),'dominant_genus'] = 'Gleichstand'
        totals = totals.join(winners.drop(columns='ties'))
        totals['dominant_genus'] = totals.dominant_genus.fillna(UNKNOWN)
        totals['dominant_count'] = totals.dominant_count.fillna(0).astype(int)
    totals['known_genus_count'] = known.groupby('cell').size().reindex(totals.index, fill_value=0)
    totals['dominant_share_known'] = totals.dominant_count / totals.known_genus_count.replace(0,np.nan)
    totals = totals.reset_index()
    hexagons = gpd.GeoDataFrame(totals, geometry=[cell_polygon(c) for c in totals.cell], crs=4326).to_crs(25833)
    hexagons['area_km2'] = hexagons.geometry.area / 1e6
    hexagons['count_per_full_cell_km2'] = hexagons['count'] / hexagons.area_km2
    return hexagons


def read_districts(path):
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError('District CRS is missing')
    column = next((c for c in ['namgem','BEZIRK','district'] if c in frame.columns),None)
    if column is None:
        raise ValueError('District name field missing')
    frame = frame[[column,'geometry']].rename(columns={column:'district'})
    if frame.geometry.isna().any() or (~frame.geometry.is_valid).any():
        raise ValueError('Invalid district boundary geometry')
    return frame.dissolve(by='district', as_index=False).to_crs(25833)


def run_analysis(data_dir, output_dir, figure_dir, resolution=9, snapshot_label=None):
    from .plots import make_figures
    data_dir, output_dir, figure_dir = map(Path, (data_dir,output_dir,figure_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    frames, quality, provenance = [], {}, {}
    for key,kind in [('street','Straße'),('park','Anlage')]:
        path = data_dir/DATASETS[key][3]
        frame = gpd.read_file(path)
        trees,quality[kind] = clean_trees(frame,kind)
        frames.append(trees)
        del frame
        provenance[key] = source_metadata(path)
    trees = pd.concat(frames,ignore_index=True)
    composition, districts, ages = summarize(trees)
    hexagons = spatial_summary(frames[0],resolution)
    boundary_path = data_dir/DATASETS['districts'][3]
    boundaries = read_districts(boundary_path)
    provenance['districts'] = source_metadata(boundary_path)
    unknown_names = set(trees.district.unique()) - set(boundaries.district) - {UNKNOWN}
    if unknown_names:
        raise ValueError(f'District names do not match boundaries: {sorted(unknown_names)}')
    street_points = frames[0].loc[frames[0].valid_point].to_crs(25833)
    berlin = boundaries.geometry.union_all()
    quality['Straße']['points_outside_boundary'] = int((~street_points.geometry.intersects(berlin)).sum())
    if int(composition['count'].sum()) != len(trees) or int(ages['count'].sum()) != len(trees):
        raise ValueError('Count conservation check failed')
    if int(hexagons['count'].sum()) != int(frames[0].valid_point.sum()):
        raise ValueError('Spatial aggregation lost records')
    for name,table in [('composition',composition),('districts',districts),('ages',ages)]:
        table.to_csv(output_dir/f'{name}.csv',index=False)
    hexagons.drop(columns='geometry').to_csv(output_dir/'street_hexagons.csv',index=False)
    label = snapshot_label or 'WFS-Abruf; Datenstand siehe Quellenmanifest'
    manifest = {'snapshot_label':label, 'sources':provenance, 'quality':quality,
                'h3_resolution':resolution, 'records_total':len(trees),
                'method':'Rows counted once per source layer; no cross-layer deduplication; genus groups from gattung_deutsch.'}
    (output_dir/'summary.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    make_figures(composition,districts,ages,hexagons,boundaries,figure_dir,label,resolution)
    print(f'Analyzed {len(trees):,} records; {len(hexagons):,} occupied street-tree cells.')
    return manifest


def source_metadata(path):
    meta = path.with_suffix('.metadata.json')
    checksum = sha256(path)
    if meta.exists():
        data = json.loads(meta.read_text(encoding='utf-8'))
        if data['sha256'] != checksum:
            raise ValueError(f'{path.name}: source checksum differs from metadata')
        return data
    return {'file':path.name, 'sha256':checksum, 'retrieved_at':None,
            'status':'Local archived source; retrieval date and WFS completeness not documented.'}
