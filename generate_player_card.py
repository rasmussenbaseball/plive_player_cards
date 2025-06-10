import os
import csv
import glob
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

from pybaseball.playerid_lookup import playerid_lookup  # Fallback lookup

# ---- CONFIG ----

FONT_PATH_BOLD = "cooper-hewitt/CooperHewitt-Bold.otf"
FONT_PATH_MEDIUM = "cooper-hewitt/CooperHewitt-Medium.otf"
CSV_FILE = "plive_hitters.csv"
TOP100_CSV_FILE = "plive_top_100.csv"
OS_CSV_FILE = "OS_full_org_list.csv"
LOGO_FILE = "plive_logo.png"
MLB_LOGOS_CSV = "mlbLogos.csv"
MLBAM_ID_CACHE = "mlbam_id_cache.csv"  # Local cache for speed

CARD_WIDTH, CARD_HEIGHT = 900, 920
BG_COLOR = (11, 27, 45)

MARGIN = 56
SIDE_MARGIN = MARGIN
TOP_MARGIN = 32
ROW_GAP = 12
BOX_GAP = 32

NAME_FONT_SIZE = 56
INFO_BOX_HEIGHT = 56
INFO_BOX_FONT_SIZE = 36
INFO_BOX_GAP = 16

RANK_LABEL_FONT_SIZE = 28  # Larger for top 100/plive+ rank
RANK_NUMBER_FONT_SIZE = 54

PHOTO_BOX_BORDER = 3

BOTTOM_BOX_WIDTH = 392
BOTTOM_BOX_HEIGHT = 490
BOTTOM_BOX_BORDER = 7

FOOTER_TEXT_SIZE = 48
FOOTER_ITALIC_PATH = "cooper-hewitt/CooperHewitt-BoldItalic.otf"

COLOR_GRAY = (80, 80, 80)
COLOR_BLUE = (70, 160, 245)
COLOR_RED = (228, 55, 50)
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)

STAT_COLOR_RULES = {
    "BB%": {"gray": (0.066, 0.10), "reverse": False},
    "K%":  {"gray": (0.184, 0.241), "reverse": True},
    "AVG": {"gray": (0.236, 0.273), "reverse": False},
    "OBP": {"gray": (0.311, 0.353), "reverse": False},
    "SLG": {"gray": (0.382, 0.455), "reverse": False},
    "wRC+": {"gray": (105, 118), "reverse": False},
    "HR":  {"gray": (15, 23), "reverse": False},
    "SB":  {"gray": (9, 15), "reverse": False}
}
SCOUT_GRADE_RULES = {"gray": (45, 55)}
SCOUT_GRADE_LABELS = ["OFP", "Hit", "Power", "Field", "Arm", "Run"]

#################### MLBAM ID UTILITIES ########################

def load_chadwick_ids(folder="people"):
    id_map = {}
    for filename in glob.glob(os.path.join(folder, "people-*.csv")):
        with open(filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                first = row['name_first'].strip().lower()
                last = row['name_last'].strip().lower()
                full_name = f"{first} {last}"
                mlbam_id = row['key_mlbam'].strip()
                if mlbam_id:
                    id_map[full_name] = mlbam_id
    return id_map

def load_mlbam_cache(cache_file):
    cache = {}
    if os.path.exists(cache_file):
        with open(cache_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    cache[row[0].upper()] = row[1]
    return cache

def save_mlbam_cache(cache, cache_file):
    with open(cache_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for key, val in cache.items():
            writer.writerow([key, val])

def get_mlbam_id(player_name, team=None, cache=None, chadwick_ids=None):
    # 1. Try Chadwick Bureau first
    if chadwick_ids is not None:
        parts = player_name.strip().lower().split()
        if len(parts) >= 2:
            full_name = f"{parts[0]} {parts[-1]}"
            mlbam_id = chadwick_ids.get(full_name)
            if mlbam_id:
                if cache is not None:
                    cache[player_name.upper()] = mlbam_id
                return mlbam_id
    # 2. Fallback to cache
    key = player_name.upper()
    if cache and key in cache:
        return cache[key]
    # 3. Fallback to pybaseball
    parts = player_name.strip().split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    try:
        lookup = playerid_lookup(last, first)
        if lookup.empty:
            return None
        if team:
            lookup_team = lookup[lookup['team'].str.upper() == team.upper()]
            if not lookup_team.empty:
                mlbam_id = int(lookup_team.iloc[0]['key_mlbam'])
            else:
                mlbam_id = int(lookup.iloc[0]['key_mlbam'])
        else:
            mlbam_id = int(lookup.iloc[0]['key_mlbam'])
        if cache is not None:
            cache[key] = str(mlbam_id)
        return str(mlbam_id)
    except Exception as e:
        print(f"MLBAM lookup failed for {player_name}: {e}")
        return None

def get_headshot_url(mlbam_id):
    return f"https://img.mlbstatic.com/mlb-photos/image/upload/v1/people/{mlbam_id}/headshot/67/current.png"

def fetch_headshot_image(url):
    try:
        resp = requests.get(url, timeout=8)
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        return img
    except Exception as e:
        print(f"Error fetching headshot: {url} ({e})")
        return None

def resize_and_center(img, target_box):
    """
    Resize img to fit inside target_box (x0, y0, x1, y1) without distortion.
    Returns resized_img, offset_x, offset_y.
    """
    box_w = target_box[2] - target_box[0]
    box_h = target_box[3] - target_box[1]
    img_w, img_h = img.size
    scale = min(box_w / img_w, box_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    resized_img = img.resize((new_w, new_h), Image.LANCZOS)
    offset_x = target_box[0] + (box_w - new_w) // 2
    offset_y = target_box[1] + (box_h - new_h) // 2
    return resized_img, offset_x, offset_y

###############################################################

def load_font(size, bold=False, medium=False, italic=False):
    if italic:
        return ImageFont.truetype(FOOTER_ITALIC_PATH, size)
    if bold:
        return ImageFont.truetype(FONT_PATH_BOLD, size)
    elif medium:
        return ImageFont.truetype(FONT_PATH_MEDIUM, size)
    else:
        return ImageFont.truetype(FONT_PATH_BOLD, size)

def color_for_stat(label, value):
    rules = STAT_COLOR_RULES.get(label)
    if rules is None:
        return COLOR_GRAY
    min_g, max_g = rules["gray"]
    reverse = rules["reverse"]
    try:
        v = float(value)
    except Exception:
        return COLOR_GRAY
    if reverse:
        if v < min_g:
            return COLOR_RED
        elif v > max_g:
            return COLOR_BLUE
        else:
            return COLOR_GRAY
    else:
        if v < min_g:
            return COLOR_BLUE
        elif v > max_g:
            return COLOR_RED
        else:
            return COLOR_GRAY

def color_for_grade(value):
    try:
        v = float(value)
    except Exception:
        return COLOR_GRAY
    min_g, max_g = SCOUT_GRADE_RULES["gray"]
    if v < min_g:
        return COLOR_BLUE
    elif v > max_g:
        return COLOR_RED
    else:
        return COLOR_GRAY

def draw_box(draw, box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=7):
    draw.rectangle(box, fill=fill, outline=outline, width=width)

def draw_centered(draw, text, box, font, fill):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = box[0] + (box[2] - box[0] - w) // 2
    y = box[1] + (box[3] - box[1] - h) // 2
    draw.text((x, y), str(text), font=font, fill=fill)

def draw_rank_box_vertical(draw, box, title, number, title_font, number_font, fill=COLOR_WHITE, outline=COLOR_BLACK, width=4):
    draw_box(draw, box, fill=fill, outline=outline, width=width)
    x0, y0, x1, y1 = box
    box_w = x1 - x0
    box_h = y1 - y0

    # Draw title (centered at top)
    title_h = title_font.getbbox(title)[3] - title_font.getbbox(title)[1]
    title_y = y0 + 10
    title_x = x0 + (box_w - (title_font.getbbox(title)[2] - title_font.getbbox(title)[0])) // 2
    draw.text((title_x, title_y), title, font=title_font, fill=COLOR_BLACK)

    # Draw number (centered, below title)
    number_str = str(number)
    num_h = number_font.getbbox(number_str)[3] - number_font.getbbox(number_str)[1]
    num_w = number_font.getbbox(number_str)[2] - number_font.getbbox(number_str)[0]
    num_x = x0 + (box_w - num_w) // 2
    num_y = title_y + title_h + 10 + (box_h - title_h - 20 - num_h) // 2
    draw.text((num_x, num_y), number_str, font=number_font, fill=COLOR_BLACK)

def load_top_100(csv_file):
    top100 = {}
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pname = row["Prospects"].strip().upper()
            rank = row.get("Rank", "").strip()
            if rank.isdigit():
                top100[pname] = str(int(rank))
            elif rank:
                top100[pname] = rank
    return top100

def fill_missing_player_info(player):
    pass

def get_pliveplus_ranks(csv_file):
    plive_ranks = {}
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            pname = row["Name"].strip().upper()
            plive_ranks[pname] = str(idx + 1)
    return plive_ranks

def get_os_positions_and_grades(os_csv_file):
    os_positions = {}
    os_grades = {}
    with open(os_csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name_col = None
            for key in row.keys():
                if key.strip().lower() == "name":
                    name_col = key
                    break
            if not name_col:
                continue
            pname = row[name_col].strip().upper()
            pos = row.get("Position", "").strip()
            os_positions[pname] = pos
            grades = {}
            for label in SCOUT_GRADE_LABELS:
                grades[label] = row.get(label, "").strip()
            os_grades[pname] = grades
    return os_positions, os_grades

def get_mlb_logo_urls(mlb_logos_csv):
    team_logo_map = {}
    with open(mlb_logos_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            team_abbr = row["TeamShort"].strip().upper()
            url = row["url"].strip()
            team_logo_map[team_abbr] = url
    return team_logo_map

def fetch_logo_image(url, size):
    try:
        resp = requests.get(url, timeout=8)
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        return img
    except Exception as e:
        print(f"Error fetching logo: {url} ({e})")
        return None

def draw_player_card(
    player, top100_map, pliveplus_ranks, os_positions, os_grades,
    mlb_logo_urls, mlbam_cache, chadwick_ids, outfile=None
):
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- FONTS ---
    name_font = load_font(NAME_FONT_SIZE, bold=True)
    info_font = load_font(INFO_BOX_FONT_SIZE, bold=True)
    bottom_section_title_font_big = load_font(32, bold=True)
    stat_label_font = load_font(28, bold=True)
    stat_value_font = load_font(50, bold=True)
    grade_font = load_font(48, bold=True)
    grade_label_font = load_font(29, bold=True)
    footer_font = load_font(FOOTER_TEXT_SIZE, italic=True)
    rank_label_font = load_font(RANK_LABEL_FONT_SIZE, bold=True)
    rank_number_font = load_font(RANK_NUMBER_FONT_SIZE, bold=True)

    name_text = player["Name"].upper()
    name_font_bbox = name_font.getbbox(name_text)
    name_text_w = name_font_bbox[2] - name_font_bbox[0]
    name_x = (CARD_WIDTH - name_text_w) // 2
    name_y = TOP_MARGIN
    draw.text((name_x, name_y), name_text, font=name_font, fill=COLOR_WHITE)

    # --- INFO SECTION (NEW LAYOUT) ---
    grid_left = SIDE_MARGIN
    grid_top = name_y + NAME_FONT_SIZE + ROW_GAP + 6
    grid_cell_w = (BOTTOM_BOX_WIDTH - INFO_BOX_GAP) // 2
    grid_cell_h = INFO_BOX_HEIGHT
    grid_v_gap = 10

    player_name_upper = player["Name"].strip().upper()
    top100_rank = top100_map.get(player_name_upper, "NR")
    pliveplus_rank = pliveplus_ranks.get(player_name_upper, "NR")
    player_pos = os_positions.get(player_name_upper, "")

    # Info box positions for new layout
    # Top row: OF (left), Level (right)
    info_top_y = grid_top
    info_box_left = (grid_left, info_top_y, grid_left + grid_cell_w, info_top_y + grid_cell_h)
    info_box_right = (grid_left + grid_cell_w + INFO_BOX_GAP, info_top_y, grid_left + 2*grid_cell_w + INFO_BOX_GAP, info_top_y + grid_cell_h)
    draw_box(draw, info_box_left, fill=COLOR_WHITE, outline=COLOR_BLACK, width=4)
    draw_centered(draw, player_pos, info_box_left, info_font, COLOR_BLACK)
    draw_box(draw, info_box_right, fill=COLOR_WHITE, outline=COLOR_BLACK, width=4)
    draw_centered(draw, player.get("Level", "LEVEL"), info_box_right, info_font, COLOR_BLACK)

    # Second row: Double-height Top 100 and PLIVE+ Rank
    double_box_h = 2 * grid_cell_h + grid_v_gap
    double_box_y = info_top_y + grid_cell_h + grid_v_gap
    rank_box_left = (grid_left, double_box_y, grid_left + grid_cell_w, double_box_y + double_box_h)
    rank_box_right = (grid_left + grid_cell_w + INFO_BOX_GAP, double_box_y, grid_left + 2*grid_cell_w + INFO_BOX_GAP, double_box_y + double_box_h)
    draw_rank_box_vertical(
        draw, rank_box_left, "TOP 100", top100_rank,
        rank_label_font, rank_number_font, fill=COLOR_WHITE, outline=COLOR_BLACK, width=4
    )
    draw_rank_box_vertical(
        draw, rank_box_right, "PLIVE+ RANK", pliveplus_rank,
        rank_label_font, rank_number_font, fill=COLOR_WHITE, outline=COLOR_BLACK, width=4
    )

    # Calculate info section bottom for headshot/logo alignment
    info_section_bottom = double_box_y + double_box_h

    # --- LOGO AND HEADSHOT (NEW LAYOUT) ---
    # Place headshot to the right of the info section, logo centered in area where PLIVE+ box was previously.
    # Define a large box for them to share, with headshot on right, logo on left (centered)
    logo_headshot_box_left = grid_left + 2*grid_cell_w + 2*INFO_BOX_GAP + BOX_GAP
    logo_headshot_box_right = CARD_WIDTH - SIDE_MARGIN
    logo_headshot_box_top = info_top_y
    logo_headshot_box_bottom = info_section_bottom
    logo_headshot_box = (logo_headshot_box_left, logo_headshot_box_top, logo_headshot_box_right, logo_headshot_box_bottom)
    logo_box_w = (logo_headshot_box_right - logo_headshot_box_left) // 2
    logo_box = (
        logo_headshot_box_left,
        logo_headshot_box_top,
        logo_headshot_box_left + logo_box_w,
        logo_headshot_box_bottom
    )
    headshot_box = (
        logo_headshot_box_left + logo_box_w,
        logo_headshot_box_top,
        logo_headshot_box_right,
        logo_headshot_box_bottom
    )

    # Draw logo (centered in left half)
    team_abbr = player.get("Team", "").strip().upper()
    logo_url = mlb_logo_urls.get(team_abbr)
    if logo_url:
        logo_size = int(min(logo_box[2] - logo_box[0], logo_box[3] - logo_box[1]) * 0.82)
        logo_img = fetch_logo_image(logo_url, logo_size)
        if logo_img:
            lx = logo_box[0] + (logo_box[2] - logo_box[0] - logo_size) // 2
            ly = logo_box[1] + (logo_box[3] - logo_box[1] - logo_size) // 2
            img.paste(logo_img, (lx, ly), logo_img)

    # Draw headshot (centered in right half, aspect ratio preserved)
    mlbam_id = get_mlbam_id(player["Name"], team=team_abbr, cache=mlbam_cache, chadwick_ids=chadwick_ids)
    if mlbam_id:
        headshot_url = get_headshot_url(mlbam_id)
        headshot_img = fetch_headshot_image(headshot_url)
        if headshot_img:
            resized_img, px, py = resize_and_center(headshot_img, headshot_box)
            img.paste(resized_img, (px, py), resized_img)
        else:
            draw_box(draw, headshot_box, fill=COLOR_GRAY, outline=COLOR_BLACK, width=PHOTO_BOX_BORDER)
    else:
        draw_box(draw, headshot_box, fill=COLOR_GRAY, outline=COLOR_BLACK, width=PHOTO_BOX_BORDER)

    # --- BOTTOM: Main White Boxes (Peak Projections & Scout Grades), aligned with top boxes ---
    bottom_y = info_section_bottom + BOX_GAP
    proj_box_x = SIDE_MARGIN
    grades_box_x = proj_box_x + BOTTOM_BOX_WIDTH + BOX_GAP

    # --- PLIVE+ PEAK PROJECTIONS BOX ---
    proj_box = (proj_box_x, bottom_y, proj_box_x + BOTTOM_BOX_WIDTH, bottom_y + BOTTOM_BOX_HEIGHT)
    draw_box(draw, proj_box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=BOTTOM_BOX_BORDER)

    title1 = "PLIVE+ PEAK"
    title2 = "PROJECTIONS"
    title_h = 36
    section_title_pad = 18
    draw_centered(
        draw,
        title1,
        (proj_box_x, bottom_y + section_title_pad, proj_box_x + BOTTOM_BOX_WIDTH, bottom_y + section_title_pad + title_h),
        bottom_section_title_font_big,
        COLOR_BLACK
    )
    draw_centered(
        draw,
        title2,
        (proj_box_x, bottom_y + section_title_pad + title_h - 6, proj_box_x + BOTTOM_BOX_WIDTH, bottom_y + section_title_pad + 2*title_h - 6),
        bottom_section_title_font_big,
        COLOR_BLACK
    )

    stat_labels = [
        ("HR", "HR"), ("SB", "SB"),
        ("K%", "K."), ("BB%", "BB."),
        ("OBP", "OBP"), ("AVG", "AVG"),
        ("SLG", "SLG"), ("wRC+", "wRC.")
    ]
    stat_start_y = bottom_y + section_title_pad + 2*title_h - 6 + 6
    stat_row_height = (BOTTOM_BOX_HEIGHT - (section_title_pad + 2*title_h)) // len(stat_labels)
    stat_col_x = proj_box_x + 36
    stat_val_x = proj_box_x + BOTTOM_BOX_WIDTH - 172

    for i, (label, key) in enumerate(stat_labels):
        y0 = stat_start_y + i * stat_row_height
        draw.text((stat_col_x, y0), label, font=stat_label_font, fill=COLOR_BLACK)
        stat_val = player.get(key, "")
        if label in ["BB%", "K%"]:
            try:
                stat_val_fmt = f"{float(stat_val)*100:.1f}%"
            except:
                stat_val_fmt = stat_val
        elif label in ["AVG", "OBP", "SLG"]:
            try:
                stat_val_fmt = f".{str(stat_val).split('.')[-1]}"
            except:
                stat_val_fmt = stat_val
        else:
            stat_val_fmt = stat_val
        color = color_for_stat(label, player.get(key, ""))
        draw.text((stat_val_x, y0), str(stat_val_fmt), font=stat_value_font, fill=color)

    # --- PROSPECTS LIVE SCOUT GRADES BOX ---
    grades_box = (grades_box_x, bottom_y, grades_box_x + BOTTOM_BOX_WIDTH, bottom_y + BOTTOM_BOX_HEIGHT)
    draw_box(draw, grades_box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=BOTTOM_BOX_BORDER)
    sg_title_1 = "PROSPECTS LIVE"
    sg_title_2 = "SCOUT GRADES"
    draw_centered(
        draw,
        sg_title_1,
        (grades_box_x, bottom_y + section_title_pad, grades_box_x + BOTTOM_BOX_WIDTH, bottom_y + section_title_pad + title_h),
        bottom_section_title_font_big,
        COLOR_BLACK
    )
    draw_centered(
        draw,
        sg_title_2,
        (grades_box_x, bottom_y + section_title_pad + title_h - 6, grades_box_x + BOTTOM_BOX_WIDTH, bottom_y + section_title_pad + 2*title_h - 6),
        bottom_section_title_font_big,
        COLOR_BLACK
    )

    player_grades = os_grades.get(player_name_upper, {}) if os_grades.get(player_name_upper) else {}
    grade_labels = SCOUT_GRADE_LABELS
    grade_start_y = bottom_y + section_title_pad + 2*title_h - 6 + 6
    grade_row_height = (BOTTOM_BOX_HEIGHT - (section_title_pad + 2*title_h)) // len(grade_labels)
    grade_label_x = grades_box_x + 36
    grade_val_x = grades_box_x + BOTTOM_BOX_WIDTH - 172
    for i, label in enumerate(grade_labels):
        y0 = grade_start_y + i * grade_row_height
        draw.text((grade_label_x, y0), f"{label.upper()} -", font=grade_label_font, fill=COLOR_BLACK)
        value = player_grades.get(label, "") if player_grades else ""
        color = color_for_grade(value) if value and value.replace('.', '', 1).isdigit() else COLOR_GRAY
        draw.text((grade_val_x, y0), str(value), font=grade_font, fill=color)

    # --- FOOTER: Bold italic "prospects live" centered at the bottom ---
    footer_text = "prospects live"
    footer_font = load_font(FOOTER_TEXT_SIZE, italic=True)
    footer_bbox = footer_font.getbbox(footer_text)
    footer_text_w = footer_bbox[2] - footer_bbox[0]
    footer_x = (CARD_WIDTH - footer_text_w) // 2
    footer_y = CARD_HEIGHT - FOOTER_TEXT_SIZE - 16
    draw.text((footer_x, footer_y), footer_text, font=footer_font, fill=COLOR_WHITE)

    # --- LOGO: bottom right, next to the footer text (larger now) ---
    try:
        logo_img = Image.open(LOGO_FILE).convert("RGBA")
        logo_size = 92
        logo_img = logo_img.resize((logo_size, logo_size), Image.LANCZOS)
        logo_x = CARD_WIDTH - SIDE_MARGIN - logo_size + 4
        logo_y = CARD_HEIGHT - logo_size - 8
        img.paste(logo_img, (logo_x, logo_y), logo_img)
    except Exception as e:
        print(f"Logo not found or error loading logo: {e}")

    if outfile:
        img.save(outfile)
        print(f"Saved card for {player['Name']} as {outfile}")

    return img  # Always return the PIL Image object

def load_players(csv_file):
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        players = [row for row in reader]
    return players

def main():
    chadwick_ids = load_chadwick_ids("people")
    players = load_players(CSV_FILE)
    top100_map = load_top_100(TOP100_CSV_FILE)
    pliveplus_ranks = get_pliveplus_ranks(CSV_FILE)
    os_positions, os_grades = get_os_positions_and_grades(OS_CSV_FILE)
    mlb_logo_urls = get_mlb_logo_urls(MLB_LOGOS_CSV)
    mlbam_cache = load_mlbam_cache(MLBAM_ID_CACHE)
    player_names = [p["Name"] for p in players]
    print("First 20 players:")
    for i, name in enumerate(player_names[:20]):
        print(f"{i+1}. {name}")
    print(f"...({len(player_names)} total)")
    inp = input("\nType a player number (1-20 above) or part of a name to search: ").strip()
    if inp.isdigit():
        idx = int(inp) - 1
        if 0 <= idx < len(players):
            player = players[idx]
        else:
            print("Invalid number")
            return
    else:
        matches = [p for p in players if inp.lower() in p["Name"].lower()]
        if not matches:
            print("No players found with that name.")
            return
        print("\nSearch results:")
        for i, p in enumerate(matches[:10]):
            print(f"{i+1}. {p['Name']}")
        sel = input("Type the number of the player you want: ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(matches[:10]):
            player = matches[int(sel)-1]
        else:
            print("Invalid selection.")
            return
    fill_missing_player_info(player)
    output_filename = f"{player['Name'].replace(' ', '_')}_card.png"
    draw_player_card(player, top100_map, pliveplus_ranks, os_positions, os_grades, mlb_logo_urls, mlbam_cache, chadwick_ids, outfile=output_filename)
    save_mlbam_cache(mlbam_cache, MLBAM_ID_CACHE)

if __name__ == "__main__":
    main()