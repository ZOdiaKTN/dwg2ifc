DXF Header $INSUNITS: 4
============================================================
LAYER INVENTORY
============================================================

Layer: 0-1
  Total entities: 2
  Entity types:
    INSERT: 2

Layer: 0-2
  Total entities: 2
  Entity types:
    INSERT: 2

Layer: Annotations génériques
  Total entities: 3
  Entity types:
    INSERT: 3

Layer: Appareils sanitaires
  Total entities: 5
  Entity types:
    INSERT: 5

Layer: Arêtes communes
  Total entities: 34
  Entity types:
    LINE: 34

Layer: Barreaux
  Total entities: 6
  Entity types:
    INSERT: 6

Layer: Bords de dalles
  Total entities: 9
  Entity types:
    LINE: 9

Layer: Contours
  Total entities: 17
  Entity types:
    LINE: 17

Layer: Cote de coordonnées
  Total entities: 15
  Entity types:
    HATCH: 2
    INSERT: 1
    LINE: 11
    MTEXT: 1

Layer: Cotes d_élévation
  Total entities: 10
  Entity types:
    INSERT: 5
    MTEXT: 5

Layer: Dashed
  Total entities: 152
  Entity types:
    LINE: 152

Layer: Doors_Other
  Total entities: 7
  Entity types:
    INSERT: 7

Layer: Eléments de détail
  Total entities: 2
  Entity types:
    INSERT: 2

Layer: Equipement spécialisé
  Total entities: 38
  Entity types:
    INSERT: 38

Layer: Equipement spécialisé-1
  Total entities: 5
  Entity types:
    INSERT: 5

Layer: Escalier-1
  Total entities: 15
  Entity types:
    HATCH: 15

Layer: Etiquettes de pièces
  Total entities: 34
  Entity types:
    MTEXT: 34

Layer: Flèches vers le haut
  Total entities: 2
  Entity types:
    LINE: 2

Layer: Lignes de contremarche
  Total entities: 16
  Entity types:
    LINE: 16

Layer: Lignes de nez de marche
  Total entities: 14
  Entity types:
    LINE: 14

Layer: MB-uszczelki_tworzywa
  Total entities: 35
  Entity types:
    INSERT: 35

Layer: Meubles de rangement
  Total entities: 1
  Entity types:
    INSERT: 1

Layer: Mobilier
  Total entities: 3
  Entity types:
    INSERT: 3

Layer: Motif de coupe-1
  Total entities: 60
  Entity types:
    HATCH: 60

Layer: Murs
  Total entities: 273
  Entity types:
    LINE: 273

Layer: Murs-1
  Total entities: 486
  Entity types:
    LINE: 486

Layer: Murs-2
  Total entities: 17
  Entity types:
    HATCH: 17

Layer: Notes textuelles
  Total entities: 57
  Entity types:
    HATCH: 2
    LINE: 10
    MTEXT: 45

Layer: Numéros de marche_contremarche d_escalier
  Total entities: 20
  Entity types:
    MTEXT: 20

Layer: Panneau
  Total entities: 6
  Entity types:
    INSERT: 6

Layer: Plan Swing
  Total entities: 3
  Entity types:
    INSERT: 3

Layer: Portes
  Total entities: 9
  Entity types:
    INSERT: 9

Layer: Sols
  Total entities: 121
  Entity types:
    LINE: 121

Layer: Symboles de coupe
  Total entities: 15
  Entity types:
    LINE: 15

Layer: Systèmes de mobilier
  Total entities: 2
  Entity types:
    INSERT: 2

Layer: Trajectoires d_escalier
  Total entities: 1
  Entity types:
    MTEXT: 1

Layer: Traverses hautes
  Total entities: 12
  Entity types:
    INSERT: 12

Layer: _Au-dessus_ Contours
  Total entities: 9
  Entity types:
    LINE: 9

Layer: _Au-dessus_ Lignes de contremarche
  Total entities: 6
  Entity types:
    LINE: 6

Layer: _Au-dessus_ Lignes de nez de marche
  Total entities: 6
  Entity types:
    LINE: 6

Layer: _Au-dessus_ Symboles de coupe
  Total entities: 15
  Entity types:
    LINE: 15

Layer: _Couches d_isolation_
  Total entities: 332
  Entity types:
    SPLINE: 332

Layer: _MB_uszczelki_0_15
  Total entities: 1
  Entity types:
    INSERT: 1

Layer: _Séparation de pièce_
  Total entities: 43
  Entity types:
    LINE: 43

## Module 1 output — `parse_dxf.py`

```json
{
  "walls": [
    {
      "id": "1A1",
      "vertices": [
        [46421.016958, -263030.693074],
        [46419.554644, -256630.693241]
      ],
      "closed": false
    }
  ],
  "doors": [
    {
      "id": "846",
      "category": "DOOR",
      "insertion_point": [46269.406131, -255980.727531],
      "rotation_deg": 270.0130913229237,
      "block_name": "Doors_Door-sets_Swedoor_JELD-WEN_Exterior_Steel_4210_Unequal_Double_40 - SNR_PuertaEmergencia_1300x2200 2-8074706-NIVEAU RDC",
      "estimated_width_mm": 1360.0
    }
  ],
  "windows": []
}
```

Counts from `test1.dxf`: **759 walls, 16 doors, 0 windows, 17 warnings**.
