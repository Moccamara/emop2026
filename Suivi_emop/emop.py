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
    st.session_state.points_gdf = None  # store uploaded CSV points
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
# LOAD SE POLYGONS
# =========================================================
#SE_URL = "https://raw.githubusercontent.com/Moccamara/emop2026/master/Suivi_emop/data/SE.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
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
try:
    gdf = load_se_data(SE_URL)
except Exception:
    st.error("❌ Unable to load SE.geojson from GitHub")
    st.stop()

# =========================================================
# SIDEBAR
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
gdf_idse = gdf_commune if idse_selected == "No filter" else gdf_commune[gdf_commune["idse_new"] == idse_selected]

# =========================================================
# LOAD POINTS
# =========================================================
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/concession.csv"

@st.cache_data(show_spinner=False)
def load_points_from_github(url):
    try:
        df = pd.read_csv(url)
        if not {"LAT", "LON"}.issubset(df.columns):
            return None
        df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
        df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
        df = df.dropna(subset=["LAT", "LON"])
        return gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
            crs="EPSG:4326"
        )
    except:
        return None

points_gdf = st.session_state.points_gdf if st.session_state.points_gdf is not None else load_points_from_github(POINTS_URL)

# =========================================================
# SPATIAL QUERY SIDEBAR
# =========================================================
st.sidebar.markdown("### 🧭 Spatial Query")
query_type = st.sidebar.selectbox(
    "Select query type",
    ["Intersects", "Within", "Contains"]
)
if st.sidebar.button("Run Query"):
    if points_gdf is not None:
        points_gdf = points_gdf.to_crs(gdf_idse.crs)
        if query_type == "Intersects":
            st.session_state.query_result = gpd.sjoin(points_gdf, gdf_idse, predicate="intersects", how="inner")
        elif query_type == "Within":
            st.session_state.query_result = gpd.sjoin(points_gdf, gdf_idse, predicate="within", how="inner")
        elif query_type == "Contains":
            st.session_state.query_result = gpd.sjoin(points_gdf, gdf_idse, predicate="contains", how="inner")
        if st.session_state.query_result.empty:
            st.sidebar.warning("No points match the query.")
        else:
            st.sidebar.success(f"{len(st.session_state.query_result)} points match the query")
    else:
        st.sidebar.error("No points available for the query.")

# =========================================================
# CSV UPLOAD (ADMIN ONLY)
# =========================================================
if st.session_state.user_role == "Admin":
    st.sidebar.markdown("### 📥 Upload CSV Points (Admin)")
    csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"], key="admin_csv")
    if csv_file is not None:
        try:
            df_csv = pd.read_csv(csv_file)
            required_cols = {"LAT", "LON"}
            if not required_cols.issubset(df_csv.columns):
                st.sidebar.error("CSV must contain LAT and LON columns")
            else:
                df_csv["LAT"] = pd.to_numeric(df_csv["LAT"], errors="coerce")
                df_csv["LON"] = pd.to_numeric(df_csv["LON"], errors="coerce")
                df_csv = df_csv.dropna(subset=["LAT", "LON"])
                points_gdf = gpd.GeoDataFrame(
                    df_csv,
                    geometry=gpd.points_from_xy(df_csv["LON"], df_csv["LAT"]),
                    crs="EPSG:4326"
                )
                st.session_state.points_gdf = points_gdf
                st.sidebar.success(f"✅ {len(points_gdf)} points loaded")
        except Exception as e:
            st.sidebar.error("Failed to read CSV file")

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny + maxy)/2, (minx + maxx)/2], zoom_start=18)
folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri",
).add_to(m)
m.fit_bounds([[miny, minx], [maxy, maxx]])
folium.GeoJson(
    gdf_idse,
    name="IDSE",
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.15},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(m)

# Use query result if exists, else default points
display_points = st.session_state.query_result if st.session_state.query_result is not None else points_gdf
if display_points is not None:
    for _, r in display_points.iterrows():
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=3,
            color="red",
            fill=True,
            fill_opacity=0.8
        ).add_to(m)

MeasureControl().add_to(m)
Draw(export=True).add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3,1), gap="small")

with col_map:
    st_folium(m, height=500, use_container_width=True)

with col_chart:
    if idse_selected == "No filter":
        st.info("Select SE.")
    else:
        # ----------------- Population Bar Chart -----------------
        st.subheader("📊 Population")
        df_long = gdf_idse[["idse_new","pop_se","pop_se_ct"]].copy()
        df_long["idse_new"] = df_long["idse_new"].astype(str)
        df_long = df_long.melt(
            id_vars="idse_new",
            value_vars=["pop_se","pop_se_ct"],
            var_name="Variable",
            value_name="Population"
        )
        df_long["Variable"] = df_long["Variable"].replace({"pop_se":"Pop SE","pop_se_ct":"Current Pop"})
        chart = (
            alt.Chart(df_long)
            .mark_bar()
            .encode(
                x=alt.X("idse_new:N", title=None, axis=alt.Axis(labelAngle=0)),
                xOffset="Variable:N",
                y=alt.Y("Population:Q", title=None),
                color=alt.Color("Variable:N", legend=alt.Legend(orient="right", title="Type")),
                tooltip=["idse_new","Variable","Population"]
            )
            .properties(height=150)
        )
        st.altair_chart(chart, use_container_width=True)

        # ----------------- Sex Pie Chart -----------------
        st.subheader("👥 Sex (M / F)")
        if points_gdf is None:
            st.info("Upload CSV file to view Sex distribution.")
        else:
            points_gdf.columns = points_gdf.columns.str.strip()
            if {"Masculin","Feminin"}.issubset(points_gdf.columns):
                gdf_idse_simple = gdf_idse.explode(ignore_index=True)
                pts_inside = gpd.sjoin(points_gdf, gdf_idse_simple, predicate="intersects", how="inner")
                if pts_inside.empty:
                    st.warning("No points inside the selected SE.")
                    m_total, f_total = 0, 0
                else:
                    pts_inside["Masculin"] = pd.to_numeric(pts_inside["Masculin"], errors="coerce").fillna(0)
                    pts_inside["Feminin"] = pd.to_numeric(pts_inside["Feminin"], errors="coerce").fillna(0)
                    m_total = int(pts_inside["Masculin"].sum())
                    f_total = int(pts_inside["Feminin"].sum())

                st.markdown(f"""
                - 👨 **M**: {m_total}  
                - 👩 **F**: {f_total}  
                - 👥 **Total**: {m_total + f_total}
                """)

                fig, ax = plt.subplots(figsize=(3,3))
                if m_total + f_total > 0:
                    ax.pie([m_total,f_total], labels=["M","F"], autopct="%1.1f%%", startangle=90, textprops={"fontsize":10})
                else:
                    ax.pie([1], labels=["No data"], colors=["lightgrey"])
                ax.axis("equal")
                st.pyplot(fig)
            else:
                st.warning("CSV must have 'Masculin' and 'Feminin' columns.")

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping** Developed with Streamlit, Folium & GeoPandas  
**Mahamadou CAMARA, PhD – Geomatics Engineering** © 2025
""")



