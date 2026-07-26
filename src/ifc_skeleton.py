"""Minimal IFC2x3 hierarchy: IfcProject -> IfcSite -> IfcBuilding -> IfcBuildingStorey."""
from __future__ import annotations

import math

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.owner
import ifcopenshell.api.owner.settings
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit

MM_TO_M = 1000.0


def create_ifc_skeleton(floor_height_mm: float = 2700, output_path: str = "skeleton.ifc") -> str:
    """Create a minimal valid IFC2x3 file and save it.

    Parameters
    ----------
    floor_height_mm : float
        Height of the IfcBuildingStorey in mm.
    output_path : str
        Destination file path.

    Returns
    -------
    str
        The path to the saved file.
    """
    model = ifcopenshell.api.project.create_file(version="IFC2X3")

    # IFC2X3 requires OwnerHistory -- set up a minimal user and application.
    application = ifcopenshell.api.owner.add_application(model)
    person = ifcopenshell.api.owner.add_person(model, identification="DXF", given_name="DXF", family_name="Tool")
    org = ifcopenshell.api.owner.add_organisation(model, identification="DXF2IFC", name="DXF2IFC")
    user = ifcopenshell.api.owner.add_person_and_organisation(model, person=person, organisation=org)
    ifcopenshell.api.owner.settings.get_user = lambda _f: user
    ifcopenshell.api.owner.settings.get_application = lambda _f: application

    # Create the spatial hierarchy
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Minimal Project")
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Default Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Default Building")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Ground Floor")

    # Elevation is a direct attribute of IfcBuildingStorey, not a pset.
    storey.Elevation = 0.0

    # Link the hierarchy
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # Set up SI units (millimetres for length, m² for area, m³ for volume).
    ifcopenshell.api.unit.assign_unit(model)

    # Create geometric representation contexts for 3D body geometry.
    model3d = ifcopenshell.api.context.add_context(model, context_type="Model")
    ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model3d,
    )

    model.write(output_path)
    return output_path


def create_wall(
    model: ifcopenshell.file.file,
    storey: ifcopenshell.entity_instance,
    p1_mm: tuple[float, float],
    p2_mm: tuple[float, float],
    thickness_mm: float = 200.0,
    height_mm: float = 2700.0,
    wall_id: str | None = None,
) -> ifcopenshell.entity_instance:
    """Create an IfcWall with extruded solid geometry from two endpoints.

    Parameters
    ----------
    model : ifcopenshell.file.file
        The IFC model (must already have units assigned).
    storey : ifcopenshell.entity_instance
        The IfcBuildingStorey that will contain the wall.
    p1_mm : tuple[float, float]
        First endpoint of the wall centerline in millimetres.
    p2_mm : tuple[float, float]
        Second endpoint of the wall centerline in millimetres.
    thickness_mm : float
        Wall thickness in millimetres (default 200).
    height_mm : float
        Extrusion height in millimetres (default 2700).
    wall_id : str or None
        Optional identifier for the wall.

    Returns
    -------
    ifcopenshell.entity_instance
        The created IfcWall entity.
    """
    MM_TO_M = 1000.0

    # Convert mm to meters for create_2pt_wall (expects SI).
    p1 = (p1_mm[0] / MM_TO_M, p1_mm[1] / MM_TO_M)
    p2 = (p2_mm[0] / MM_TO_M, p2_mm[1] / MM_TO_M)
    height = height_mm / MM_TO_M
    thickness = thickness_mm / MM_TO_M

    # Create the IfcWall element.
    wall = ifcopenshell.api.root.create_entity(model, ifc_class="IfcWall", name=wall_id or "Wall")

    # Get the Body subcontext for 3D geometry.
    body_ctx = None
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body":
            body_ctx = ctx
            break
    if body_ctx is None:
        body_ctx = model.by_type("IfcGeometricRepresentationContext")[0]

    # Create the extruded solid shape representation.
    shape = ifcopenshell.api.geometry.create_2pt_wall(
        model, wall, body_ctx,
        p1=p1, p2=p2,
        elevation=0.0,
        height=height,
        thickness=thickness,
        is_si=True,
    )

    # Assign the representation to the wall.
    ifcopenshell.api.geometry.assign_representation(model, product=wall, representation=shape)

    # Contain the wall in the storey.
    ifcopenshell.api.spatial.assign_container(model, products=[wall], relating_structure=storey)

    return wall


def _get_body_context(model: ifcopenshell.file.file):
    """Return the Body subcontext, falling back to the first context."""
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body":
            return ctx
    return model.by_type("IfcGeometricRepresentationContext")[0]


def _wall_centerline(wall: ifcopenshell.entity_instance):
    """Return (p1, p2) in mm in global coordinates from the wall's profile.

    The wall profile is a rectangle whose long axis aligns with the wall
    centerline in local coordinates.  We extract the midpoints of the two
    short edges, then transform through the ObjectPlacement to get global coords.
    """
    import numpy as np
    for rep in wall.Representation.Representations:
        for item in rep.Items:
            if item.is_a("IfcExtrudedAreaSolid"):
                profile = item.SweptArea
                if profile.is_a("IfcArbitraryClosedProfileDef"):
                    pts = [tuple(p.Coordinates) for p in profile.OuterCurve.Points]
                    if len(pts) < 4:
                        continue
                    # Find the longest edge to determine wall direction.
                    best_len = 0.0
                    best_dir = (1.0, 0.0)
                    for i in range(len(pts) - 1):
                        dx = pts[i + 1][0] - pts[i][0]
                        dy = pts[i + 1][1] - pts[i][1]
                        seg_len = math.hypot(dx, dy)
                        if seg_len > best_len:
                            best_len = seg_len
                            best_dir = (dx / seg_len, dy / seg_len)
                    # Find edges perpendicular to wall direction and
                    # compute their midpoints -> centerline endpoints.
                    perp_midpoints = []
                    for i in range(len(pts) - 1):
                        dx = pts[i + 1][0] - pts[i][0]
                        dy = pts[i + 1][1] - pts[i][1]
                        seg_len = math.hypot(dx, dy)
                        if seg_len < 1e-6:
                            continue
                        dot = (dx / seg_len) * best_dir[0] + (dy / seg_len) * best_dir[1]
                        if abs(dot) < 0.5:
                            mx = (pts[i][0] + pts[i + 1][0]) / 2.0
                            my = (pts[i][1] + pts[i + 1][1]) / 2.0
                            perp_midpoints.append((mx, my))
                    if len(perp_midpoints) >= 2:
                        # Apply ObjectPlacement to transform to global coords.
                        try:
                            matrix = np.array(
                                ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
                            )
                        except Exception:
                            matrix = np.eye(4)
                        def _xform(pt_2d):
                            v = matrix @ np.array([pt_2d[0], pt_2d[1], 0.0, 1.0])
                            return (v[0], v[1])
                        p1 = _xform(perp_midpoints[0])
                        p2 = _xform(perp_midpoints[-1])
                        return (p1, p2)
    raise ValueError("Could not extract centerline from wall representation")


def _wall_extrusion_info(wall: ifcopenshell.entity_instance):
    """Return (thickness_m, height_m) from the wall's IfcExtrudedAreaSolid."""
    for rep in wall.Representation.Representations:
        for item in rep.Items:
            if item.is_a("IfcExtrudedAreaSolid"):
                profile = item.SweptArea
                if profile.is_a("IfcArbitraryClosedProfileDef"):
                    pts = profile.OuterCurve.Points
                    coords = [p.Coordinates for p in pts]
                    xs = [c[0] for c in coords]
                    ys = [c[1] for c in coords]
                    thickness = max(ys) - min(ys)
                    height = item.Depth
                    return (thickness, height)
    raise ValueError("Could not extract extrusion info from wall")


def create_opening_in_wall(
    model: ifcopenshell.file.file,
    wall: ifcopenshell.entity_instance,
    opening_width_mm: float,
    opening_height_mm: float,
    sill_height_mm: float = 0.0,
    center_along_mm: float | None = None,
    opening_id: str | None = None,
) -> tuple[ifcopenshell.entity_instance, ifcopenshell.entity_instance]:
    """Create an IfcOpeningElement and an IfcDoor, boolean-subtract from the wall.

    This produces the IFC relationships that DIALux uses:
      IfcWall -> IfcRelVoidsElement -> IfcOpeningElement
      IfcOpeningElement -> IfcRelFillsElement -> IfcDoor
    """
    body_ctx = _get_body_context(model)

    # Extract wall geometry (all in mm).
    p1, p2 = _wall_centerline(wall)
    wall_thickness_mm, wall_height_mm_raw = _wall_extrusion_info(wall)
    wall_len_mm = math.hypot(p2[0] - p1[0], p2[1] - p1[1])

    # Opening dimensions — add_wall_representation expects SI (meters).
    open_w_m = opening_width_mm / MM_TO_M
    open_h_m = opening_height_mm / MM_TO_M
    sill_m = sill_height_mm / MM_TO_M
    wall_thickness_m = wall_thickness_mm / MM_TO_M

    # Position along wall (mm).
    center = center_along_mm if center_along_mm is not None else wall_len_mm / 2.0

    # Wall direction unit vector (XY plane).
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if wall_len_mm < 1e-9:
        ux, uy = 1.0, 0.0
    else:
        ux, uy = dx / wall_len_mm, dy / wall_len_mm

    # Wall center point at the opening location (mm).
    cx = p1[0] + ux * center
    cy = p1[1] + uy * center

    # --- IfcOpeningElement ---
    opening = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcOpeningElement", name=opening_id or "Opening",
    )

    opening_shape = ifcopenshell.api.geometry.add_wall_representation(
        model, context=body_ctx,
        length=open_w_m, height=open_h_m, thickness=wall_thickness_m,
    )
    ifcopenshell.api.geometry.assign_representation(model, product=opening, representation=opening_shape)

    # Position: rotate to wall direction, translate to (cx, cy, sill) in mm.
    import numpy as np

    angle = math.atan2(dy, dx)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    matrix = np.array([
        [cos_a, -sin_a, 0, cx],
        [sin_a,  cos_a, 0, cy],
        [0,      0,     1, sill_height_mm],
        [0,      0,     0, 1],
    ])
    # Matrix is in model units (mm), not SI.
    import copy
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=opening, matrix=copy.deepcopy(matrix), is_si=False,
    )

    # --- IfcDoor ---
    door = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcDoor", name=(opening_id or "Opening") + "_Door",
    )
    door_shape = ifcopenshell.api.geometry.add_door_representation(
        model, context=body_ctx,
        overall_width=opening_width_mm, overall_height=opening_height_mm,
    )
    ifcopenshell.api.geometry.assign_representation(model, product=door, representation=door_shape)

    ifcopenshell.api.geometry.edit_object_placement(
        model, product=door, matrix=copy.deepcopy(matrix), is_si=False,
    )

    # Contain both in the same storey as the wall.
    storey = None
    for rel in wall.Decomposes:
        storey = rel.RelatingObject
        break
    if storey is None:
        # Fallback: find the storey via containment.
        for rel in model.by_type("IfcRelContainedInSpatialStructure"):
            if wall in rel.RelatedElements:
                storey = rel.RelatingStructure
                break
    if storey is not None:
        ifcopenshell.api.spatial.assign_container(model, products=[opening, door], relating_structure=storey)

    # --- IfcRelVoidsElement: wall -> opening ---
    owner = ifcopenshell.api.owner.create_owner_history(model)
    void_rel = model.createIfcRelVoidsElement(
        ifcopenshell.guid.new(), owner,
        "Voids " + (opening_id or ""), None,
        wall, opening,
    )

    # --- IfcRelFillsElement: opening -> door ---
    fill_rel = model.createIfcRelFillsElement(
        ifcopenshell.guid.new(), owner,
        "Fills " + (opening_id or ""), None,
        opening, door,
    )

    # --- Boolean subtraction on the wall's representation ---
    wall_reps = wall.Representation.Representations
    for rep in wall_reps:
        for item in rep.Items:
            if item.is_a("IfcExtrudedAreaSolid"):
                # We need the opening's solid to subtract.
                opening_solid = None
                for orep in opening.Representation.Representations:
                    for oitem in orep.Items:
                        if oitem.is_a("IfcExtrudedAreaSolid"):
                            opening_solid = oitem
                            break
                if opening_solid is not None:
                    ifcopenshell.api.geometry.add_boolean(
                        model, first_item=item,
                        second_items=[opening_solid], operator="DIFFERENCE",
                    )
                break

    return opening, door


def fix_profile_winding_order(model: ifcopenshell.file.file) -> None:
    """Reverse all IfcPolyline point orders used as OuterCurve of IfcArbitraryClosedProfileDef.

    IFC spec requires counter-clockwise winding for outer boundaries.
    ifcopenshell's add_wall_representation creates them clockwise.
    This function fixes every profile in the model so ODA viewer renders them.
    """
    for profile in model.by_type("IfcArbitraryClosedProfileDef"):
        curve = profile.OuterCurve
        if curve.is_a("IfcPolyline"):
            pts = list(curve.Points)
            if len(pts) >= 4:
                # Remove closing point, reverse, re-add closing point.
                # e.g. [(0,0),(0,T),(L,T),(L,0),(0,0)] -> [(0,0),(L,0),(L,T),(0,T),(0,0)]
                open_pts = pts[:-1]
                open_pts.reverse()
                curve.Points = open_pts + [pts[0]]


# ---------------------------------------------------------------------------
# Room loop detection & IfcSpace generation
# ---------------------------------------------------------------------------

def _snap_coord(x: float, y: float, precision: int = 6) -> tuple[int, int]:
    """Quantise (x, y) to integer grid for exact equality comparisons."""
    f = 10 ** precision
    return (round(x * f), round(y * f))


def find_room_loops(walls: list[dict], min_area_mm2: float = 1e6) -> list[list[list[float]]]:
    """Find closed wall-centerline loops that enclose rooms.

    Parameters
    ----------
    walls : list of dict
        Each wall dict must have ``vertices`` key with at least two ``[x, y]``
        pairs (the centerline).
    min_area_mm2 : float
        Minimum enclosed area in mm² to consider a loop a room (default 1 m²).

    Returns
    -------
    list of list of [x, y]
        Each inner list is the ordered vertex list of a closed room polygon.
    """
    from collections import defaultdict

    # Build adjacency: quantised endpoint -> list of (neighbour_quantised, wall_idx)
    adj: dict[tuple, list[tuple]] = defaultdict(list)
    wall_endpoints: list[tuple] = []

    for i, w in enumerate(walls):
        verts = w["vertices"]
        if len(verts) < 2:
            continue
        a = _snap_coord(verts[0][0], verts[0][1])
        b = _snap_coord(verts[-1][0], verts[-1][1])
        wall_endpoints.append((a, b))
        adj[a].append((b, i))
        adj[b].append((a, i))

    # DFS to find all simple cycles of length >= 3.
    # Cap max path length and total iterations to avoid exponential explosion.
    MAX_CYCLE_LEN = 50
    MAX_LOOPS = 1000
    MAX_ITER = 500_000
    seen_edges: set[tuple] = set()
    loops: list[list[tuple]] = []
    iterations = 0

    for start in list(adj.keys()):
        if len(loops) >= MAX_LOOPS:
            break
        # DFS from start, track path and visited edges.
        stack: list[tuple] = [(start, [start], set())]
        while stack:
            iterations += 1
            if iterations >= MAX_ITER or len(loops) >= MAX_LOOPS:
                break
            node, path, visited_edges = stack.pop()
            if len(path) > MAX_CYCLE_LEN:
                continue
            for neighbour, wall_idx in adj[node]:
                edge = (min(node, neighbour), max(node, neighbour))
                if edge in visited_edges:
                    continue
                if neighbour == start and len(path) >= 3:
                    loops.append(path)
                    continue
                if neighbour in path:
                    continue
                new_visited = visited_edges | {edge}
                stack.append((neighbour, path + [neighbour], new_visited))
        if iterations >= MAX_ITER or len(loops) >= MAX_LOOPS:
            break

    # Filter by area and convert back to float coordinates.
    f = 10 ** 6
    result: list[list[list[float]]] = []
    for loop in loops:
        pts = [(v[0] / f, v[1] / f) for v in loop]
        area = abs(_polygon_area(pts))
        if area >= min_area_mm2:
            result.append(pts)

    # Remove duplicate loops (same vertices in different order/rotation).
    unique: list[list[list[float]]] = []
    seen_signatures: set[tuple] = set()
    for pts in result:
        # Canonical signature: smallest vertex as start.
        min_idx = min(range(len(pts)), key=lambda i: (pts[i][1], pts[i][0]))
        rotated = pts[min_idx:] + pts[:min_idx]
        sig = tuple(tuple(round(c, 4) for c in p) for p in rotated)
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            unique.append(pts)

    return unique


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    """Signed area via the shoelace formula."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return area / 2.0


def _sort_loops_by_area(loops: list[list[list[float]]]) -> list[list[list[float]]]:
    """Sort loops by area descending; the outermost polygon comes first."""
    return sorted(loops, key=lambda pts: abs(_polygon_area(pts)), reverse=True)


def create_space(
    model: ifcopenshell.file.file,
    storey: ifcopenshell.entity_instance,
    polygon_mm: list[list[float]],
    floor_height_mm: float = 2700.0,
    space_name: str | None = None,
) -> ifcopenshell.entity_instance:
    """Create an IfcSpace from a closed 2D polygon extruded to *floor_height_mm*.

    All geometry is in mm (matching what create_2pt_wall produces).
    """
    from shapely.geometry import Polygon as ShapelyPolygon

    # Ensure polygon is closed.
    if polygon_mm[0] != polygon_mm[-1]:
        polygon_mm = list(polygon_mm) + [polygon_mm[0]]

    # Compute centroid for local placement (in mm).
    poly = ShapelyPolygon(polygon_mm)
    cx, cy = poly.centroid.x, poly.centroid.y

    # Create the IfcSpace.
    space = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcSpace", name=space_name or "Room",
    )

    body_ctx = _get_body_context(model)

    # Shift polygon to centroid-relative coords (all in mm).
    rel_pts = [(p[0] - cx, p[1] - cy) for p in polygon_mm]

    # Create IfcPolyline.
    ifc_points = []
    for x, y in rel_pts:
        pt = model.createIfcCartesianPoint((float(x), float(y)))
        ifc_points.append(pt)
    polyline = model.createIfcPolyline(ifc_points)

    # Create IfcArbitraryClosedProfileDef.
    profile = model.createIfcArbitraryClosedProfileDef("AREA", None, polyline)

    # Create IfcAxis2Placement3D at centroid (mm).
    location = model.createIfcCartesianPoint((cx, cy, 0.0))
    z_dir = model.createIfcDirection((0.0, 0.0, 1.0))
    x_dir = model.createIfcDirection((1.0, 0.0, 0.0))
    placement = model.createIfcAxis2Placement3D(location, z_dir, x_dir)

    # Extruded direction.
    extrude_dir = model.createIfcDirection((0.0, 0.0, 1.0))

    # Create IfcExtrudedAreaSolid (height in mm).
    solid = model.createIfcExtrudedAreaSolid(profile, placement, extrude_dir, floor_height_mm)

    # Wrap in IfcShapeRepresentation.
    body = body_ctx
    shape_rep = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])

    # Create ProductDefinitionShape.
    pds = model.createIfcProductDefinitionShape(None, None, [shape_rep])
    space.Representation = pds

    # Set ObjectPlacement (mm).
    loc2 = model.createIfcCartesianPoint((cx, cy, 0.0))
    pl2 = model.createIfcAxis2Placement3D(loc2, z_dir, x_dir)
    local_placement = model.createIfcLocalPlacement(None, pl2)
    space.ObjectPlacement = local_placement

    # Contain in storey (IfcSpace uses aggregation, not containment).
    ifcopenshell.api.aggregate.assign_object(model, products=[space], relating_object=storey)

    return space
