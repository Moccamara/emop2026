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
    for k in list(st.session_state.keys()):
        del st.session_state[k]
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
# LOAD SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/emop2026.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)

    # CRS fix
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)

    # Normalize columns
    gdf.columns = gdf.columns.str.lower().str.strip()

    # Flexible renaming (handles ALL EMOP schemas)
    rename_map = {}
    for col in gdf.columns:
        if "region" in col:
            rename_map[col] = "region"
        elif "cercle" in col:
            rename_map[col] = "cercle"
        elif "commune" in col:
            rename_map[col] = "commune"

    gdf = gdf.rename(columns=rename_map)

    # Guarantee required columns
    for col in ["region", "cercle", "commune", "idse_new"]:
        if col not in gdf.columns:
            gdf[col] = ""

    for col in ["pop_se", "pop_se_ct"]:
        if col not in gdf.columns:
            gdf[col] = 0

    # Geometry cleaning
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]

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

# --- REGION ---
regions = sorted(
    gdf["region"].astype(str).str.strip().replace("", pd.NA).dropna().unique()
)

if regions:
    region = st.sidebar.selectbox("Region", regions)
    gdf_r = gdf[gdf["region"] == region]
else:
    st.sidebar.warning("No Region data available")
    gdf_r = gdf.copy()

# --- CERCLE ---
cercles = sorted(
    gdf_r["cercle"].astype(str).str.strip().replace("", pd.NA).dropna().unique()
)

if cercles:
    cercle = st.sidebar.selectbox("Cercle", cercles)
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]
else:
    st.sidebar.warning("No Cercle data available")
    gdf_c = gdf_r.copy()

# --- COMMUNE ---
communes = sorted(
    gdf_c["commune"].astype(str).str.strip().replace("", pd.NA).dropna().unique()
)

if communes:
    commune = st.sidebar.selectbox("Commune", communes)
    gdf_commune = gdf_c[gdf_c["commune"] == commune]
else:
    st.sidebar.warning("No Commune data available")
    gdf_commune = gdf_c.copy()

# --- IDSE ---
idse_list = ["No filter"] + sorted(
    gdf_commune["idse_new"].astype(str).str.strip().replace("", pd.NA).dropna().unique()
)

idse_selected = st.sidebar.selectbox("Unit_Geo", idse_list)

gdf_idse = (
    gdf_commune
    if idse_selected == "No filter"
    else gdf_commune[gdf_commune["idse_new"] == idse_selected]
)

# =========================================================
# SPATIAL QUERY
# =========================================================
st.sidebar.markdown("### 🧭 Spatial Query")
query_type = st.sidebar.selectbox("Select query type", ["Intersects", "Within", "Contains"])

if st.sidebar.button("Run Query"):
    if st.session_state.points_gdf is not None and not gdf_idse.empty:
        pts = st.session_state.points_gdf.to_crs(gdf_idse.crs)
        st.session_state.query_result = gpd.sjoin(
            pts, gdf_idse, predicate=query_type.lower(), how="inner"
        )
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
        df = pd.read_csv(csv_file)
        df = df.rename(columns=str.strip)

        if {"Latitude", "Longitude"}.issubset(df.columns):
            points_gdf = gpd.GeoDataFrame(
                df,
                geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
                crs="EPSG:4326",
            )
            st.session_state.points_gdf = points_gdf
            st.sidebar.success(f"✅ {len(points_gdf)} points loaded")
        else:
            st.sidebar.error("CSV must contain Latitude and Longitude")

# =========================================================
# MAP
# =========================================================
if not gdf_idse.empty:
    minx, miny, maxx, maxy = gdf_idse.total_bounds
    m = folium.Map(
        location=[(miny + maxy) / 2, (minx + maxx) / 2],
        zoom_start=13,
    )

    folium.GeoJson(
        gdf_idse,
        name="IDSE",
        tooltip=folium.GeoJsonTooltip(
            fields=["idse_new", "pop_se", "pop_se_ct"]
        ),
        style_function=lambda x: {
            "color": "blue",
            "weight": 2,
            "fillOpacity": 0.2,
        },
    ).add_to(m)

    display_points = st.session_state.query_result or st.session_state.points_gdf
    if display_points is not None and not display_points.empty:
        for _, r in display_points.iterrows():
            folium.CircleMarker(
                location=[r.geometry.y, r.geometry.x],
                radius=3,
                color="red",
                fill=True,
            ).add_to(m)

    MeasureControl().add_to(m)
    Draw(export=True).add_to(m)
    folium.LayerControl().add_to(m)

    col_map, col_chart = st.columns((3, 1))

    with col_map:
        st_folium(m, height=500, use_container_width=True)

    with col_chart:
        if idse_selected != "No filter":
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
                ),
                use_container_width=True,
            )

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
Developed with Streamlit, Folium & GeoPandas  
**Mahamadou Oumar CAMARA, PhD – Geomatics Engineering** © 2025
""")
