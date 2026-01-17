import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="EMOP 2026 – Suivi")
st.title("🌍 EMOP 2026 – Geospatial Monitoring Dashboard")

# =========================================================
# USERS AND REGIONS (Login → Password → Accessible Regions)
# =========================================================
USERS = {
    "roland_emop": {"password": "emop2026rd", "role": "User", "regions": ["Kayes","Kita","Nioro","Sikasso","Koutiala"]},
    "fanta_emop": {"password": "emop2026ft", "role": "User", "regions": ["Koulikoro","Bamako"]},
    "boubacar_emop": {"password": "emop2026bk", "role": "User", "regions": ["Dioila","Nara"]},
    "mohamed_emop": {"password": "emop2026mf", "role": "User", "regions": ["Bougouni","Segou","San","Mopti"]},
    "kalilou_emop": {"password": "emop2026kb", "role": "User", "regions": ["Bandiagara","Douentza","Tombouctou"]},
    "modibo_emop": {"password": "emop2026mb", "role": "User", "regions": ["Menaka","Kidal","Taoudeni","Gao"]},
    "admin": {"password": "admin2026", "role": "Admin", "regions": []}  # Admin sees all
}

# =========================================================
# SESSION INIT
# =========================================================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.accessible_regions = []
    st.session_state.points_gdf = None
    st.session_state.query_result = None

# =========================================================
# LOGOUT FUNCTION
# =========================================================
def logout():
    st.session_state.clear()
    st.rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    username = st.sidebar.text_input("Login")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if username in USERS and password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]
            st.session_state.accessible_regions = USERS[username]["regions"]
            st.rerun()
        else:
            st.sidebar.error("❌ Invalid login or password")
    st.stop()

# =========================================================
# LOAD EMOP SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/emop2026.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    gdf.columns = [c.lower().strip() for c in gdf.columns]
    if "lregion" not in gdf.columns: gdf["lregion"] = gdf.get("region", None)
    if "lcercle" not in gdf.columns: gdf["lcercle"] = gdf.get("cercle", None)
    if "lcommune" not in gdf.columns: gdf["lcommune"] = gdf.get("commune", None)
    gdf["region"] = gdf["lregion"]
    gdf["cercle"] = gdf["lcercle"]
    gdf["commune"] = gdf["lcommune"]
    gdf = gdf.loc[:, ~gdf.columns.duplicated()]
    for col in ["region","cercle","commune","num_se"]:
        if col not in gdf.columns: gdf[col] = None
    if "pop_se" not in gdf.columns: gdf["pop_se"] = 0
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    return gdf
try:
    gdf = load_se_data(SE_URL)
except Exception as e:
    st.error(f"❌ Unable to load EMOP GeoJSON: {e}")
    st.stop()

# =========================================================
# SIDEBAR HEADER
# =========================================================
with st.sidebar:
    st.image("Suivi_emop/logo/emop.png", width=200)
    st.markdown(f"**User:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

# =========================================================
# SAFE UNIQUE FUNCTION
# =========================================================
def unique_clean(series):
    if isinstance(series, pd.DataFrame): series = series.iloc[:,0]
    return sorted(series.dropna().astype(str).str.strip().unique())

# =========================================================
# ATTRIBUTE FILTERS
# =========================================================
# =========================================================
# ATTRIBUTE FILTERS (EMOP OFFICIAL FIELDS)
# =========================================================
st.sidebar.markdown("### 🗂️ Attribute Query")
# REGION (label)
all_regions = unique_clean(gdf["lreg_new"])
if st.session_state.user_role == "Admin":
    regions = all_regions
else:
    regions = [r for r in all_regions if r in st.session_state.accessible_regions]
region = st.sidebar.selectbox("Region", regions)
gdf_r = gdf[gdf["lreg_new"] == region]
# CERCLE (label)
cercles = unique_clean(gdf_r["lcer_new"])
cercle = st.sidebar.selectbox("Cercle", cercles)
gdf_c = gdf_r[gdf_r["lcer_new"] == cercle]
# COMMUNE (label)
communes = unique_clean(gdf_c["lcom_new"])
commune = st.sidebar.selectbox("Commune", communes)
gdf_commune = gdf_c[gdf_c["lcom_new"] == commune]
# SE
se_list = ["No filter"] + unique_clean(gdf_commune["num_se"])
se_selected = st.sidebar.selectbox("SE (num_se)", se_list)
gdf_se = (
    gdf_commune
    if se_selected == "No filter"
    else gdf_commune[gdf_commune["num_se"] == se_selected]
)
# =========================================================
# SPATIAL QUERY
# =========================================================
st.sidebar.markdown("### 🧭 Spatial Query")
query_type = st.sidebar.selectbox("Query type", ["Intersects", "Within", "Contains"])
if st.sidebar.button("Run Query"):
    if st.session_state.points_gdf is not None and not gdf_se.empty:
        pts = st.session_state.points_gdf.to_crs(gdf_se.crs)
        st.session_state.query_result = gpd.sjoin(
            pts, gdf_se, predicate=query_type.lower(), how="inner"
        )
        st.sidebar.success(f"{len(st.session_state.query_result)} points found.")
    else:
        st.sidebar.error("No point data available.")

# =========================================================
# CSV LOAD FROM GOOGLE DRIVE
# =========================================================
st.sidebar.markdown("### ☁️ Load CSV from Google Drive")

gdrive_url = st.sidebar.text_input(
    "Paste Google Drive CSV link",
    placeholder="https://drive.google.com/..."
)

if st.sidebar.button("Load from Google Drive"):
    try:
        if "drive.google.com" in gdrive_url:
            file_id = gdrive_url.split("/d/")[1].split("/")[0]
            download_url = f"https://drive.google.com/uc?id={file_id}"

            df = pd.read_csv(download_url)

            if {"Latitude", "Longitude"}.issubset(df.columns):
                st.session_state.points_gdf = gpd.GeoDataFrame(
                    df,
                    geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
                    crs="EPSG:4326"
                )
                st.sidebar.success(f"✅ {len(df)} points loaded from Google Drive")
            else:
                st.sidebar.error("CSV must contain Latitude & Longitude columns")
        else:
            st.sidebar.error("Invalid Google Drive link")

    except Exception as e:
        st.sidebar.error(f"❌ Failed to load CSV: {e}")


# =========================================================
# MAP (OSM + GOOGLE SATELLITE + Collapsible Legend)
# =========================================================
if not gdf_se.empty:
    minx, miny, maxx, maxy = gdf_se.total_bounds
    m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=13, tiles=None)

    # Base maps
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=False,
        control=True
    ).add_to(m)

    # SE polygons
    se_group = folium.FeatureGroup(name="SE")
    folium.GeoJson(
        gdf_se,
        tooltip=folium.GeoJsonTooltip(
            fields=["num_se","pop_se"],
            aliases=["SE Number","Population"]
        ),
        style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.2},
    ).add_to(se_group)
    se_group.add_to(m)

    # CSV points (Concession)
    if st.session_state.points_gdf is not None and not st.session_state.points_gdf.empty:
        st.session_state.points_gdf = st.session_state.points_gdf.to_crs(gdf_se.crs)
        concession_group = folium.FeatureGroup(name="Concession")
        for _, r in st.session_state.points_gdf.iterrows():
            folium.CircleMarker(
                location=[r.geometry.y, r.geometry.x],
                radius=4,
                color="red",
                fill=True,
                fill_opacity=0.7
            ).add_to(concession_group)
        concession_group.add_to(m)

    # Measure & Draw
    MeasureControl().add_to(m)
    Draw(export=True).add_to(m)

    # Collapsible LayerControl
    folium.LayerControl(collapsed=True).add_to(m)

    # Fit bounds
    m.fit_bounds([[miny,minx],[maxy,maxx]])

    # Display map
    st_folium(m, height=550, use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**EMOP 2026 – Suivi Géospatial**   

Auterurs:

**- Abdoul Karim DIAWARA**, Chef de Division Cartographie et SIG

**- Dr.Mahamadou CAMARA**, PhD – Geomatics Engineering   

dtate: **© 2026**
""")










