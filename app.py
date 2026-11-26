"""Browser interface for AgriSense."""
import calendar
import json
from html import escape

import altair as alt
import folium
import streamlit as st
from streamlit_folium import st_folium

from agrisense import DATA, fetch_climate, limit_matches, load_crops, load_grid, rank, soil_at, summarize_climate

st.set_page_config(page_title="AgriSense", page_icon="🌱", layout="wide")


@st.cache_data
def crop_data():
    return load_crops()


@st.cache_data
def soil_grid():
    return load_grid()


DEMO = {"Aza Khel": (33.80295, 71.62101), "Peshawar": (34.0151, 71.5249), "Lahore": (31.52, 74.36), "Multan": (30.16, 71.52)}
FIELD_CROPS = {
    "Triticum aestivum", "Oryza sativa", "Zea mays ssp. mays", "Gossypium hirsutum",
    "Saccharum officinarum", "Cicer arietinum", "Lens culinaris", "Vigna radiata",
    "Brassica juncea", "Helianthus annuus", "Solanum tuberosum", "Abelmoschus esculentus",
}
BOUNDS = [[23.5, 60.5], [38.0, 78.0]]


@st.cache_data(ttl=86400, max_entries=256, show_spinner=False)
def live_climate(latitude, longitude):
    return fetch_climate(latitude, longitude)


def climate_at(latitude, longitude):
    try:
        return live_climate(latitude, longitude), "NASA POWER (online data)"
    except (OSError, ValueError, KeyError, TypeError):
        for city, coordinates in DEMO.items():
            snapshot = DATA / f"{city.lower()}-power.json"
            if (latitude, longitude) == coordinates and snapshot.exists():
                with snapshot.open(encoding="utf-8") as source:
                    return summarize_climate(json.load(source)), "NASA POWER (saved demo data)"
        raise


def climate_charts(rows):
    months = list(calendar.month_abbr)[1:]
    data = alt.Data(values=rows)
    for field, title, unit, mark in (
        ("Temperature", "How warm is each month?", "Temperature (°C)", "line"),
        ("Rainfall", "How much rain falls each month?", "Rain per month (mm)", "bar"),
    ):
        chart = alt.Chart(data)
        chart = chart.mark_line(point=True) if mark == "line" else chart.mark_bar()
        chart = chart.encode(
            x=alt.X("Month:N", sort=months, title=None),
            y=alt.Y(f"{field}:Q", title=unit),
            color=alt.value("#96c77d"),
            tooltip=["Place:N", "Month:N", alt.Tooltip(f"{field}:Q", title=unit, format=".1f")],
        )
        if mark == "bar":
            chart = chart.encode(xOffset="Place:N")
        st.subheader(title)
        st.altair_chart(chart.properties(height=230), width="stretch")


def crop_chart(results_by_place, plant_type):
    best = {}
    for results in results_by_place.values():
        for row in results:
            name = row["Crop"]
            best[name] = max(best.get(name, 0), row["Score"])
    names = sorted(best, key=lambda name: (-best[name], name))[:8]
    rows = [
        {"Crop": name, "Score": row["Score"], "Place": place,
         "Label": row["Common name"] or name}
        for place, results in results_by_place.items()
        for name in names
        for row in results
        if row["Crop"] == name
    ]
    if not rows:
        return
    labels = {row["Crop"]: row["Label"] for row in rows}
    chart = alt.Chart(alt.Data(values=rows)).mark_bar().encode(
        x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 100]), title="Suitability score (out of 100)"),
        y=alt.Y("Label:N", sort=[labels[name] for name in names], title=None,
                axis=alt.Axis(labelLimit=280)),
        yOffset="Place:N",
        color=alt.value("#96c77d"),
        tooltip=[alt.Tooltip("Label:N", title="Crop"), "Place:N", "Score:Q"],
    )
    st.subheader(f"Your highest-scoring {plant_type.lower()}")
    st.altair_chart(chart.properties(height=max(180, 36 * len(names))), width="stretch")


st.markdown("""
<style>
.stApp { background: #101c16; color: #e7efe6; }
.block-container { max-width: 1100px; padding-top: 2rem; padding-bottom: 3rem; }
h1,h2,h3 { color: #b8dfaf; }
.hero { background: #214d35; color: #fff; padding: 2rem; border-radius: 20px; margin-bottom: 1.6rem; }
.hero h1 { color: #fff; margin: 0; font-size: 2.6rem; }
.hero p { color: #e1eddf; max-width: 40rem; font-size: 1.1rem; margin-bottom: 0; }
.plant-card { border: 1px solid #3b5343; border-radius: 15px; padding: 1rem 1.2rem;
 background: #1c2e23; margin: .65rem 0; }
.plant-card h3 { margin: 0; font-size: 1.2rem; }
.plant-card p { margin: .3rem 0; overflow-wrap: anywhere; }
.plant-score { color: #b5dea4; font-weight: 700; }
div[data-testid="stMetric"] { background: #1c2e23; padding: 1rem; border: 1px solid #3b5343; border-radius: 14px; }
div[data-testid="stMetricLabel"] { white-space: normal; }
.stButton button, .stFormSubmitButton button { min-height: 48px; }
.stButton button[kind="primary"] { background: #236344; border-color: #236344; }
div[role="radiogroup"] { flex-wrap: wrap; gap: .5rem; }
@media (max-width: 640px) {
 .block-container { padding: 1rem .85rem 2rem; }
 .hero { padding: 1.3rem; border-radius: 14px; }
 .hero h1 { font-size: 2rem; }
 .stButton button, .stFormSubmitButton button { width: 100%; }
 div[data-testid="stMetricValue"] { font-size: 1.7rem; }
}
</style>
<div class="hero"><h1>AgriSense</h1>
<p>Find plants that fit your land.</p>
<p>Explore your location's soil and climate, then find crops and trees for your growing plans.</p></div>
""", unsafe_allow_html=True)

if "location" not in st.session_state:
    st.session_state.location = DEMO["Aza Khel"]

st.subheader("Choose your location")
with st.expander("Start with an example city"):
    preset = st.selectbox("City", list(DEMO))
    if st.button("Use this city"):
        st.session_state.location = DEMO[preset]


def pick_map_point():
    event = st.session_state.get("place_map", {}).get("last_clicked")
    if not event:
        return
    latitude, longitude = (round(event[key], 4) for key in ("lat", "lng"))
    south, west = BOUNDS[0]
    north, east = BOUNDS[1]
    if south <= latitude <= north and west <= longitude <= east:
        st.session_state.location = (latitude, longitude)
        st.session_state.pop("map_pick_error", None)
    else:
        st.session_state.map_pick_error = "Choose a point inside the supported map area."



st.caption("Click or tap to place the pin. Drag to move the map, or use + and - to zoom.")
selected_lat, selected_lon = st.session_state.location
with st.expander("Enter exact coordinates"):
    with st.form(f"coordinates-{selected_lat}-{selected_lon}"):
        left, right = st.columns(2)
        latitude = left.number_input("Latitude (north)", BOUNDS[0][0], BOUNDS[1][0],
                                     selected_lat, step=0.0001, format="%.4f")
        longitude = right.number_input("Longitude (east)", BOUNDS[0][1], BOUNDS[1][1],
                                       selected_lon, step=0.0001, format="%.4f")
        submitted = st.form_submit_button("Use these coordinates")
    if submitted:
        st.session_state.location = (round(latitude, 4), round(longitude, 4))
        st.session_state.pop("map_pick_error", None)
        st.rerun()

map_view = folium.Map(location=st.session_state.location, zoom_start=13, tiles="OpenStreetMap",
                      min_zoom=4, max_bounds=True,
                      min_lat=23.5, max_lat=38.0, min_lon=60.5, max_lon=78.0)
map_view.get_root().header.add_child(folium.Element("""
<style>
.leaflet-container.leaflet-grab { cursor: crosshair; }
.leaflet-dragging .leaflet-container.leaflet-grab { cursor: grabbing; }
</style>
"""))
pins = folium.FeatureGroup()
folium.Marker(st.session_state.location, tooltip="Your selected location", interactive=False,
              icon=folium.Icon(color="green")).add_to(pins)

st.write(f"**Selected point:** {selected_lat:.4f} N, {selected_lon:.4f} E")
if error := st.session_state.get("map_pick_error"):
    st.warning(error)
st_folium(map_view, key="place_map", height=350, use_container_width=True,
          feature_group_to_add=pins, returned_objects=["last_clicked"], on_change=pick_map_point)

season_windows = {
    "Rabi (winter)": (11, 6, "November to April"),
    "Kharif (summer and monsoon)": (6, 5, "June to October"),
}
plant_type = st.radio("What would you like to grow?", ["Crops", "Trees"], horizontal=True)
tree_mode = plant_type == "Trees"
if tree_mode:
    scope = st.radio("Tree type", ["Fruit & nut trees", "Other trees"], horizontal=True)
    season, start_month, months = "Year-round", 1, 12
    st.caption("Trees are checked against year-round conditions.")
else:
    scope = st.radio("Crop list", ["Familiar crops", "All non-tree plants"], horizontal=True)
    season = st.radio("Growing season", list(season_windows), horizontal=True)
    start_month, months, window = season_windows[season]
    st.caption(window)
irrigate = st.checkbox("I'll irrigate", help="Use temperature and soil texture to rank crops when you plan to supply water yourself.")

selection = st.session_state.location
request = (selection, plant_type, scope, season, irrigate)
if st.button("Find suitable plants", type="primary", width="stretch"):
    st.session_state.analysis = request

if st.session_state.get("analysis") != request:
    st.info("Choose your location and growing options, then select Find suitable plants.")
else:
    grid, crops = soil_grid(), crop_data()
    crops = [crop for crop in crops if crop.is_tree == tree_mode]
    if tree_mode:
        crops = [crop for crop in crops if crop.fruit_or_nut == (scope == "Fruit & nut trees")]
    elif scope == "Familiar crops":
        crops = [crop for crop in crops if crop.name in FIELD_CROPS]
    st.subheader(f"{plant_type} that match your conditions")
    st.caption(f"Temperature window: {season}. ")
    if tree_mode:
        st.caption("Tree scores use average temperature. Frost, winter chilling, and irrigation needs are outside this check.")
    monthly_rows = []
    results_by_place = {}
    crops_by_name = {crop.name: crop for crop in crops}
    latitude, longitude = selection
    city = next((name for name, point in DEMO.items() if point == (latitude, longitude)), None)
    place = city or "Your selected location"
    st.subheader(place)
    st.caption(f"{latitude:.4f}° N, {longitude:.4f}° E")
    texture, group = soil_at(grid, latitude, longitude)
    try:
        with st.spinner("Getting climate data for your location…"):
            climate, source = climate_at(latitude, longitude)
    except (OSError, ValueError, KeyError, TypeError) as error:
        st.error(f"Climate lookup failed. Run the analysis again to retry. ({error})")
        st.stop()
    temperature, results = rank(crops, climate, group, start_month, months, irrigate=irrigate)
    available, match_limit = limit_matches(results)
    results_by_place[place] = available
    monthly_rows.extend(
        {"Month": calendar.month_abbr[i + 1], "Temperature": temperature,
         "Rainfall": rain, "Place": place}
        for i, (temperature, rain) in enumerate(zip(climate[0], climate[2]))
    )
    if not available:
        checks = "temperature and soil texture" if irrigate else "temperature, rainfall, and soil texture"
        st.info(f"No plants in this list passed the {checks} checks for this location and season.")
        if scope == "Familiar crops":
            st.caption("Try All non-tree plants above to check more crops.")
        st.stop()
    st.caption(f"{len(available):,} matches shown (up to {match_limit}). Higher scores mean a closer match to the checks used.")
    for row in available[:3]:
        name = escape(row["Common name"] or row["Crop"])
        scientific = escape(row["Crop"])
        soil = escape(row["Soil texture"])
        st.markdown(f'<div class="plant-card"><h3>{name}</h3><p><i>{scientific}</i></p>'
                    f'<p class="plant-score">Compatibility score · {row["Score"]:.3g}/100</p>'
                    f'<p>Soil match · {soil}</p></div>', unsafe_allow_html=True)
    st.markdown("**All matching plants**")
    st.dataframe(available, column_order=["Common name", "Score", "Soil texture", "Temperature fit", "Rainfall fit", "Crop"], hide_index=True, width="stretch", column_config={
        "Crop": "Scientific name",
        "Common name": "Plant name",
        "Score": st.column_config.NumberColumn("Compatibility / 100", format="%.3g"),
        "Temperature fit": st.column_config.NumberColumn("Temperature match", format="%d%%"),
        "Rainfall fit": None if irrigate else st.column_config.NumberColumn("Rainfall match", format="%d%%"),
        "Soil texture": "Soil match",
    })
    st.subheader("Your location’s climate and soil")
    rain, heat = st.columns(2)
    rain.metric("Typical yearly rain", f"{climate[1]:,.0f} mm")
    heat.metric("Average yearly temperature" if tree_mode else "Average growing-season temperature", f"{temperature:.1f} °C")
    st.write(f"**Regional soil:** {texture}" + (f" ({group})" if group else ""))
    st.caption(f"{source} · 1991–2020")

    crop = st.selectbox("Tree details" if tree_mode else "Crop details", available,
                        format_func=lambda row: (f"{row['Common name']} ({row['Crop']})"
                            if row["Common name"] else row["Crop"])
                            + f" | {row['Score']:.3g}/100", key="plant_details")
    matching = f"Temperature match: {crop['Temperature fit']}%."
    if not irrigate:
        matching += f" Rainfall match: {crop['Rainfall fit']}%."
    st.write(f"**{crop['Crop']}** scored **{crop['Score']:.3g}/100**. "
             f"{matching} Soil match: {crop['Soil texture'].lower()}.")

    requirements = crops_by_name[crop["Crop"]]
    _, low_temp, high_temp, _ = requirements.temperature
    _, low_rain, high_rain, _ = requirements.rainfall
    st.markdown("**Growing conditions to aim for**")
    st.write(f"- **Preferred temperature:** {low_temp:g} to {high_temp:g} °C")
    st.write(f"- **Typical yearly rainfall:** {low_rain:g} to {high_rain:g} mm")
    if requirements.optimal_soil:
        textures = ", ".join(sorted(requirements.optimal_soil))
        st.write(f"- **Preferred soil texture:** {textures.replace('wide', 'broad range of textures')}")
    for condition, preference in requirements.soil_preferences.items():
        st.write(f"- **{condition}:** {preference}")
    if not requirements.optimal_soil and not requirements.soil_preferences:
        st.caption("ECOCROP has no preferred soil conditions for this crop.")
    st.caption(
        "Rainfall is a climate benchmark. For watering decisions, check moisture around "
        "the roots and use the drainage preference above. These datasets do not give "
        "a field moisture target or an irrigation amount."
    )


    if irrigate:
        st.caption("Irrigated scoring leaves out rainfall and assumes you can supply enough water.")
    else:
        st.caption("Rain-fed scoring includes yearly rainfall.")

    if results_by_place:
        crop_chart(results_by_place, plant_type)
        climate_charts(monthly_rows)

with st.expander("How does the score work?"):
    st.markdown(
        "Rain-fed mode multiplies temperature fit by annual rainfall fit. Each reaches 100% "
        "within the ECOCROP optimal range and falls toward zero at its absolute limits. "
        "With I'll irrigate selected, only temperature contributes to the numeric score. A known soil class outside the stated tolerance sets the score to zero in either mode. "
        "Texture breaks ties. Missing texture stays visible as an unknown."
    )
    st.caption(
        "The selected season sets the temperature window for every crop. The rain-fed check uses a full year of rainfall. The screen uses regional GLDAS texture "
        "and historical climate. Irrigation, local soil pH, salinity, drainage, yield, and "
        "crop-specific planting calendars are outside this calculation."
    )



