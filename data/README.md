# Datenquellen

| Inhalt | WFS-Dienst | Layer | Sortierung |
|---|---|---|---|
| Straßenbäume | https://gdi.berlin.de/services/wfs/baumbestand | baumbestand:strassenbaeume | gisid |
| Anlagenbäume | https://gdi.berlin.de/services/wfs/baumbestand | baumbestand:anlagenbaeume | gisid |
| Bezirke | https://gdi.berlin.de/services/wfs/alkis_bezirke | alkis_bezirke:bezirksgrenzen | name |

Die öffentlich veröffentlichten Datensatzbeschreibungen nennen jeweils **dl-de-zero-2.0**:

- [Baumbestand Berlin](https://daten.berlin.de/datensaetze/baumbestand-berlin-wfs-48ad3a23)
- [ALKIS Berlin Bezirke](https://daten.berlin.de/datensaetze/alkis-berlin-bezirke-wfs-ced31d7d)

Der Download behält für Bäume ausschließlich Gattungsbezeichnungen, Bezirk, Standalter, Feature-ID und Geometrie. Eigentümer-, Straßen- und Hausnummernfelder werden nicht gespeichert. Die Feature-ID dient der Vollständigkeitsprüfung; eine Standortnummer allein ist keine geeignete berlinweite ID.

Die Quelldateien und ihre Metadaten entstehen unter `data/raw/` und werden nicht mit Git versioniert. Die Metadaten enthalten UTC-Abrufzeiten, Layer, Datensatzanzahl, Prüfsumme und die Zeitstempel der WFS-Antworten. Diese Zeitstempel bezeichnen keine individuellen Erhebungszeitpunkte der Bäume.

Das öffentliche [Ergebnismanifest](../results/summary.json) dokumentiert die Quellen der mitgelieferten Analyse. Die Rohdaten sind veränderlich; identische Ergebnisse setzen identische Quelldateien voraus. Das Repository enthält ausschließlich aggregierte Ergebnisse und keine Einzelbaumdateien.
