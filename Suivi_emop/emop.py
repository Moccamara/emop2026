import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd
import altair as alt

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="EMOP 2026 – Suivi")
st.title("🌍 EMOP 2026 – Geospatial Monitoring Dashboard")

# =========================================================
# USERS AND ROLES
# =========================================================
USERS = {
    "admin": {"password": "admin2025", "role": "Admin"},
    "customer": {"password": "cust2025", "role": "Customer"},
}

# =========================================================
# SESSION INIT
# =========================================================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.session_state.query_result = None

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.clear()
    st.rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    username = st.sidebar.selectbox("User", list(USERS.keys()))
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):
        if password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]
            st.rerun()
        else:
            st.sidebar.error("❌ Incorrect password")
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

    gdf = gdf.rename(columns={
        "lregion": "region",
        "lcerde": "cercle",
        "lcommune": "commune",
        "num_se": "se_id"
    })

    # 🔴 critical fix
    gdf = gdf.loc[:, ~gdf.columns.duplicated()]

    for col in ["region", "cercle", "commune", "se_id"]:
        if col not in gdf.columns:
            gdf[col] = None

    if "pop_se" not in gdf.columns:
        gdf["pop_se"] = 0

    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    return gdf

gdf = load_se_data(SE_URL)

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
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return sorted(series.dropna().astype(str).str.strip().unique())

# =========================================================
# ATTRIBUTE FILTERS
# =========================================================
st.sidebar.markdown("### 🗂️ Attribute Query")

region = st.sidebar.selectbox("Region", unique_clean(gdf["region"]))
gdf_r = gdf[gdf["region"] == region]

cercle = st.sidebar.selectbox("Cercle", unique_clean(gdf_r["cercle"]))
gdf_c = gdf_r[gdf_r["cercle"] == cercle]

commune = st.sidebar.selectbox("Commune", unique_clean(gdf_c["commune"]))
gdf_commune = gdf_c[gdf_c["commune"] == commune]

se_list = ["No filter"] + unique_clean(gdf_commune["se_id"])
se_selected = st.sidebar.selectbox("SE (num_se)", se_list)

gdf_se = gdf_commune if se_selected == "No filter" else gdf_commune[gdf_commune["se_id"] == se_selected]

# =========================================================
# SPATIAL QUERY
# =========================================================
st.sidebar.markdown("### 🧭 Spatial Query")
query_type = st.sidebar.selectbox("Query type", ["Intersects", "Within", "Contains"])

if st.sidebar.button("Run Query"):
    if st.session_state.points_gdf is not None:
        pts = st.session_state.points_gdf.to_crs(gdf_se.crs)
        st.session_state.query_result = gpd.sjoin(
            pts, gdf_se, predicate=query_type.lower(), how="inner"
        )

# =========================================================
# CSV UPLOAD (ADMIN)
# =========================================================
if st.session_state.user_role == "Admin":
    st.sidebar.markdown("### 📥 Upload CSV Points")
    csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])

    if csv_file is not None:
        df = pd.read_csv(csv_file)
        if {"Latitude", "Longitude"}.issubset(df.columns):
            st.session_state.points_gdf = gpd.GeoDataFrame(
                df,
                geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
                crs="EPSG:4326"
            )

# =========================================================
# MAP (OSM + GOOGLE SATELLITE)
# =========================================================
if not gdf_se.empty:
    minx, miny, maxx, maxy = gdf_se.total_bounds

    m = folium.Map(
        location=[(miny + maxy) / 2, (minx + maxx) / 2],
        zoom_start=13,
        tiles=None
    )

    # --- Base maps ---
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=False,
        control=True
    ).add_to(m)

    # --- SE polygons ---
    folium.GeoJson(
        gdf_se,
        name="SE",
        tooltip=folium.GeoJsonTooltip(
            fields=["se_id", "pop_se"],
            aliases=["SE Number", "Population"]
        ),
        style_function=lambda x: {
            "color": "blue",
            "weight": 2,
            "fillOpacity": 0.2,
        },
    ).add_to(m)

    points_to_show = st.session_state.query_result or st.session_state.points_gdf
    if points_to_show is not None:
        for _, r in points_to_show.iterrows():
            folium.CircleMarker(
                location=[r.geometry.y, r.geometry.x],
                radius=3,
                color="red",
                fill=True,
            ).add_to(m)

    MeasureControl().add_to(m)
    Draw(export=True).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    st_folium(m, height=550, use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**EMOP 2026 – Suivi Géospatial**  
Streamlit · GeoPandas · Folium  
**Mahamadou Oumar CAMARA, PhD – Geomatics Engineering** © 2025
""")
