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
# LOAD SE POLYGONS (REAL SCHEMA)
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/emop2026.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)

    # CRS
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)

    # Normalize columns
    gdf.columns = [c.lower().strip() for c in gdf.columns]

    # Explicit renaming based on your REAL table
    gdf = gdf.rename(columns={
        "lregion": "region",
        "lcerde": "cercle",
        "lcommune": "commune",
        "num_se": "se_id"
    })

    # Safety guarantees
    for col in ["region", "cercle", "commune", "se_id"]:
        if col not in gdf.columns:
            gdf[col] = None

    if "pop_se" not in gdf.columns:
        gdf["pop_se"] = 0

    # Geometry validity
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
# ATTRIBUTE FILTERS (MATCH REAL DATA)
# =========================================================
st.sidebar.markdown("### 🗂️ Attribute Query")

def unique_clean(series):
    return sorted(
        series
        .apply(lambda x: str(x).strip() if pd.notna(x) else None)
        .dropna()
        .unique()
    )

# REGION
regions = unique_clean(gdf["region"])
region = st.sidebar.selectbox("Region", regions)
gdf_r = gdf[gdf["region"] == region]

# CERCLE
cercles = unique_clean(gdf_r["cercle"])
cercle = st.sidebar.selectbox("Cercle", cercles)
gdf_c = gdf_r[gdf_r["cercle"] == cercle]

# COMMUNE
communes = unique_clean(gdf_c["commune"])
commune = st.sidebar.selectbox("Commune", communes)
gdf_commune = gdf_c[gdf_c["commune"] == commune]

# SE (num_se)
se_list = ["No filter"] + unique_clean(gdf_commune["se_id"])
se_selected = st.sidebar.selectbox("SE (num_se)", se_list)

gdf_se = (
    gdf_commune
    if se_selected == "No filter"
    else gdf_commune[gdf_commune["se_id"] == se_selected]
)

# =========================================================
# SPATIAL QUERY
# =========================================================
st.sidebar.markdown("### 🧭 Spatial Query")
query_type = st.sidebar.selectbox("Select query type", ["Intersects", "Within", "Contains"])

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
# CSV UPLOAD (ADMIN)
# =========================================================
if st.session_state.user_role == "Admin":
    st.sidebar.markdown("### 📥 Upload CSV Points")
    csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])

    if csv_file is not None:
        df = pd.read_csv(csv_file)
        if {"Latitude", "Longitude"}.issubset(df.columns):
            gdf_pts = gpd.GeoDataFrame(
                df,
                geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
                crs="EPSG:4326"
            )
            st.session_state.points_gdf = gdf_pts
            st.sidebar.success(f"✅ {len(gdf_pts)} points loaded")
        else:
            st.sidebar.error("CSV must contain Latitude & Longitude")

# =========================================================
# MAP
# =========================================================
if not gdf_se.empty:
    minx, miny, maxx, maxy = gdf_se.total_bounds
    m = folium.Map(
        location=[(miny + maxy) / 2, (minx + maxx) / 2],
        zoom_start=13
    )

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
    if points_to_show is not None and not points_to_show.empty:
        for _, r in points_to_show.iterrows():
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
        st_folium(m, height=520, use_container_width=True)

    with col_chart:
        if se_selected != "No filter":
            st.subheader("📊 Population (SE)")
            st.metric(
                label=f"SE {se_selected}",
                value=int(gdf_se["pop_se"].sum())
            )

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**EMOP 2026 – Suivi Géospatial**  
Streamlit · GeoPandas · Folium  
**Mahamadou Oumar CAMARA, PhD – Geomatics Engineering** © 2025
""")
