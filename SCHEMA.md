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

## Module 2 output — `reconstruct_walls.py `

walls=776 doors=16 windows=0 intersections=448 footprints=679 unclosable=97

## Module 3 output — `detect_openings.py`
INFO     Loaded 776 walls, 16 doors, 0 windows
INFO     Opening defaults: {'DOOR': {'height_mm': 2100.0, 'sill_mm': 0.0}, 'WINDOW': {'height_mm': 1200.0, 'sill_mm': 900.0}}
Opening 846 rotation 270.0° rejected: wall 1A8 angle 8.1°, diff 81.9° > 10.0° tolerance
WARNING  Opening 846 (DOOR) – no matching wall found, flagged for review
Opening 933 rotation 270.0° rejected: wall 307 angle 351.9°, diff 81.9° > 10.0° tolerance
WARNING  Opening 933 (DOOR) – no matching wall found, flagged for review
Opening AD2 rotation 270.0° rejected: wall 9B9 angle 0.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening AD2 (DOOR) – no matching wall found, flagged for review
Opening B38 (width 4623) does not fit wall 3BC (length 663): start=352 end=4974
WARNING  Opening B38 (DOOR) – invalid position on wall 3BC, flagged for review
Opening B39 (width 4623) does not fit wall 3C5 (length 807): start=-4311 end=311
WARNING  Opening B39 (DOOR) – invalid position on wall 3C5, flagged for review
Opening B51 (width 4123) does not fit wall 3DD (length 1243): start=932 end=5054
WARNING  Opening B51 (DOOR) – invalid position on wall 3DD, flagged for review
Opening B52 (width 4623) does not fit wall 3F2 (length 3202): start=-4311 end=311
WARNING  Opening B52 (DOOR) – invalid position on wall 3F2, flagged for review
Opening B53 (width 4623) does not fit wall 40A (length 607): start=-4311 end=311
WARNING  Opening B53 (DOOR) – invalid position on wall 40A, flagged for review
Opening B54 rotation 90.0° rejected: wall 1AA angle 180.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening B54 (DOOR) – no matching wall found, flagged for review
Opening F7A rotation 180.0° rejected: wall 944 angle 270.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening F7A (DOOR) – no matching wall found, flagged for review
Opening 1060 rotation 270.0° rejected: wall 474 angle 180.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening 1060 (DOOR) – no matching wall found, flagged for review
Opening 1150 rotation 270.0° rejected: wall 562 angle 180.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening 1150 (DOOR) – no matching wall found, flagged for review
Opening 4203 rotation 180.0° rejected: wall 1A8D angle 90.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening 4203 (DOOR) – no matching wall found, flagged for review
Opening 43AC rotation 0.0° rejected: wall 3F3 angle 90.0°, diff 90.0° > 10.0° tolerance
WARNING  Opening 43AC (DOOR) – no matching wall found, flagged for review
Opening 796E (width 5100) does not fit wall 1A3A (length 590): start=540 end=5640
WARNING  Opening 796E (DOOR) – invalid position on wall 1A3A, flagged for review
total_openings=16  matched=1  flagged_for_review=15  walls=776
