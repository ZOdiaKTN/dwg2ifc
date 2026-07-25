"""Pytest for dxf_inventory module."""

import pytest
import ezdxf
import tempfile
import os
from src.inventory import inventory_layers


@pytest.fixture
def synthetic_dxf_path():
    """Create a synthetic DXF file with a rectangle and a block insert."""
    # Create a new DXF document
    doc = ezdxf.new('R2010')
    
    # Set INSUNITS to inches (4 = inches, 1 = inches in some versions)
    doc.header['$INSUNITS'] = 4  # Inches
    
    # Get modelspace
    msp = doc.modelspace()
    
    # Create a rectangle on layer "A-WALL"
    # Rectangle: (0,0) to (10,5)
    points = [(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)]
    msp.add_lwpolyline(points, dxfattribs={'layer': 'A-WALL'})
    
    # Create a block definition for a door
    block = doc.blocks.new(name='DOOR')
    # Add a simple arc to represent a door swing
    block.add_arc(
        center=(0, 0),
        radius=2,
        start_angle=0,
        end_angle=90,
        dxfattribs={'layer': '0'}
    )
    block.add_line(
        start=(0, 0),
        end=(2, 2),
        dxfattribs={'layer': '0'}
    )
    
    # Insert the block on layer "A-DOOR"
    msp.add_blockref(
        'DOOR',
        insert=(5, 2.5),
        dxfattribs={'layer': 'A-DOOR'}
    )
    
    # Add another line to A-WALL for testing
    msp.add_line(
        start=(0, 5),
        end=(10, 5),
        dxfattribs={'layer': 'A-WALL'}
    )
    
    # Save to a temporary file
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
        doc.saveas(tmp.name)
        tmp_path = tmp.name
    
    yield tmp_path
    
    # Cleanup
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)


def test_inventory_layers(synthetic_dxf_path):
    """Test inventory_layers function with synthetic DXF."""
    inventory = inventory_layers(synthetic_dxf_path)
    
    # Check that we have the expected layers
    assert 'A-WALL' in inventory
    assert 'A-DOOR' in inventory
    
    # Check A-WALL layer
    wall_data = inventory['A-WALL']
    assert wall_data['total_count'] == 2  # 1 LWPOLYLINE + 1 LINE
    assert 'LWPOLYLINE' in wall_data['types']
    assert wall_data['types']['LWPOLYLINE'] == 1
    assert 'LINE' in wall_data['types']
    assert wall_data['types']['LINE'] == 1
    
    # Check A-DOOR layer
    door_data = inventory['A-DOOR']
    assert door_data['total_count'] == 1
    assert 'INSERT' in door_data['types']
    assert door_data['types']['INSERT'] == 1
    
    # Print the inventory for visual inspection
    from src.inventory import print_inventory
    print_inventory(inventory)