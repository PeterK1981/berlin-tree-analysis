"""Publication figures with explicit denominators and missing-value categories."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np

from .analysis import AGE_LABELS, UNKNOWN

COLORS = ['#0072B2','#D55E00','#009E73','#E69F00','#CC79A7','#56B4E9']


def finish(fig, path, label, note):
    fig.text(.03,.035,note,fontsize=9,color='#39434b',va='bottom')
    fig.text(.03,.012,f'Quelle: Geoportal Berlin · {label}',fontsize=7,color='#59636b',va='bottom')
    fig.savefig(path,dpi=160,facecolor='white')
    plt.close(fig)


def base_map(boundaries, title, subtitle):
    fig,ax=plt.subplots(figsize=(10,10))
    fig.subplots_adjust(left=.03,right=.92,top=.88,bottom=.12)
    boundaries.plot(ax=ax,color='#f0f2f2',edgecolor='#78858b',linewidth=.5)
    ax.set_axis_off()
    ax.set_aspect('equal')
    fig.text(.03,.95,title,fontsize=20,weight='bold')
    fig.text(.03,.915,subtitle,fontsize=11,color='#39434b')
    return fig,ax


def make_figures(composition,districts,ages,hexagons,boundaries,directory,label,resolution):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    fig,ax=base_map(boundaries,'Straßenbäume in Berlin',
                    f'Erfasste Straßenbäume pro belegter H3-Zelle · Auflösung {resolution}')
    cap=max(1,float(hexagons['count'].quantile(.99)))
    norm=Normalize(0,cap,clip=True)
    hexagons.plot(ax=ax,column='count',cmap='YlGnBu',norm=norm,edgecolor='none')
    boundaries.boundary.plot(ax=ax,color='#65747b',linewidth=.55)
    cb=fig.colorbar(ScalarMappable(norm=norm,cmap='YlGnBu'),ax=ax,shrink=.5,pad=.01,extend='max')
    cb.set_label('Erfasste Straßenbäume je Zelle')
    finish(fig,directory/'street_tree_counts.png',label,
           f'Alle belegten Zellen bleiben sichtbar; Farbskala ab {cap:.0f} Bäumen gesättigt (99%-Quantil).\n'
           'Graue Flächen: keine dargestellte Zählung. Keine Aussage über die gesamte Vegetation.')

    street=composition.loc[(composition.kind=='Straße') & composition.genus.ne(UNKNOWN)]
    top=street.sort_values(['count','genus'],ascending=[False,True]).head(6).genus.tolist()
    palette=dict(zip(top,COLORS))
    palette.update({'Andere Gattung':'#8b9a83','Gleichstand':'#b65fa2',UNKNOWN:'#333333'})
    groups=hexagons.dominant_genus.where(hexagons.dominant_genus.isin(palette),'Andere Gattung')
    fig,ax=base_map(boundaries,'Welche Gattungen überwiegen?',
                    f'Häufigste bekannte Gattungsgruppe pro belegter Straßenbaumzelle · H3 {resolution}')
    hexagons.plot(ax=ax,color=groups.map(palette),edgecolor='none')
    boundaries.boundary.plot(ax=ax,color='#65747b',linewidth=.55)
    handles=[Patch(facecolor=c,label=g.title() if g in top else g)
             for g,c in palette.items() if g in set(groups)]
    fig.subplots_adjust(bottom=.22)
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.155),
               ncol=3,fontsize=9,frameon=False)
    finish(fig,directory/'dominant_genus.png',label,
           'Gleich häufige Spitzenreiter sind als Gleichstand markiert. Andere Gattungen bleiben sichtbar.\n'
           'Unbekannt: keine bekannte Gattungsangabe in der Zelle. Häufigste Gruppe bedeutet nicht Mehrheit.')

    totals=composition.groupby('genus')['count'].sum().sort_values(ascending=False)
    selected=[g for g in totals.index if g!=UNKNOWN][:8]
    labels=selected+['Andere Gattungen',UNKNOWN]
    fig,ax=plt.subplots(figsize=(11,6.5))
    fig.subplots_adjust(left=.19,right=.97,top=.84,bottom=.19)
    y=np.arange(len(labels))
    for delta,(kind,c) in zip([-.19,.19],[('Straße',COLORS[0]),('Anlage',COLORS[1])]):
        subset=composition.loc[composition.kind==kind].set_index('genus')['count']
        values=[subset.get(g,0) for g in selected]
        values += [subset.loc[~subset.index.isin(selected+[UNKNOWN])].sum(),subset.get(UNKNOWN,0)]
        ax.barh(y+delta,np.array(values)/subset.sum(),height=.36,color=c,label=f'{kind} (n={subset.sum():,})')
    ax.set_yticks(y,[g.title() for g in labels]);ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(1));ax.set_xlabel('Anteil an allen erfassten Bäumen des jeweiligen Typs')
    ax.legend(loc='lower right');ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Straßen- und Anlagenbäume im Vergleich',fontsize=18,weight='bold',y=.95)
    finish(fig,directory/'genus_composition.png',label,
           'Top 8 Gattungsgruppen nach gemeinsamer Anzahl; übrige bekannte Gruppen zusammengefasst.\n'
           'Fehlende Gattungsangaben bleiben im Nenner und werden gesondert dargestellt.')

    valid=districts.loc[districts.district.ne(UNKNOWN)]
    order=valid.groupby('district').effective_genera.mean().sort_values().index.tolist()
    fig,ax=plt.subplots(figsize=(11,7.5))
    fig.subplots_adjust(left=.29,right=.96,top=.86,bottom=.20)
    for kind,c,marker in [('Straße',COLORS[0],'o'),('Anlage',COLORS[1],'s')]:
        subset=valid.loc[valid.kind==kind].set_index('district').reindex(order)
        ax.scatter(subset.effective_genera,np.arange(len(order)),color=c,marker=marker,s=55,label=kind)
    ax.set_yticks(range(len(order)),order)
    ax.set_xlabel('Effektive Anzahl der Gattungsgruppen: exp(Shannon-Entropie)')
    ax.legend();ax.grid(axis='x',alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Gattungsdiversität nach Bezirk',fontsize=18,weight='bold',y=.95)
    finish(fig,directory/'district_diversity.png',label,
           'Berechnung nur für Bäume mit bekannter Gattungsgruppe; keine Klimaresilienzbewertung.\n'
           'Abdeckung und Fallzahlen je Bezirk stehen in results/districts.csv; Bestände sind unterschiedlich erfasst.')

    fig,ax=plt.subplots(figsize=(11,6))
    fig.subplots_adjust(left=.09,right=.97,top=.84,bottom=.23)
    x=np.arange(len(AGE_LABELS))
    for delta,(kind,c) in zip([-.19,.19],[('Straße',COLORS[0]),('Anlage',COLORS[1])]):
        subset=ages.loc[ages.kind==kind].set_index('age_class')['share'].reindex(AGE_LABELS,fill_value=0)
        ax.bar(x+delta,subset,width=.36,color=c,label=kind)
    ax.set_xticks(x,AGE_LABELS);ax.set_xlabel('Standalter in Jahren laut Quelldaten')
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylabel('Anteil am erfassten Bestand')
    ax.legend();ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Altersstruktur und fehlende Altersangaben',fontsize=18,weight='bold',y=.95)
    finish(fig,directory/'age_structure.png',label,
           'Nenner: alle Bäume des jeweiligen Typs, einschließlich unbekannten Alters.\n'
           '140+ ist eine offene Klasse. Hohe Altersangaben werden übernommen und im Qualitätsbericht gezählt.')
