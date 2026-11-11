"""Validated, paginated WFS downloads with portable provenance metadata."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import truststore

DATASETS = {
    'street': ('baumbestand', 'strassenbaeume', 'gisid', 'baumbestand_strasse.geojson'),
    'park': ('baumbestand', 'anlagenbaeume', 'gisid', 'baumbestand_anlagen.geojson'),
    'districts': ('alkis_bezirke', 'bezirksgrenzen', 'name', 'bezirke_berlin.geojson'),
}
TREE_FIELDS = {'gattung_deutsch', 'gattung', 'bezirk', 'standalter'}
DISTRICT_FIELDS = {'name', 'namgem'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def session():
    # Use the operating system's trusted certificates, without disabling TLS checks.
    truststore.inject_into_ssl()
    client = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods={'GET'}, respect_retry_after_header=True)
    client.mount('https://', HTTPAdapter(max_retries=retry))
    client.headers['User-Agent'] = 'berlin-tree-analysis/1.0 (public WFS client)'
    return client


def matched_count(client, url, layer, timeout):
    response = client.get(url, params={'service': 'WFS', 'version': '2.0.0',
        'request': 'GetFeature', 'typeNames': layer, 'resultType': 'hits'}, timeout=timeout)
    response.raise_for_status()
    document = ET.fromstring(response.content)
    count = document.attrib.get('numberMatched')
    if count is None or not count.isdigit():
        raise ValueError(f'{layer}: service did not supply a verifiable total count')
    return int(count)


def validate_page(data, expected, seen, required):
    if data.get('type') != 'FeatureCollection':
        raise ValueError('WFS response is not a GeoJSON FeatureCollection')
    matched = data.get('numberMatched', data.get('totalFeatures'))
    if matched is not None and str(matched) != str(expected):
        raise ValueError('Dataset changed during pagination; retry the download')
    features = data.get('features')
    if not isinstance(features, list):
        raise ValueError('Missing GeoJSON feature list')
    for feature in features:
        identifier = feature.get('id')
        if not identifier or identifier in seen:
            raise ValueError('Missing or repeated feature ID; pagination cannot be verified')
        seen.add(identifier)
        properties = feature.get('properties') or {}
        if not required.issubset(properties):
            raise ValueError(f'Missing required fields: {sorted(required - properties.keys())}')
    return features


def download_dataset(client, key, directory, page_size=10000, timeout=90, refresh=False):
    service, name, sort_field, filename = DATASETS[key]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    metadata_path = target.with_suffix('.metadata.json')
    if target.exists() and not refresh:
        if not metadata_path.exists():
            raise ValueError(f'{filename}: cached file has no provenance; use --refresh')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if sha256(target) != metadata['sha256']:
            raise ValueError(f'{filename}: cached checksum differs; use --refresh')
        print(f'{key}: using verified cache ({metadata["feature_count"]:,} records)')
        return metadata
    url = f'https://gdi.berlin.de/services/wfs/{service}'
    layer = f'{service}:{name}'
    expected = matched_count(client, url, layer, timeout)
    if expected == 0:
        raise ValueError(f'{layer}: empty source dataset')
    seen, offset = set(), 0
    fields = DISTRICT_FIELDS if key == 'districts' else TREE_FIELDS
    temporary = target.with_suffix('.geojson.part')
    timestamps = set()
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            stream.write('{"type":"FeatureCollection","features":[')
            while offset < expected:
                response = client.get(url, params={'service': 'WFS', 'version': '2.0.0',
                    'request': 'GetFeature', 'typeNames': layer, 'outputFormat': 'application/json',
                    'srsName': 'EPSG:4326', 'sortBy': sort_field, 'count': page_size,
                    'startIndex': offset}, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                features = validate_page(data, expected, seen, fields)
                if not features:
                    raise ValueError(f'{layer}: empty page before total count was reached')
                if data.get('timeStamp'):
                    timestamps.add(data['timeStamp'])
                for feature in features:
                    slim = {'type': 'Feature', 'id': feature['id'],
                            'properties': {k: feature['properties'][k] for k in sorted(fields)},
                            'geometry': feature.get('geometry')}
                    if offset:
                        stream.write(',')
                    json.dump(slim, stream, ensure_ascii=False, separators=(',', ':'))
                    offset += 1
                print(f'{key}: {offset:,}/{expected:,}')
                time.sleep(.1)
            stream.write(']}')
        if offset != expected or matched_count(client, url, layer, timeout) != expected:
            raise ValueError(f'{layer}: final count mismatch; download was not accepted')
        metadata = {'source': url, 'layer': layer, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                    'feature_count': offset, 'crs': 'EPSG:4326', 'sort_field': sort_field,
                    'license': 'dl-de-zero-2.0', 'sha256': sha256(temporary),
                    'response_timestamps': sorted(timestamps), 'retained_fields': sorted(fields)}
        temporary.replace(target)
        meta_tmp = metadata_path.with_suffix('.json.part')
        meta_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        meta_tmp.replace(metadata_path)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)


def download_all(directory, page_size=10000, timeout=90, refresh=False):
    with session() as client:
        return {key: download_dataset(client, key, directory, page_size, timeout, refresh)
                for key in DATASETS}
