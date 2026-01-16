import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt

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
    st.session_state.query_result = None

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.session_state.query_result = None
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
# SAFE POINTS INIT
# =========================================================
points_gdf = st.session_state.points_gdf

# =========================================================
# LOAD SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/SE.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)

    gdf.columns = gdf.columns.str.lower().str.strip()
    gdf = gdf.rename(columns={
        "lregion": "region",
        "lcercle": "cercle",
        "lcommune": "commune"
    })

    gdf = gdf[gdf.is_valid & ~gdf.is_empty]

    for col in ["region", "cercle", "commune", "idse_new"]:
        if col not in gdf.columns:
            gdf[col] = ""

    for col in ["pop_se", "pop_se_ct"]:
        if col not in gdf.columns:
            gdf[col] = 0

    return gdf

try:
    gdf = load_se_data(SE_URL)
except Exception as e:
    st.error(f"❌ Unable to load SE.geojson: {e}")
    st.stop()

# =========================================================
# SIDEBAR HEADER
# =========================================================
with st.sidebar:
    st.image("Suivi_emop/logo/emop.png", width=200)
    st.markdown(f"**Logged in as:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

# =========================================================
# ATTRIBUTE FILTERS
# =========================================================
st.sidebar.markdown("### 🗂️ Attribute Query")

region = st.sidebar.selectbox("Region", sorted(gdf["region"].dropna().unique()))
gdf_r = gdf[gdf["region"] == region]

cercle = st.sidebar.selectbox("Cercle", sorted(gdf_r["cercle"].dropna().unique()))
gdf_c = gdf_r[gdf_r["cercle"] == cercle]

commune = st.sidebar.selectbox("Commune", sorted(gdf_c["commune"].dropna().unique()))
gdf_commune = gdf_c[gdf_c["commune"] == commune]

idse_list = ["No filter"] + sorted(gdf_commune["idse_new"].dropna().unique())
idse_selected = st.sidebar.selectbox("Unit_Geo", idse_list)

gdf_idse = (
    gdf_commune if idse_selected == "No filter"
    else gdf_commune[gdf_commune["idse_new"] == idse_selected]
)

# =========================================================
# SPATIAL QUERY
# =========================================================
st.sidebar.markdown("### 🧭 Spatial Query")
query_type = st.sidebar.selectbox(
    "Select query type", ["Intersects", "Within", "Contains"]
)

if st.sidebar.button("Run Query"):
    if points_gdf is not None and not gdf_idse.empty:
        pts = points_gdf.to_crs(gdf_idse.crs)
        st.session_state.query_result = gpd.sjoin(
            pts, gdf_idse, predicate=query_type.lower(), how="inner"
        )

        if st.session_state.query_result.empty:
            st.sidebar.warning("No points match the query.")
        else:
            st.sidebar.success(f"{len(st.session_state.query_result)} points found.")
    else:
        st.sidebar.error("No point data available.")

# =========================================================
# CSV UPLOAD (ADMIN ONLY)
# =========================================================
if st.session_state.user_role == "Admin":
    st.sidebar.markdown("### 📥 Upload CSV Points (Admin)")
    csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])

    if csv_file is not None:
        try:
            try:
                df = pd.read_csv(csv_file, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(csv_file, encoding="latin1")

            required_cols = {"Latitude", "Longitude"}
            if not required_cols.issubset(df.columns):
                st.sidebar.error("CSV must contain 'Latitude' and 'Longitude'")
            else:
                df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
                df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
                df = df.dropna(subset=["Latitude", "Longitude"])

                points_gdf = gpd.GeoDataFrame(
                    df,
                    geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"])
                )

                # CRS FIX (Folium needs WGS84)
                points_gdf = points_gdf.set_crs(epsg=4326, allow_override=True)

                st.session_state.points_gdf = points_gdf
                st.sidebar.success(f"✅ {len(points_gdf)} points loaded")

        except Exception as e:
            st.sidebar.error(f"Failed to read CSV: {e}")

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(
    location=[(miny + maxy) / 2, (minx + maxx) / 2],
    zoom_start=14
)

folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri"
).add_to(m)

folium.GeoJson(
    gdf_idse,
    name="IDSE",
    style_function=lambda x: {
        "color": "blue",
        "weight": 2,
        "fillOpacity": 0.15
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["idse_new", "pop_se", "pop_se_ct"]
    ),
).add_to(m)

display_points = (
    st.session_state.query_result
    if st.session_state.query_result is not None
    else points_gdf
)

if display_points is not None and not display_points.empty:
    pts_wgs84 = display_points.to_crs(epsg=4326)

    for _, r in pts_wgs84.iterrows():
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=3,
            color="red",
            fill=True,
            fill_opacity=0.8,
        ).add_to(m)

MeasureControl().add_to(m)
Draw(export=True).add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3, 1), gap="small")

with col_map:
    st_folium(m, height=500, use_container_width=True)

with col_chart:
    if idse_selected != "No filter":
        st.subheader("📊 Population")
        df_long = gdf_idse.melt(
            id_vars="idse_new",
            value_vars=["pop_se", "pop_se_ct"],
            var_name="Type",
            value_name="Population",
        )

        st.altair_chart(
            alt.Chart(df_long)
            .mark_bar()
            .encode(
                x="idse_new:N",
                y="Population:Q",
                color="Type:N",
                tooltip=["idse_new", "Type", "Population"]
            )
            .properties(height=150),
            use_container_width=True,
        )

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
Developed with Streamlit, Folium & GeoPandas  
**Mahamadou CAMARA, PhD – Geomatics Engineering** © 2025
""")
