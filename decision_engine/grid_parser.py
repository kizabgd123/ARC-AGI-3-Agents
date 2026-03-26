"""
Grid Parser for ARC-AGI-3 LockSmith Game

Extracts game state from raw grid data:
- Player position and state
- Object locations (door, rotator, energy pills, walls)
- Energy levels
- Key-door match status
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# Color code mappings
COLOR_CODES = {
    0: "black",
    2: "red",
    4: "green",
    6: "blue",
    7: "yellow",
    8: "orange",
    9: "purple",
    10: "white",
    11: "gray",
}

# Object signatures
PLAYER_SIGNATURE = [[0, 0, 0], [4, 4, 4], [4, 4, 4]]  # 3x3 green base
WALL_COLOR = 10
FLOOR_COLOR = 8
DOOR_BORDER_COLOR = 11
ENERGY_PILL_COLOR = 6
ROTATOR_COLORS = {9, 4, 7, 2}  # purple, green, yellow, red


class GridParser:
    """Parse ARC-AGI-3 grid to extract game state."""

    def __init__(self, grid_size: int = 64):
        self.grid_size = grid_size

    def parse_grid(self, grid: List[List[int]]) -> Dict[str, Any]:
        """
        Parse raw grid and extract all game state information.

        Args:
            grid: 64x64 matrix of integers (0-15)

        Returns:
            Dictionary with extracted game state
        """
        grid_array = np.array(grid)

        return {
            "player_position": self._find_player(grid_array),
            "player_direction": self._find_player_direction(grid_array),
            "energy": self._extract_energy_level(grid_array),
            "energy_pill_visible": self._find_energy_pills(grid_array),
            "energy_pill_positions": self._get_energy_pill_positions(grid_array),
            "door_position": self._find_exit_door(grid_array),
            "door_key_pattern": self._extract_door_pattern(grid_array),
            "key_position": self._find_key_display(grid_array),
            "key_pattern": self._extract_key_pattern(grid_array),
            "key_matches_door": self._check_key_door_match(grid_array),
            "rotator_position": self._find_rotator(grid_array),
            "wall_positions": self._get_wall_positions(grid_array),
            "walkable_area": self._get_walkable_area(grid_array),
            "grid_bounds": (0, self.grid_size - 1, 0, self.grid_size - 1),
        }

    def _find_player(self, grid: np.ndarray) -> Tuple[int, int]:
        """Find player position (4x4 green/black square)."""
        # Look for the characteristic 4x4 player pattern
        # Player has green (4) and black (0) pixels
        for i in range(self.grid_size - 3):
            for j in range(self.grid_size - 3):
                region = grid[i : i + 4, j : j + 4]
                # Check for player signature (simplified)
                if self._is_player_region(region):
                    return (j, i)  # Return (x, y) = (col, row)

        # Fallback: find center of green mass
        green_mask = grid == 4
        if np.any(green_mask):
            coords = np.argwhere(green_mask)
            center = coords.mean(axis=0).astype(int)
            return (center[1], center[0])

        return (32, 32)  # Default center

    def _is_player_region(self, region: np.ndarray) -> bool:
        """Check if region matches player signature."""
        # Player is 4x4 with specific pattern
        # Simplified check: mostly green (4) with some black (0)
        unique_colors = set(region.flatten())
        return 4 in unique_colors and 0 in unique_colors

    def _find_player_direction(self, grid: np.ndarray) -> str:
        """Determine player facing direction from shape."""
        # Analyze player region to determine orientation
        # Placeholder - would need detailed shape analysis
        return "unknown"

    def _extract_energy_level(self, grid: np.ndarray) -> int:
        """
        Extract energy level from row 61 (energy indicator row).

        Energy is shown as:
        - Unused energy: 1x1 INT<6> (blue)
        - Used energy: 1x1 INT<8> (orange)
        - Total: 25 energy per life
        """
        try:
            # Row 61 contains energy indicators
            energy_row = grid[61, :]

            # Count blue pixels (unused energy)
            unused_energy = np.sum(energy_row == 6)

            # Each blue pixel = 1 energy unit
            return min(25, unused_energy)
        except Exception as e:
            logger.warning(f"Failed to extract energy level: {e}")
            return 25  # Default full energy

    def _find_energy_pills(self, grid: np.ndarray) -> bool:
        """Check if energy pills (2x2 blue squares) are visible."""
        pills = self._get_energy_pill_positions(grid)
        return len(pills) > 0

    def _get_energy_pill_positions(self, grid: np.ndarray) -> List[Tuple[int, int]]:
        """Find all energy pill positions (2x2 INT<6> squares)."""
        positions = []

        for i in range(self.grid_size - 1):
            for j in range(self.grid_size - 1):
                region = grid[i : i + 2, j : j + 2]
                # Check for 2x2 blue square
                if np.all(region == 6):
                    positions.append((j, i))

        return positions

    def _find_exit_door(self, grid: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Find exit door (4x4 square with INT<11> gray border).

        Returns:
            (x, y) position of door center, or None if not found
        """
        for i in range(self.grid_size - 3):
            for j in range(self.grid_size - 3):
                region = grid[i : i + 4, j : j + 4]

                # Check for door border (gray = 11)
                border_pixels = np.concatenate(
                    [
                        region[0, :],  # Top row
                        region[-1, :],  # Bottom row
                        region[:, 0],  # Left column
                        region[:, -1],  # Right column
                    ]
                )

                if np.sum(border_pixels == 11) >= 12:  # At least 12 gray border pixels
                    return (j + 2, i + 2)  # Return center

        return None

    def _extract_door_pattern(self, grid: np.ndarray) -> Optional[np.ndarray]:
        """Extract the key pattern from center of exit door (2x2)."""
        door_pos = self._find_exit_door(grid)
        if not door_pos:
            return None

        x, y = door_pos
        # Extract 2x2 center pattern
        try:
            pattern = grid[y - 1 : y + 1, x - 1 : x + 1]
            return pattern
        except Exception:
            return None

    def _find_key_display(self, grid: np.ndarray) -> Optional[Tuple[int, int]]:
        """Find key display position (bottom-left corner, 6x6 square)."""
        # Key is typically shown in bottom-left corner
        # Search bottom-left quadrant
        bottom_left = grid[40:, :24]

        if np.any(bottom_left):
            # Find the 6x6 key region
            coords = np.argwhere(bottom_left != 0)
            if len(coords) > 0:
                min_y, min_x = coords.min(axis=0)
                return (min_x, min_y + 40)  # Adjust for offset

        return None

    def _extract_key_pattern(self, grid: np.ndarray) -> Optional[np.ndarray]:
        """Extract 6x6 key pattern from bottom-left corner."""
        try:
            # Key is in bottom-left 6x6 area
            key_region = grid[58:64, :6]
            return key_region
        except Exception:
            return None

    def _check_key_door_match(self, grid: np.ndarray) -> bool:
        """
        Check if current key pattern matches exit door target pattern.

        Key is 6x6, door pattern is 2x2 (scaled down 2X).
        Need to compare core design elements.
        """
        key_pattern = self._extract_key_pattern(grid)
        door_pattern = self._extract_door_pattern(grid)

        if key_pattern is None or door_pattern is None:
            return False

        # Simplified comparison: check if dominant colors match
        # In production, would need proper pattern matching

        # Downscale key to 3x3 (average pooling)
        key_downscaled = self._downscale_pattern(key_pattern, 3)
        door_downscaled = self._downscale_pattern(door_pattern, 2)

        # Compare patterns
        return np.array_equal(key_downscaled, door_downscaled)

    def _downscale_pattern(self, pattern: np.ndarray, target_size: int) -> np.ndarray:
        """Downscale pattern to target size using mode."""
        # Simplified: just take the mode color
        unique, counts = np.unique(pattern, return_counts=True)
        mode_color = unique[np.argmax(counts)]
        return np.full((target_size, target_size), mode_color)

    def _find_rotator(self, grid: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Find key rotator (3x3 or 4x4 with INT<9> purple and INT<4> green).

        Shape:
        4 9 9
        9 7 7
        9 7 9
        """
        for i in range(self.grid_size - 2):
            for j in range(self.grid_size - 2):
                region = grid[i : i + 3, j : j + 3]

                # Check for rotator colors
                has_purple = np.any(region == 9)
                has_green = np.any(region == 4)
                has_yellow = np.any(region == 7)

                if has_purple and has_green and has_yellow:
                    return (j + 1, i + 1)  # Return center

        return None

    def _get_wall_positions(self, grid: np.ndarray) -> List[Tuple[int, int]]:
        """Get all wall positions (INT<10> white)."""
        wall_mask = grid == 10
        coords = np.argwhere(wall_mask)
        return [(coord[1], coord[0]) for coord in coords]

    def _get_walkable_area(self, grid: np.ndarray) -> List[Tuple[int, int]]:
        """Get all walkable floor positions (INT<8> orange)."""
        floor_mask = grid == 8
        coords = np.argwhere(floor_mask)
        return [(coord[1], coord[0]) for coord in coords]

    def get_game_state_for_decision_engine(
        self, grid: List[List[int]], frames: List[Any]
    ) -> Dict[str, Any]:
        """
        Extract game state formatted for Decision Engine.

        Args:
            grid: 64x64 raw grid
            frames: List of previous frames for history analysis

        Returns:
            Game state dictionary for decision engine
        """
        parsed = self.parse_grid(grid)

        # Add derived state
        player_pos = parsed["player_position"]
        door_pos = parsed["door_position"]

        # Calculate distance to door
        if door_pos:
            distance_to_door = np.sqrt(
                (player_pos[0] - door_pos[0]) ** 2 + (player_pos[1] - door_pos[1]) ** 2
            )
        else:
            distance_to_door = 100.0  # Unknown

        # Check nearby walls (within 5 cells)
        walls = parsed["wall_positions"]
        nearby_walls = [
            w
            for w in walls
            if abs(w[0] - player_pos[0]) <= 5 and abs(w[1] - player_pos[1]) <= 5
        ]

        # Get last action from frames
        last_action = None
        if frames and len(frames) > 0 and hasattr(frames[-1], "action_input"):
            if frames[-1].action_input:
                last_action = frames[-1].action_input.id.name

        return {
            "player_position": player_pos,
            "energy": parsed["energy"],
            "energy_pill_visible": parsed["energy_pill_visible"],
            "energy_pill_distance": self._calculate_distance(
                player_pos,
                parsed["energy_pill_positions"][0]
                if parsed["energy_pill_positions"]
                else None,
            ),
            "key_matches_door": parsed["key_matches_door"],
            "door_position": door_pos,
            "door_distance": distance_to_door,
            "rotator_position": parsed["rotator_position"],
            "rotator_distance": self._calculate_distance(
                player_pos, parsed["rotator_position"]
            ),
            "nearby_walls": nearby_walls,
            "wall_distance": min(
                [
                    abs(w[0] - player_pos[0]) + abs(w[1] - player_pos[1])
                    for w in nearby_walls
                ],
                default=10,
            ),
            "last_action": last_action,
            "grid_bounds": parsed["grid_bounds"],
        }

    def _calculate_distance(
        self, pos1: Tuple[int, int], pos2: Optional[Tuple[int, int]]
    ) -> float:
        """Calculate Euclidean distance between two positions."""
        if pos2 is None:
            return 100.0  # Unknown

        return np.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)
