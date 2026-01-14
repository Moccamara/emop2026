import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point
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
    st.session_state.run_spatial_query = False  # <-- Added to store query state

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
SE_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/SE.geojson"

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
# LOAD CONCESSION POINTS
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
        df = df.dropna(subset=["LAT","LON"])
        return gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
            crs="EPSG:4326"
        )
    except:
        return None

# =========================================================
# POINTS SOURCE LOGIC
# =========================================================
if st.session_state.points_gdf is not None:
    points_gdf = st.session_state.points_gdf
else:
    points_gdf = load_points_from_github(POINTS_URL)
    st.session_state.points_gdf = points_gdf

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons, how="inner", predicate="intersects"):
    if points is None or points.empty or polygons is None or polygons.empty:
        return gpd.GeoDataFrame(
            columns=points.columns if points is not None else [],
            crs=points.crs if points is not None else None
        )
    for col in ["index_right", "_r"]:
        if col in polygons.columns:
            polygons = polygons.drop(columns=[col])
    return gpd.sjoin(points, polygons, how=how, predicate=predicate, rsuffix="_r")

# =========================================================
# SIDEBAR FILTERS
# =========================================================
with st.sidebar:
    st.image("logo/logo_wgv.png", width=200)
    st.markdown(f"**Logged in as:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

    st.markdown("### 🗂️ Attribute Query")
    region = st.selectbox("Region", sorted(gdf["region"].dropna().unique()))
    gdf_r = gdf[gdf["region"] == region]

    cercle = st.selectbox("Cercle", sorted(gdf_r["cercle"].dropna().unique()))
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]

    commune = st.selectbox("Commune", sorted(gdf_c["commune"].dropna().unique()))
    gdf_commune = gdf_c[gdf_c["commune"] == commune]

    idse_list = ["No filter"] + sorted(gdf_commune["idse_new"].dropna().unique())
    idse_selected = st.selectbox("Unit_Geo", idse_list)
    gdf_idse = gdf_commune if idse_selected=="No filter" else gdf_commune[gdf_commune["idse_new"]==idse_selected]

    # =========================================================
    # Spatial Query (Admin only) with Run/Cancel
    # =========================================================
    pts_inside_map = None
    if st.session_state.user_role=="Admin":
        st.markdown("### 🛰️ Spatial Query")
        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("Run Spatial Query"):
                st.session_state.run_spatial_query = True
        with col2:
            if st.button("Cancel Spatial Query"):
                st.session_state.run_spatial_query = False

        if st.session_state.run_spatial_query and points_gdf is not None:
            pts_inside_map = safe_sjoin(points_gdf, gdf_idse, predicate="intersects")
            st.success(f"✅ Spatial query returned {len(pts_inside_map)} points inside selected SE.")
        else:
            pts_inside_map = None

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=18)

# ===== Base layers =====
folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri",
    control=True
).add_to(m)

m.fit_bounds([[miny,minx],[maxy,maxx]])

# ===== Overlay layers =====
# SE Polygons
fg_idse = folium.FeatureGroup(name="SE Polygons", show=True)
folium.GeoJson(
    gdf_idse,
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.15},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(fg_idse)
fg_idse.add_to(m)

# Concession Points
points_to_plot = pts_inside_map if (st.session_state.user_role=="Admin" and pts_inside_map is not None) else points_gdf
fg_points = folium.FeatureGroup(name="Concession Points", show=True)
if points_to_plot is not None:
    points_to_plot = points_to_plot.to_crs(gdf_idse.crs)
    for _, r in points_to_plot.iterrows():
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=3,
            color="red",
            fill=True,
            fill_opacity=0.8
        ).add_to(fg_points)
fg_points.add_to(m)

# Plugins
MeasureControl().add_to(m)
draw_control = Draw(export=True, draw_options={"polyline": False, "rectangle": False, "circle": False, "circlemarker": False})
draw_control.add_to(m)

MousePosition(
    position="bottomright",
    separator=" | ",
    empty_string="Move cursor",
    lng_first=True,
    num_digits=6,
    prefix="Coordinates:"
).add_to(m)

# ===== Dynamic Legend / LayerControl =====
folium.LayerControl(collapsed=True).add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3,1), gap="small")
with col_map:
    # Display map and capture drawn polygons & markers
    map_data = st_folium(
        m,
        height=500,
        returned_objects=["all_drawings"],
        use_container_width=True
    )

    # ================================
    # DYNAMIC MARKER TABLE AND GEOJSON DOWNLOAD
    # ================================
    markers_list = []

    if map_data and "all_drawings" in map_data and map_data["all_drawings"]:
        for feature in map_data["all_drawings"]:
            geom_type = feature["geometry"]["type"]
            geom_shape = shape(feature["geometry"])
            if geom_type == "Point":
                markers_list.append({"Latitude": geom_shape.y, "Longitude": geom_shape.x, "Label": ""})

    if markers_list:
        markers_df = pd.DataFrame(markers_list)
        st.subheader("📍 Marker Table (Editable Labels)")
        edited_df = st.data_editor(markers_df, num_rows="dynamic")

        # Save edited markers to GeoJSON
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [row.Longitude, row.Latitude]},
                    "properties": {"Label": row.Label}
                }
                for _, row in edited_df.iterrows()
            ]
        }
        st.download_button(
            label="💾 Download Markers as GeoJSON",
            data=json.dumps(geojson_data),
            file_name="markers.geojson",
            mime="application/json"
        )

with col_chart:

    # Polygon-based statistics
    if map_data and "all_drawings" in map_data and map_data["all_drawings"]:
        last_feature = map_data["all_drawings"][-1]
        drawn_polygon = shape(last_feature["geometry"])
        if drawn_polygon is not None and points_gdf is not None:
            pts_in_polygon = points_gdf[points_gdf.geometry.within(drawn_polygon)]
            st.subheader("🟢 Points inside drawn polygon")
            st.markdown(f"- Total points: {len(pts_in_polygon)}")
            if not pts_in_polygon.empty:
                attr_cols = [c for c in ["Masculin","Feminin"] if c in pts_in_polygon.columns]
                if attr_cols:
                    stats = pts_in_polygon[attr_cols].sum().to_frame().T
                    stats["Total"] = stats.sum(axis=1)
                    st.dataframe(stats)
                else:
                    st.dataframe(pts_in_polygon)

with col_chart:
    # Population bar chart
    if idse_selected=="No filter":
        st.info("Select SE.")
    else:
        st.subheader("📊 Population")
        df_long = gdf_idse[["idse_new","pop_se","pop_se_ct"]].copy()
        df_long["idse_new"] = df_long["idse_new"].astype(str)
        df_long = df_long.melt(id_vars="idse_new", value_vars=["pop_se","pop_se_ct"],
                               var_name="Variable", value_name="Population")
        df_long["Variable"] = df_long["Variable"].replace({"pop_se":"Pop Ref","pop_se_ct":"Pop Current"})
        chart = (alt.Chart(df_long)
                 .mark_bar()
                 .encode(x=alt.X("idse_new:N", title=None, axis=alt.Axis(labelAngle=0)),
                         xOffset="Variable:N",
                         y=alt.Y("Population:Q", title=None),
                         color=alt.Color("Variable:N", legend=alt.Legend(orient="right", title="Type")),
                         tooltip=["idse_new","Variable","Population"])
                 .properties(height=150))
        st.altair_chart(chart, use_container_width=True)

        # ===========================
        # Sex pie chart
        # ===========================
        st.subheader("👥 Sex (M / F) in selected SE")
        if points_gdf is not None and {"Masculin","Feminin"}.issubset(points_gdf.columns):
            gdf_idse_simple = gdf_idse.explode(ignore_index=True)
            pts_inside = safe_sjoin(points_gdf, gdf_idse_simple, predicate="intersects")
            if not pts_inside.empty:
                m_total = int(pts_inside["Masculin"].sum())
                f_total = int(pts_inside["Feminin"].sum())
            else:
                m_total, f_total = 0,0
            st.markdown(f"- 👨 **M**: {m_total}  \n- 👩 **F**: {f_total}  \n- 👥 **Total**: {m_total+f_total}")

            fig, ax = plt.subplots(figsize=(3,3))
            if m_total + f_total > 0:
                ax.pie([m_total,f_total], labels=["M","F"], autopct="%1.1f%%", startangle=90, colors=["#1f77b4","#ff7f0e"])
            else:
                ax.pie([1], labels=["No data"], colors=["lightgrey"])
            ax.axis("equal")
            st.pyplot(fig)
            
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
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping** Developed with Streamlit, Folium & GeoPandas  
**Dr. Mahamadou CAMARA, PhD – Geomatics Engineering** © 2025
""")


