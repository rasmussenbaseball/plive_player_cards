import os
import csv
import requests
from PIL import Image, ImageDraw, ImageFont
from bs4 import BeautifulSoup

# ---- CONFIG ----

FONT_PATH_BOLD = "cooper-hewitt/CooperHewitt-Bold.otf"
FONT_PATH_MEDIUM = "cooper-hewitt/CooperHewitt-Medium.otf"
CSV_FILE = "plive_hitters.csv"
TOP100_CSV_FILE = "plive_top_100.csv"
LOGO_FILE = "plive_logo.png"  # Your logo file

CARD_WIDTH, CARD_HEIGHT = 900, 920
BG_COLOR = (11, 27, 45)

MARGIN = 56  # Left/right margin for all top and bottom boxes (aligns with bottom boxes)
SIDE_MARGIN = MARGIN
TOP_MARGIN = 32
ROW_GAP = 12
BOX_GAP = 32

NAME_FONT_SIZE = 56
INFO_BOX_HEIGHT = 56
INFO_BOX_FONT_SIZE = 36
INFO_BOX_GAP = 16

RANK_BOX_HEIGHT = 56
RANK_BOX_FONT_SIZE = 30
RANK_LABEL_FONT_SIZE = 15

PLIVE_BOX_WIDTH = 180
PLIVE_BOX_BORDER = 7

PHOTO_BOX_BORDER = 3

BOTTOM_BOX_WIDTH = 392
BOTTOM_BOX_HEIGHT = 490
BOTTOM_BOX_BORDER = 7

TEAM_CIRCLE_RADIUS = 34

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
SCOUT_GRADE_RULES = { "gray": (45, 55) }


def fetch_player_info_online(player_name):
    """
    Attempts to find Position, B/T, Team, and Level for a player using Baseball Reference.
    Returns a dictionary with any found keys.
    """
    from urllib.parse import quote

    query = f"{player_name} site:baseball-reference.com/register"
    search_url = f"https://www.bing.com/search?q={quote(query)}"
    try:
        r = requests.get(search_url, timeout=10)
    except Exception:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")

    bbref_url = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        if "baseball-reference.com/register/player" in href:
            bbref_url = href
            break
    if not bbref_url:
        return {}  # Not found

    try:
        r = requests.get(bbref_url, timeout=10)
    except Exception:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    info = {}

    bt_div = soup.find('div', attrs={'itemtype': 'https://schema.org/Person'})
    if bt_div:
        text = bt_div.get_text()
        import re
        bt_match = re.search(r"Bats: (.+?) • Throws: (.+)", text)
        if bt_match:
            info['B/T'] = f"{bt_match.group(1)[0]}/{bt_match.group(2)[0]}"
        pos_match = re.search(r"Position: ([A-Za-z, /-]+)", text)
        if pos_match:
            info['Position'] = pos_match.group(1).split(',')[0].strip()
    table = soup.find('table', id='standard_batting')
    if table:
        rows = table.find_all('tr')
        for row in reversed(rows):
            team_cell = row.find('td', {'data-stat': 'team_ID'})
            level_cell = row.find('td', {'data-stat': 'lg_ID'})
            if team_cell and team_cell.text.strip():
                info['Team'] = team_cell.text.strip()
                if level_cell and level_cell.text.strip():
                    info['Level'] = level_cell.text.strip()
                break
    return info


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

def draw_centered(draw, text, box, font, fill):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = box[0] + (box[2] - box[0] - w) // 2
    y = box[1] + (box[3] - box[1] - h) // 2
    draw.text((x, y), str(text), font=font, fill=fill)

def draw_box(draw, box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=7):
    draw.rectangle(box, fill=fill, outline=outline, width=width)

def load_top_100(csv_file):
    """Returns a dict {player_name_upper: rank (str/int)}"""
    top100 = {}
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "Name" in row:
                pname = row["Name"].strip().upper()
            elif "Player" in row:
                pname = row["Player"].strip().upper()
            else:
                continue
            rank = row.get("Rank", "").strip()
            if rank.isdigit():
                top100[pname] = str(int(rank))
            elif rank:
                top100[pname] = rank
    return top100

def fill_missing_player_info(player):
    """
    For a dict player, check for missing Position, B/T, Team, Level.
    If missing, attempts to fetch from Baseball Reference.
    Updates player in place.
    """
    missing_keys = [k for k in ['Position', 'B/T', 'Team', 'Level'] if not player.get(k) or player[k].strip() == ""]
    if missing_keys:
        web_info = fetch_player_info_online(player['Name'])
        for k in missing_keys:
            if k in web_info:
                player[k] = web_info[k]

def draw_player_card(player, top100_map, outfile="player_card.png"):
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- FONTS ---
    name_font = load_font(NAME_FONT_SIZE, bold=True)
    info_font = load_font(INFO_BOX_FONT_SIZE, bold=True)
    rank_font = load_font(RANK_BOX_FONT_SIZE, bold=True)
    rank_label_font = load_font(RANK_LABEL_FONT_SIZE)
    plive_title_font = load_font(24, bold=True)
    plive_score_font = load_font(66, bold=True)
    plive_small_font = load_font(20)
    bottom_section_title_font_big = load_font(32, bold=True)
    stat_label_font = load_font(28, bold=True)
    stat_value_font = load_font(50, bold=True)
    grade_font = load_font(48, bold=True)
    grade_label_font = load_font(29, bold=True)
    footer_font = load_font(FOOTER_TEXT_SIZE, italic=True)

    # --- TEAM LOGO CIRCLE ---
    circle_y = TOP_MARGIN + NAME_FONT_SIZE // 2 + 2
    circle_x = SIDE_MARGIN + TEAM_CIRCLE_RADIUS
    draw.ellipse(
        (
            circle_x - TEAM_CIRCLE_RADIUS,
            circle_y - TEAM_CIRCLE_RADIUS,
            circle_x + TEAM_CIRCLE_RADIUS,
            circle_y + TEAM_CIRCLE_RADIUS,
        ),
        fill=COLOR_WHITE,
        outline=COLOR_BLACK,
        width=4
    )

    # --- NAME (centered at top) ---
    name_text = player["Name"].upper()
    name_font_bbox = name_font.getbbox(name_text)
    name_text_w = name_font_bbox[2] - name_font_bbox[0]
    name_x = (CARD_WIDTH - name_text_w) // 2
    name_y = TOP_MARGIN
    draw.text((name_x, name_y), name_text, font=name_font, fill=COLOR_WHITE)

    # --- INFO GRID (2x3), left-aligned with bottom box edge ---
    grid_left = SIDE_MARGIN
    grid_top = name_y + NAME_FONT_SIZE + ROW_GAP + 6
    grid_cell_w = (BOTTOM_BOX_WIDTH - INFO_BOX_GAP) // 2
    grid_cell_h = INFO_BOX_HEIGHT
    grid_v_gap = 10

    # --- Top 100 logic ---
    player_name_upper = player["Name"].strip().upper()
    top100_rank = top100_map.get(player_name_upper, "NR")

    # --- INFO GRID (2x3), use actual Team and Position fields from CSV or auto-filled ---
    info_grid = [
        (player.get("Position", "POS"), player.get("B/T", "B/T")),
        (player.get("Level", "LEVEL"), player.get("Team", "TEAM")),
        (top100_rank, player.get("PLIVE+ Rank", "PLIVE+ RANK"))
    ]
    for row in range(3):
        for col in range(2):
            x0 = grid_left + col * (grid_cell_w + INFO_BOX_GAP)
            y0 = grid_top + row * (grid_cell_h + grid_v_gap)
            box = (x0, y0, x0 + grid_cell_w, y0 + grid_cell_h)
            draw_box(draw, box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=4)
            draw_centered(draw, info_grid[row][col], box, info_font, COLOR_BLACK)

    # --- Calculate total info grid height for PLIVE+/photo alignment ---
    info_grid_right = grid_left + 2 * grid_cell_w + INFO_BOX_GAP
    info_grid_bottom = grid_top + 3 * grid_cell_h + 2 * grid_v_gap
    info_section_top = grid_top
    info_section_bottom = info_grid_bottom

    # --- PLIVE+ BOX (aligned right above Peak Projections box) ---
    plive_x = SIDE_MARGIN + BOTTOM_BOX_WIDTH + BOX_GAP
    plive_y = info_section_top
    plive_box = (plive_x, plive_y, plive_x + PLIVE_BOX_WIDTH, info_section_bottom)
    draw_box(draw, plive_box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=PLIVE_BOX_BORDER)

    # Title, moved down for spacing
    box_width = plive_box[2] - plive_box[0]
    box_height = plive_box[3] - plive_box[1]
    title_h = 36
    title_y_offset = 14
    draw_centered(
        draw,
        "PLIVE+",
        (plive_x, plive_y + title_y_offset, plive_x + box_width, plive_y + title_y_offset + title_h),
        plive_title_font,
        COLOR_BLACK
    )
    # Score
    draw_centered(
        draw,
        str(int(float(player["PLIVEplus"])) if player["PLIVEplus"] else player["PLIVEplus"]),
        (plive_x, plive_y + title_y_offset + title_h, plive_x + box_width, plive_y + title_y_offset + title_h + 70),
        plive_score_font,
        COLOR_BLACK
    )
    # Week/month neatly inside box with more padding
    metric_y = plive_y + title_y_offset + title_h + 70 + 12
    metric_h = 30
    draw.text((plive_x + 16, metric_y), "WEEK", font=plive_small_font, fill=COLOR_BLACK)
    draw.text((plive_x + 100, metric_y), "-0.9", font=plive_small_font, fill=COLOR_BLACK)
    draw.text((plive_x + 16, metric_y + metric_h), "MONTH", font=plive_small_font, fill=COLOR_BLACK)
    draw.text((plive_x + 100, metric_y + metric_h), "-4.6", font=plive_small_font, fill=COLOR_BLACK)

    # --- HEADSHOT (aligned with PLIVE+ box, now stretches to right edge of scout grades box) ---
    grades_box_x = SIDE_MARGIN + BOTTOM_BOX_WIDTH + BOX_GAP
    grades_box_right = grades_box_x + BOTTOM_BOX_WIDTH
    photo_x = plive_box[2] + INFO_BOX_GAP
    photo_y = info_section_top
    photo_box = (photo_x, photo_y, grades_box_right, info_section_bottom)
    draw_box(draw, photo_box, fill=COLOR_GRAY, outline=COLOR_BLACK, width=PHOTO_BOX_BORDER)

    # --- BOTTOM: Main White Boxes (Peak Projections & Scout Grades), aligned with top boxes ---
    bottom_y = info_section_bottom + BOX_GAP
    proj_box_x = SIDE_MARGIN
    grades_box_x = proj_box_x + BOTTOM_BOX_WIDTH + BOX_GAP

    # --- PLIVE+ PEAK PROJECTIONS BOX ---
    proj_box = (proj_box_x, bottom_y, proj_box_x + BOTTOM_BOX_WIDTH, bottom_y + BOTTOM_BOX_HEIGHT)
    draw_box(draw, proj_box, fill=COLOR_WHITE, outline=COLOR_BLACK, width=BOTTOM_BOX_BORDER)

    # Section title (two lines, bold and large, moved down for padding)
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

    grade_labels = [
        ("OFP", 45), ("Risk", "HIGH"),
        ("Hit", 55), ("Power", 45),
        ("Field", 50), ("Throw", 50),
        ("Run", 60)
    ]
    grade_start_y = bottom_y + section_title_pad + 2*title_h - 6 + 6
    grade_row_height = (BOTTOM_BOX_HEIGHT - (section_title_pad + 2*title_h)) // len(grade_labels)
    grade_label_x = grades_box_x + 36
    grade_val_x = grades_box_x + BOTTOM_BOX_WIDTH - 172
    for i, (label, value) in enumerate(grade_labels):
        y0 = grade_start_y + i * grade_row_height
        draw.text((grade_label_x, y0), f"{label.upper()} -", font=grade_label_font, fill=COLOR_BLACK)
        color = color_for_grade(value) if isinstance(value, (int, float)) else COLOR_BLUE if value == "HIGH" else COLOR_GRAY
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
        logo_size = 92  # larger logo
        logo_img = logo_img.resize((logo_size, logo_size), Image.LANCZOS)
        logo_x = CARD_WIDTH - SIDE_MARGIN - logo_size + 4
        logo_y = CARD_HEIGHT - logo_size - 8
        img.paste(logo_img, (logo_x, logo_y), logo_img)
    except Exception as e:
        print(f"Logo not found or error loading logo: {e}")

    img.save(outfile)
    print(f"Saved card for {player['Name']} as {outfile}")

def load_players(csv_file):
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        players = [row for row in reader]
    return players

def main():
    players = load_players(CSV_FILE)
    top100_map = load_top_100(TOP100_CSV_FILE)
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

    # -- Fill missing info automatically --
    fill_missing_player_info(player)

    output_filename = f"{player['Name'].replace(' ', '_')}_card.png"
    draw_player_card(player, top100_map, outfile=output_filename)

if __name__ == "__main__":
    main()