import argparse
import sys
from pathlib import Path

from .analysis import run_analysis
from .download import download_all


def main():
    parser=argparse.ArgumentParser(description='Berliner Baumbestand: Datenabruf und Analyse')
    sub=parser.add_subparsers(dest='command',required=True)
    download=sub.add_parser('download',help='Öffentliche WFS-Daten herunterladen und prüfen')
    download.add_argument('--data-dir',type=Path,default=Path('data/raw'))
    download.add_argument('--page-size',type=int,default=10000)
    download.add_argument('--timeout',type=int,default=90)
    download.add_argument('--refresh',action='store_true')
    analyze=sub.add_parser('analyze',help='Tabellen, Qualitätsbericht und fünf Grafiken erzeugen')
    analyze.add_argument('--data-dir',type=Path,default=Path('data/raw'))
    analyze.add_argument('--output-dir',type=Path,default=Path('results'))
    analyze.add_argument('--figure-dir',type=Path,default=Path('figures'))
    analyze.add_argument('--resolution',type=int,choices=range(0,16),default=9)
    analyze.add_argument('--snapshot-label',help='Kurze Herkunfts-/Datenstandsangabe für die Grafiken')
    args=parser.parse_args()
    try:
        if args.command=='download':
            if args.page_size<=0 or args.timeout<=0:
                parser.error('page-size und timeout müssen positiv sein')
            download_all(args.data_dir,args.page_size,args.timeout,args.refresh)
        else:
            run_analysis(args.data_dir,args.output_dir,args.figure_dir,args.resolution,args.snapshot_label)
    except Exception as exc:
        print(f'Fehler: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
