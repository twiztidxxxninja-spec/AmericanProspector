# Screen
SCREEN_WIDTH  = 120
SCREEN_HEIGHT = 50

# Map panel (local map, left side)
MAP_WIDTH  = 80
MAP_HEIGHT = 45

# Sidebar (right side)
SIDE_X     = 82
SIDE_WIDTH = 36

# Message log (bottom of map panel)
MSG_Y      = 40
MSG_HEIGHT = 5

# World map dimensions (~400x200 tiles, each ~5 miles)
WORLD_WIDTH  = 520
WORLD_HEIGHT = 340

# Area patches per world tile axis (14×14 = 196 patches per world tile)
# Each world tile (~5.1 miles) is subdivided into a grid of area patches.
# Walking off one patch enters the adjacent patch seamlessly.
AREAS_PER_WORLD = 14

# Physical size of each local tile in feet
TILE_FEET = 5

# Local map / patch dimensions (384x384 tiles, each ~5 feet)
# One patch covers 384 × 5ft = 1,920ft ≈ 0.36 miles.
# 14 patches per world tile axis → 5,376 tiles → ~5.09 miles per world tile.
LOCAL_WIDTH  = 384
LOCAL_HEIGHT = 384
PATCH_SIZE   = LOCAL_WIDTH  # alias for clarity

# Screen viewport for local map rendering (player stays centered)
VIEWPORT_W = MAP_WIDTH       # 80 — columns
VIEWPORT_H = MSG_Y - 1       # 39 — rows (row 1 below hotbar, row 39 above messages)

# Time constants — movement in SECONDS, actions in MINUTES
# Each local tile ≈ 5 feet. One patch = 384 tiles. One world tile = 14 patches.
# Crossing one world tile on foot: 14 × 384 × 3 sec = 16,128 sec ≈ 269 min ≈ 4.5 hr.
# Walk speed: 5ft / 3sec ≈ 1.1 mph (rough terrain navigation pace).
WALK_TIME    = 3     # seconds per tile walking
JOG_TIME     = 2     # seconds per tile jogging (~67% of walk)
RUN_TIME     = 1     # seconds per tile running (~33% of walk)
CRAWL_TIME   = 9     # seconds per tile crawling (~3x walk)
WORLD_TRAVEL = 300   # 1 world tile on foot (~5 miles, ~5 hours rough terrain avg)

# Survival stat drain rates (units per hour of normal activity)
HUNGER_RATE  = 2.0
THIRST_RATE  = 3.0
WARMTH_RATE  = 1.0   # modified heavily by temperature/shelter
FATIGUE_RATE = 2.0   # modified by activity intensity

# Stat thresholds
STAT_WARNING  = 30   # advisory warning
STAT_CRITICAL = 15   # task pause / danger
STAT_ZERO     = 0    # damage begins

# Z-levels (vertical terrain)
Z_MIN = -20              # deepest mine shaft
Z_MAX = 20               # tallest peak relative to reference
Z_LEVELS = Z_MAX - Z_MIN + 1   # 41
Z_SURFACE_DEFAULT = 0    # reference "sea level" elevation
Z_FEET_PER_LEVEL = 3     # display conversion
CLIMB_TIME_MULT = 1.5    # climbing ramps/stairs takes 1.5x walk time
VIEW_Z_BELOW = 5         # how many z-levels below to show through open air

# Title
TITLE = "American Prospector"
