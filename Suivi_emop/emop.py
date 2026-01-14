import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape
import json

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="Geospatial Enterprise Solution")
st.title("🌍 Geospatial Enterprise Solution")

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
    st.session_state.run_spatial_query = False

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.session_state.run_spatial_query = False
    st.rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    username = st.sidebar.selectbox("User", list(USERS.keys()))
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login", use_container_width=True):
        if password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]
            st.success("✅ Login successful")
            st.rerun()
        else:
            st.sidebar.error("❌ Incorrect password")
    st.stop()

# =========================================================
# LOAD SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/SE.geojson"
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/concession.csv"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)
    gdf = gdf.to_crs(epsg=4326) if gdf.crs else gdf.set_crs(epsg=4326)
    gdf.columns = gdf.columns.str.lower().str.strip()
    gdf = gdf.rename(columns={"lregion":"region","lcercle":"cercle","lcommune":"commune"})
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]

    for col in ["region","cercle","commune","idse_new"]:
        if col not in gdf.columns:
            gdf[col] = ""
    for col in ["pop_se","pop_se_ct"]:
        if col not in gdf.columns:
            gdf[col] = 0

    return gdf

@st.cache_data(show_spinner=False)
def load_points_from_github(url):
    try:
        df = pd.read_csv(url)
        if not {"LAT","LON"}.issubset(df.columns):
            return None

        df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
        df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
        df = df.dropna(subset=["LAT","LON"])

        return gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
            crs="EPSG:4326"
        )
    except:
        return None

def safe_sjoin(points, polygons, predicate="intersects"):
    if points is None or points.empty or polygons is None or polygons.empty:
        return gpd.GeoDataFrame(columns=points.columns if points is not None else [])
    return gpd.sjoin(points, polygons, predicate=predicate)

gdf = load_se_data(SE_URL)

# =========================================================
# INIT POINTS (SAFE & GLOBAL)
# =========================================================
if st.session_state.points_gdf is None:
    st.session_state.points_gdf = load_points_from_github(POINTS_URL)

points_gdf = st.session_state.points_gdf

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.image(
        "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/logo/logo_wgv.png",
        width=200
    )

    st.markdown(f"**Logged in as:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

    st.markdown("### 🗂️ Attribute Query")
    region = st.selectbox("Region", sorted(gdf["region"].unique()))
    gdf_r = gdf[gdf["region"] == region]

    cercle = st.selectbox("Cercle", sorted(gdf_r["cercle"].unique()))
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]

    commune = st.selectbox("Commune", sorted(gdf_c["commune"].unique()))
    gdf_commune = gdf_c[gdf_c["commune"] == commune]

    idse_list = ["No filter"] + sorted(gdf_commune["idse_new"].unique())
    idse_selected = st.selectbox("Unit_Geo", idse_list)

    gdf_idse = gdf_commune if idse_selected=="No filter" else gdf_commune[gdf_commune["idse_new"]==idse_selected]

    pts_inside_map = None
    if st.session_state.user_role == "Admin":
        st.markdown("### 🛰️ Spatial Query")
        if st.button("Run Spatial Query"):
            st.session_state.run_spatial_query = True
        if st.button("Cancel Spatial Query"):
            st.session_state.run_spatial_query = False

        if st.session_state.run_spatial_query and points_gdf is not None:
            pts_inside_map = safe_sjoin(points_gdf, gdf_idse)

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=17)

folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri"
).add_to(m)

folium.GeoJson(
    gdf_idse,
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.15},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(m)

fg_points = folium.FeatureGroup(name="Concession Points")
points_to_plot = pts_inside_map if (st.session_state.user_role=="Admin" and pts_inside_map is not None) else points_gdf

if points_to_plot is not None:
    for _, r in points_to_plot.iterrows():
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=3,
            color="red",
            fill=True
        ).add_to(fg_points)

fg_points.add_to(m)

MeasureControl().add_to(m)
Draw(export=True).add_to(m)
MousePosition(prefix="Coordinates").add_to(m)
folium.LayerControl().add_to(m)

# =========================================================
# DISPLAY
# =========================================================
col_map, col_chart = st.columns((3,1))

with col_map:
    map_data = st_folium(m, height=500, returned_objects=["all_drawings"])

with col_chart:
    if idse_selected != "No filter":
        df_long = gdf_idse[["idse_new","pop_se","pop_se_ct"]].melt(
            id_vars="idse_new", var_name="Type", value_name="Population"
        )
        chart = alt.Chart(df_long).mark_bar().encode(
            x="Type:N", y="Population:Q", color="Type:N"
        )
        st.altair_chart(chart, use_container_width=True)

# =========================================================
# CSV UPLOAD (ADMIN)
# =========================================================
if st.session_state.user_role == "Admin":
    st.sidebar.markdown("### 📥 Upload CSV Points")
    csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])
    if csv_file:
        df = pd.read_csv(csv_file)
        df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
        df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
        df = df.dropna(subset=["LAT","LON"])
        st.session_state.points_gdf = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
            crs="EPSG:4326"
        )
        st.sidebar.success("✅ Points loaded")

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
Developed with Streamlit, Folium & GeoPandas  
**Dr. Mahamadou CAMARA, PhD – Geomatics Engineering** © 2025
""")
