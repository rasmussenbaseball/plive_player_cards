import streamlit as st
import io
from PIL import Image
from generate_player_card import (
    load_players, draw_player_card, load_top_100,
    get_pliveplus_ranks, get_os_positions_and_grades,
    get_mlb_logo_urls, load_mlbam_cache, load_chadwick_ids
)

# --- Constants for your data files ---
CSV_FILE = "plive_hitters.csv"
TOP100_CSV_FILE = "plive_top_100.csv"
OS_CSV_FILE = "OS_full_org_list.csv"
MLB_LOGOS_CSV = "mlbLogos.csv"
MLBAM_ID_CACHE = "mlbam_id_cache.csv"

# --- Load all resources once ---
players = load_players(CSV_FILE)
top100_map = load_top_100(TOP100_CSV_FILE)
pliveplus_ranks = get_pliveplus_ranks(CSV_FILE)
os_positions, os_grades = get_os_positions_and_grades(OS_CSV_FILE)
mlb_logo_urls = get_mlb_logo_urls(MLB_LOGOS_CSV)
mlbam_cache = load_mlbam_cache(MLBAM_ID_CACHE)
chadwick_ids = load_chadwick_ids("people")

st.set_page_config(page_title="PLIVE Player Card Generator", layout="wide")
st.title("PLIVE Player Card Generator")

player_names = [p["Name"] for p in players]
player_choice = st.selectbox("Select a hitter", player_names)

if st.button("Generate Card"):
    player = next(p for p in players if p["Name"] == player_choice)
    # Generate the card image in memory (no file is created)
    card_img = draw_player_card(
        player, top100_map, pliveplus_ranks, os_positions,
        os_grades, mlb_logo_urls, mlbam_cache, chadwick_ids, outfile=None
    )
    st.image(card_img, caption=f"{player['Name']}'s PLIVE Card")
    
    # Prepare image bytes for download
    buf = io.BytesIO()
    card_img.save(buf, format="PNG")
    byte_im = buf.getvalue()
    st.download_button(
        label="Download Player Card",
        data=byte_im,
        file_name=f"{player['Name'].replace(' ', '_')}_card.png",
        mime="image/png"
    )

st.info("Select a player and click 'Generate Card' to see their PLIVE card.")